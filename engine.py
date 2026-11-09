"""
Bilingual speech engine: Hebrew via ReNikud, English via espeak-ng.

HebrewReader's basic voice is Piper "noa" (thewh1teagle/piper-he-noa, CC BY 4.0): one VITS model with two
speakers, noa (Hebrew, trained on renikud's stressed IPA) and ljspeech (English, public-domain LJSpeech). A Hebrew run
is read by noa, a whole English run by ljspeech, so English words keep a native accent. HebrewSpeaker used two StyleTTS2
models here; their origin and licence could not be verified (business/legal/hebrew-reader-licenses.md), so they are
not shipped. The run splitting, merging and seams below are HebrewSpeaker's, unchanged.

Hebrew text first goes through hebrew_text.py (numbers in the right gender, dates,
abbreviations, the pronunciation lexicon, words written with nikud) and only then
to ReNikud. Both engines, and the hub through them, share that layer.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

import numpy as np

import hebrew_text
import paths

MODELS_DIR = paths.MODELS
PIPER_MODEL = MODELS_DIR / "piper" / "he_IL-noa-medium.onnx"
PIPER_CONFIG = MODELS_DIR / "piper" / "he_IL-noa-medium.onnx.json"
RENIKUD_MODEL = MODELS_DIR / "renikud.onnx"
SPEAKERS = {"he": 0, "en": 1}  # noa, ljspeech (speaker_id_map in the config)

SAMPLE_RATE = 24000
JOIN_GAP = 0.14  # breath inserted at a language switch, in seconds
EDGE_FADE = 0.006  # fade at each seam, long enough to kill clicks, short enough to hide
CLOSING_FADE = 0.07  # the last run of a phrase is allowed to settle, not cut off
SILENCE_FLOOR = 0.004  # amplitude below this counts as silence when trimming
KEEP_TAIL = 0.16  # seconds of the natural decay kept after the last loud sample
MIN_RUN_PHONEMES = 14  # below this a run is too short to render on its own
PEAK_TARGET = 0.85  # the two models are levelled to this, so a switch is not a jump
MAX_GAIN, MIN_GAIN = 1.35, 0.75  # levelling stays gentle, never enough to clip

_HEBREW_LETTER = re.compile(r"[א-ת]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_EDGE_PUNCT = ".,!?;:…\"'()[]{}-–—«»"

# English owns sounds Hebrew does not. Handing them to the Hebrew model
# produces noise - it turned "wav" into "rav" - so a fragment that ends up
# hosted by the other language is first bent into that language's inventory,
# which is what a speaker's mouth does anyway.
# Only the consonants Hebrew genuinely does not own. Bending the vowels too
# was measurably worse: it broke words the model already said correctly,
# turning "Unity" into "Unary".
_EN_TO_HE = {
    "w": "v",       # אין w בעברית
    "θ": "t",  # think
    "ð": "d",  # this
    "ŋ": "n",  # sing
}
_HE_TO_EN = {"ʁ": "ɹ", "χ": "x"}


# An all-capitals token is spelled out letter by letter. espeak already does
# this for shapes it cannot pronounce (PDF, USB), but reads a pronounceable
# one as a word - and "WAV" spoken as a word came back from the transcriber as
# "רב". Spelling is the safer default for a reader.
_ACRONYM = re.compile(r"^[A-Z0-9]{2,6}$")

# The letter names are phonemized from their spellings rather than typed out
# as IPA by hand, so they always match the voice the rest of the text uses.
_LETTER_WORDS = {
    "A": "eh", "B": "bee", "C": "see", "D": "dee", "E": "ee", "F": "ef",
    "G": "jee", "H": "aitch", "I": "eye", "J": "jay", "K": "kay", "L": "el",
    "M": "em", "N": "en", "O": "oh", "P": "pee", "Q": "cue", "R": "ar",
    "S": "ess", "T": "tee", "U": "you", "V": "vee", "W": "double you",
    "X": "ex", "Y": "why", "Z": "zee",
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}


def _is_acronym(token: str) -> bool:
    return bool(_ACRONYM.match(token)) and sum(c.isalpha() for c in token) >= 2


def adapt_phonemes(phonemes: str, host: str) -> str:
    """Rewrite a fragment so the hosting model can actually pronounce it."""
    table = _EN_TO_HE if host == "he" else _HE_TO_EN
    return "".join(table.get(c, c) for c in phonemes)


def _script_of(char: str) -> str:
    if _HEBREW_LETTER.match(char):
        return "he"
    if _LATIN_LETTER.match(char):
        return "en"
    return "neutral"


def split_by_script(text: str) -> list[tuple[str, str]]:
    """Split text into runs of Hebrew and English.

    Digits, punctuation and spaces have no script of their own, so they join
    the run they follow - and the run they precede when they open the text.
    """
    runs: list[list[str]] = []
    for char in text:
        script = _script_of(char)
        if runs and (script == "neutral" or runs[-1][0] in (script, "neutral")):
            if runs[-1][0] == "neutral" and script != "neutral":
                runs[-1][0] = script
            runs[-1][1] += char
        else:
            runs.append([script, char])

    merged: list[tuple[str, str]] = []
    for script, chunk in runs:
        script = "he" if script == "neutral" else script
        if merged and merged[-1][0] == script:
            merged[-1] = (script, merged[-1][1] + chunk)
        else:
            merged.append((script, chunk))
    return [(s, c) for s, c in merged if c.strip()]


def dominant_script(text: str) -> str:
    """Which language leads this text - Hebrew wins whenever it appears."""
    if _HEBREW_LETTER.search(text):
        return "he"
    return "en" if _LATIN_LETTER.search(text) else "he"


def _trim(samples: np.ndarray) -> np.ndarray:
    """Drop the silent lead-in and the silent tail, keeping the natural decay."""
    loud = np.flatnonzero(np.abs(samples) > SILENCE_FLOOR)
    if loud.size == 0:
        return samples[:0]
    start = max(0, loud[0] - int(SAMPLE_RATE * 0.01))
    end = min(len(samples), loud[-1] + int(SAMPLE_RATE * KEEP_TAIL))
    return samples[start:end]


def _soften_edges(samples: np.ndarray, closing: bool = False) -> np.ndarray:
    """Ramp both ends so a seam cannot click.

    The final run of a phrase gets a longer tail fade, so the voice settles
    the way a speaker does instead of stopping dead - a hard cut is a large
    part of what makes synthetic speech sound mechanical.
    """
    out = samples.copy()
    lead = min(int(SAMPLE_RATE * EDGE_FADE), len(out) // 2)
    if lead > 1:
        out[:lead] *= np.linspace(0.0, 1.0, lead, dtype="float32")
    tail_seconds = CLOSING_FADE if closing else EDGE_FADE
    tail = min(int(SAMPLE_RATE * tail_seconds), len(out) // 2)
    if tail > 1:
        out[-tail:] *= np.linspace(1.0, 0.0, tail, dtype="float32")
    return out


def _phoneme_weight(phonemes: str) -> int:
    return len([c for c in phonemes if c not in " .,!?;:\u2026"])


def _merge_short_runs(items: list[dict]) -> list[dict]:
    """Fold tiny runs into a neighbour before anything is rendered.

    The TTS model stretches and smears an utterance it considers too short (measured on StyleTTS2): the
    phonemes of "WAV" alone come out at 186ms each, against 78ms inside a full
    sentence. That smearing is what a lone acronym sounds like. Merging keeps
    each fragment's own phonemes - so the word is still pronounced in its own
    language - while giving the model enough context to speak it cleanly.
    """
    while len(items) > 1:
        index = next(
            (
                i
                for i, item in enumerate(items)
                if _phoneme_weight(_render_phonemes(item)) < MIN_RUN_PHONEMES
            ),
            None,
        )
        if index is None:
            break

        script = items[index]["script"]
        before = items[index - 1] if index > 0 else None
        after = items[index + 1] if index + 1 < len(items) else None
        take_after = None
        # a neighbour in the same language is always the better home
        if before is not None and before["script"] == script:
            take_after = False
        elif after is not None and after["script"] == script:
            take_after = True
        elif before is None:
            take_after = True
        elif after is None:
            take_after = False
        else:
            take_after = _phoneme_weight(_render_phonemes(after)) > _phoneme_weight(
                _render_phonemes(before)
            )
        if take_after:
            partner, order = after, (index, index + 1)
        else:
            partner, order = before, (index - 1, index)

        first, second = items[order[0]], items[order[1]]
        items[order[0] : order[1] + 1] = [_join(first, second)]
    return _coalesce_same_script(items)


def _join(first: dict, second: dict) -> dict:
    """Weld two runs, and let the language carrying more speech pick the model."""
    spoken = {
        "he": first["spoken"]["he"] + second["spoken"]["he"],
        "en": first["spoken"]["en"] + second["spoken"]["en"],
    }
    # A switch of language inside a single render cannot carry a silence, so it
    # carries a comma instead: the model reads punctuation as a real pause.
    crosses = first["tail"] != second["head"]
    tail = first["parts"][-1]["phonemes"].rstrip()
    bridge = ", " if crosses and tail and tail[-1] not in ".,!?;:\u2026" else " "
    parts = list(first["parts"])
    for index, part in enumerate(second["parts"]):
        part = dict(part)
        if index == 0:
            part["separator"] = bridge
        parts.append(part)
    return {
        "script": "he" if spoken["he"] else "en",
        "spoken": spoken,
        "head": first["head"],
        "tail": second["tail"],
        "text": f"{first['text']} {second['text']}",
        "parts": parts,
    }


def _coalesce_same_script(items: list[dict]) -> list[dict]:
    """Join adjacent runs of one language - every seam avoided is a seam that
    cannot be heard."""
    out: list[dict] = []
    for item in items:
        if out and out[-1]["script"] == item["script"]:
            out[-1] = _join(out[-1], item)
        else:
            out.append(item)
    return out


def _render_phonemes(item: dict) -> str:
    """The phonemes as the hosting model will actually receive them."""
    host = item["script"]
    out = []
    for index, part in enumerate(item["parts"]):
        phonemes = part["phonemes"]
        if part["script"] != host:
            phonemes = adapt_phonemes(phonemes, host)
        out.append(("" if index == 0 else part["separator"]) + phonemes)
    return "".join(out)


def resample(audio: np.ndarray, rate_in: int, rate_out: int) -> np.ndarray:
    """Band-limited resampling by FFT, numpy only (keeps scipy, 68 MB, out of the download).

    The piece is padded with silence first so the FFT's wrap-around cannot fold its end onto its start."""
    if audio.size == 0 or rate_in == rate_out:
        return audio.astype("float32")
    from math import gcd

    step_in = rate_in // gcd(rate_in, rate_out)  # 147 for 22050 -> 24000: lengths in whole steps map exactly
    step_out = rate_out // gcd(rate_in, rate_out)
    pad = step_in * max(1, (rate_in // 20) // step_in)
    tail = pad + (-(audio.size + 2 * pad)) % step_in
    padded = np.concatenate([np.zeros(pad, "float32"), audio.astype("float32"), np.zeros(tail, "float32")])
    n_in = padded.size
    n_out = n_in // step_in * step_out
    spectrum = np.fft.rfft(padded)
    bins = n_out // 2 + 1
    if bins <= spectrum.size:
        spectrum = spectrum[:bins]
    else:
        spectrum = np.concatenate([spectrum, np.zeros(bins - spectrum.size, spectrum.dtype)])
    out = np.fft.irfft(spectrum, n=n_out) * (n_out / n_in)
    cut = pad // step_in * step_out
    return out[cut:cut + int(round(audio.size * rate_out / rate_in))].astype("float32")


def _match_level(samples: np.ndarray) -> np.ndarray:
    """Even out the loudness gap between the Hebrew and the English model.

    The English model comes out around 0.65-0.78 peak and the Hebrew one
    around 0.90, which is an audible step at a switch. Gain is clamped so
    levelling can never push a run into clipping.
    """
    if not samples.size:
        return samples
    peak = float(np.abs(samples).max())
    if peak < 1e-4:
        return samples
    gain = min(max(PEAK_TARGET / peak, MIN_GAIN), MAX_GAIN)
    return samples * gain


class Engine:
    """Loads every model once, lazily, and voices each run in its own language."""

    def __init__(self) -> None:
        # Re-entrant: ensure_loaded() calls load_phonemizers() while holding it.
        self._lock = threading.RLock()
        self._loaded = False
        self._renikud = None
        self._espeak = None
        self._letters: dict[str, str] = {}
        self._piper = None
        self._ids: dict[str, list[int]] = {}
        self._scales = (0.667, 0.8)
        self._piper_rate = 22050
        self.sample_rate = SAMPLE_RATE

    def ensure_loaded(self, on_status=None) -> None:
        with self._lock:
            if self._loaded:
                return
            missing = [
                p.name
                for p in (PIPER_MODEL, PIPER_CONFIG, RENIKUD_MODEL)
                if not p.exists()
            ]
            if missing:
                raise FileNotFoundError(
                    "חסרים קבצי מודל בתיקיית models: " + ", ".join(missing)
                )
            if on_status:
                on_status("טוען מודלים, רק בפעם הראשונה...")

            self.load_phonemizers()
            import json
            import os

            import onnxruntime as ort

            config = json.loads(PIPER_CONFIG.read_text(encoding="utf-8"))
            self._ids = config["phoneme_id_map"]
            inference = config.get("inference", {})
            self._scales = (float(inference.get("noise_scale", 0.667)), float(inference.get("noise_w", 0.8)))
            self._piper_rate = int(config["audio"]["sample_rate"])
            options = ort.SessionOptions()
            options.intra_op_num_threads = max(1, min(os.cpu_count() or 4, 8))
            self._piper = ort.InferenceSession(str(PIPER_MODEL), options, providers=["CPUExecutionProvider"])
            self._loaded = True

    def load_phonemizers(self) -> None:
        """Only the text-to-phoneme part: ReNikud and espeak (the reading layer is hebrew_text.py).

        The ZipVoice engine reuses this, so every voice pronounces text the same
        way without loading the Piper model it does not need.
        """
        with self._lock:
            if self._renikud is not None:
                return
            if not RENIKUD_MODEL.exists():
                raise FileNotFoundError(
                    "חסרים קבצי מודל בתיקיית models: " + RENIKUD_MODEL.name
                )
            import espeakng_loader
            from phonemizer.backend.espeak.wrapper import EspeakWrapper

            EspeakWrapper.set_library(espeakng_loader.get_library_path())
            EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
            from phonemizer.backend import EspeakBackend
            from renikud_onnx import G2P

            self._espeak = EspeakBackend(
                "en-us", preserve_punctuation=True, with_stress=True
            )
            self._renikud = G2P(str(RENIKUD_MODEL))

    def plan_phonemes(self, text: str) -> list[dict]:
        """The phoneme plan for a text, for engines that render it themselves."""
        self.load_phonemizers()
        return self._plan(text)

    # ---------- phonemization ----------

    def _hebrew_phonemes(self, text: str) -> str:
        # The reading layer (hebrew_text.py) settles everything the G2P cannot: numbers in the gender of what
        # they count, dates, abbreviations, the lexicon, and words written with nikud (which ReNikud itself
        # cannot read). What it settles arrives as IPA, which ReNikud passes through untouched.
        return self._renikud.phonemize(hebrew_text.prepare(text))

    def _letter(self, character: str) -> str:
        if character not in self._letters:
            word = _LETTER_WORDS.get(character)
            self._letters[character] = (
                self._espeak.phonemize([word])[0].strip() if word else ""
            )
        return self._letters[character]

    def _spell(self, token: str) -> str:
        return " ".join(p for p in (self._letter(c) for c in token) if p)

    def _english_phonemes(self, text: str) -> str:
        """Phonemize English, spelling out anything written in capitals."""
        out: list[str] = []
        plain: list[str] = []

        def flush() -> None:
            if plain:
                out.append(self._espeak.phonemize([" ".join(plain)])[0].strip())
                plain.clear()

        for token in text.split():
            core = token.strip(_EDGE_PUNCT)
            if core and _is_acronym(core):
                flush()
                trailing = token[len(token.rstrip(_EDGE_PUNCT)) :]
                out.append(self._spell(core) + trailing)
            else:
                plain.append(token)
        flush()
        return " ".join(p for p in out if p).strip()

    def phonemize_run(self, script: str, text: str) -> str:
        if script == "he":
            return self._hebrew_phonemes(text)
        return self._english_phonemes(text)

    # ---------- synthesis ----------

    def _phoneme_ids(self, phonemes: str) -> list[int]:
        """Piper's phonemes_to_ids: BOS, then every phoneme followed by the pad, then EOS. Unknown symbols are dropped."""
        ids = self._ids
        out = list(ids["^"]) + list(ids["_"])
        for char in phonemes:
            if char in ids:
                out.extend(ids[char])
                out.extend(ids["_"])
        out.extend(ids["$"])
        return out

    def _render(self, script: str, phonemes: str, speed: float) -> np.ndarray:
        """One Piper call; the 22.05 kHz output is resampled to the app's 24 kHz."""
        ids = self._phoneme_ids(phonemes)
        if len(ids) <= 3:
            return np.zeros(0, dtype="float32")
        noise, noise_w = self._scales
        feeds = {
            "input": np.array([ids], dtype=np.int64),
            "input_lengths": np.array([len(ids)], dtype=np.int64),
            "scales": np.array([noise, 1.0 / max(speed, 0.1), noise_w], dtype=np.float32),
        }
        if any(i.name == "sid" for i in self._piper.get_inputs()):
            feeds["sid"] = np.array([SPEAKERS[script]], dtype=np.int64)
        audio = np.asarray(self._piper.run(None, feeds)[0], dtype="float32").reshape(-1)
        if self._piper_rate != SAMPLE_RATE:
            audio = resample(audio, self._piper_rate, SAMPLE_RATE)
        return audio

    def _plan(self, text: str) -> list[dict]:
        """Split into runs, phonemize each in its own language, fold tiny ones."""
        items: list[dict] = []
        for script, chunk in split_by_script(text):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                phonemes = self.phonemize_run(script, chunk)
            except Exception:
                continue
            if not phonemes.strip():
                continue
            weight = _phoneme_weight(phonemes)
            items.append(
                {
                    "script": script,
                    # which language each end of the run speaks, so a later
                    # merge knows where the seams really are
                    "head": script,
                    "tail": script,
                    # how much speech each language contributes, used to pick
                    # the model once runs start folding into each other
                    "spoken": {
                        "he": weight if script == "he" else 0,
                        "en": weight if script == "en" else 0,
                    },
                    "text": chunk,
                    "parts": [
                        {"script": script, "phonemes": phonemes, "separator": " "}
                    ],
                }
            )
        return _merge_short_runs(items)

    def synthesize(self, text: str, speed: float):
        """Voice each run with its language's model and weld what is left.

        Returns (samples, sample_rate, spans), where spans carries one
        (word, start_seconds, end_seconds) entry per spoken word so the caller
        can follow along on screen.
        """
        gap = np.zeros(int(SAMPLE_RATE * JOIN_GAP), dtype="float32")
        segments: list[np.ndarray] = []
        spans: list[tuple[str, float, float]] = []
        cursor = 0  # samples written so far

        plan = self._plan(text)
        for position, item in enumerate(plan):
            rendered = self._render(item["script"], _render_phonemes(item), speed)
            audio = _soften_edges(
                _match_level(_trim(rendered)), closing=position == len(plan) - 1
            )
            if not audio.size:
                continue
            if segments:
                segments.append(gap)
                cursor += len(gap)
            segments.append(audio)
            spans.extend(_word_spans(item["text"], cursor, len(audio)))
            cursor += len(audio)

        if not segments:
            return None, SAMPLE_RATE, []
        return np.concatenate(segments), SAMPLE_RATE, spans


def _word_spans(
    text: str, offset_samples: int, length_samples: int
) -> list[tuple[str, float, float]]:
    """Spread a run's duration over its words, weighted by how long each is.

    The models do not report alignment, so this is an estimate - close enough
    to keep a highlight travelling with the voice.
    """
    words = [w for w in text.split() if w.strip(_EDGE_PUNCT)]
    if not words:
        return []
    weights = np.array([len(w.strip(_EDGE_PUNCT)) + 1 for w in words], dtype="float64")
    edges = np.concatenate([[0.0], np.cumsum(weights / weights.sum())])
    spans = []
    for index, word in enumerate(words):
        start = (offset_samples + edges[index] * length_samples) / SAMPLE_RATE
        end = (offset_samples + edges[index + 1] * length_samples) / SAMPLE_RATE
        spans.append((word.strip(_EDGE_PUNCT), start, end))
    return spans
