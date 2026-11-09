"""One-time conversion of engine.py from StyleTTS2 (libritts_*.onnx, unknown licence) to Piper noa (CC BY 4.0), 9.11.2026."""
import io
from pathlib import Path

f = Path(__file__).resolve().parent.parent / "engine.py"
s = io.open(f, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:90]
    s = s.replace(a, b)


rep('''Every run of text is voiced by the model that matches its own script, so
Hebrew is never spoken with an American accent and English is never spoken
with an Israeli one. Both models share a single style vector, which keeps the
speaker identity stable across a language switch.

Audio is pulled straight out of the ONNX session rather than through
StyleTTS2.create(), because that helper fades the last 250ms of every phrase
to silence. That fade is meant for a whole utterance; applied to a two-word
run it swallows the end of the word and the joins sound like choking.
''', '''HebrewReader's basic voice is Piper "noa" (thewh1teagle/piper-he-noa, CC BY 4.0): one VITS model with two
speakers, noa (Hebrew, trained on renikud's stressed IPA) and ljspeech (English, public-domain LJSpeech). A Hebrew run
is read by noa, a whole English run by ljspeech, so English words keep a native accent. HebrewSpeaker used two StyleTTS2
models here; their origin and licence could not be verified (business/legal/hebrew-reader-licenses.md), so they are
not shipped. The run splitting, merging and seams below are HebrewSpeaker's, unchanged.
''')
rep('''HEBREW_MODEL = MODELS_DIR / "libritts_hebrew.onnx"
ENGLISH_MODEL = MODELS_DIR / "libritts_english.onnx"
RENIKUD_MODEL = MODELS_DIR / "renikud.onnx"
VOICE_STYLE = MODELS_DIR / "707_male_style.npy"  # measurably the most stable of the four
''', '''PIPER_MODEL = MODELS_DIR / "piper" / "he_IL-noa-medium.onnx"
PIPER_CONFIG = MODELS_DIR / "piper" / "he_IL-noa-medium.onnx.json"
RENIKUD_MODEL = MODELS_DIR / "renikud.onnx"
SPEAKERS = {"he": 0, "en": 1}  # noa, ljspeech (speaker_id_map in the config)
''')
rep('''        self._voices: dict[str, object] = {}
        self.sample_rate = SAMPLE_RATE''', '''        self._piper = None
        self._ids: dict[str, list[int]] = {}
        self._scales = (0.667, 0.8)
        self._piper_rate = 22050
        self.sample_rate = SAMPLE_RATE''')
rep('''                for p in (HEBREW_MODEL, ENGLISH_MODEL, RENIKUD_MODEL, VOICE_STYLE)''', '''                for p in (PIPER_MODEL, PIPER_CONFIG, RENIKUD_MODEL)''')
rep('''            from style_onnx import StyleTTS2

            self._voices = {
                "he": StyleTTS2(str(HEBREW_MODEL), str(VOICE_STYLE)),
                "en": StyleTTS2(str(ENGLISH_MODEL), str(VOICE_STYLE)),
            }
            self._loaded = True''', '''            import json
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
            self._loaded = True''')
rep('''        way without loading the StyleTTS2 models it does not need.''', '''        way without loading the Piper model it does not need.''')
start = s.index('    def _render(self, script: str, phonemes: str, speed: float) -> np.ndarray:')
end = s.index('    def _plan(self, text: str)')
s = s[:start] + '''    def _phoneme_ids(self, phonemes: str) -> list[int]:
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
            from math import gcd

            from scipy.signal import resample_poly

            g = gcd(self._piper_rate, SAMPLE_RATE)
            audio = resample_poly(audio, SAMPLE_RATE // g, self._piper_rate // g).astype("float32")
        return audio

''' + s[end:]
s = s.replace("StyleTTS2 stretches and smears an utterance it considers too short", "The TTS model stretches and smears an utterance it considers too short (measured on StyleTTS2)")
io.open(f, "w", encoding="utf-8", newline="").write(s)
print("engine.py -> piper")
