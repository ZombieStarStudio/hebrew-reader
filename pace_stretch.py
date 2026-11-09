# -*- coding: utf-8 -*-
"""
Drop-in replacement for zip_engine.timescale(samples, rate, factor).

    from pace_stretch import timescale            # same signature: float32 mono in, float32 mono out, same rate

What is different from the reader's overlap-add (each point is measured in README.md):
  1. The input is padded with zeros, so the loop reads the REAL end of the chunk; the output is exactly
     round(len/factor) samples and ends in a raised-cosine fade to zero. (The reader stopped reading early and its
     weight normalisation un-faded the last half window, so every chunk ended mid-sound: a click, and a lost word.)
  2. Every window is searched around its IDEAL place (output position x factor). The reader searched around the
     previous nudged place, so the nudges added up and the input was not consumed at exactly `factor`.
  3. Each window is placed by NORMALISED cross-correlation, tried at every sample. (The reader used a raw dot
     product, which prefers loud candidates over matching ones, on every 4th sample only.)
  4. compensate=True: the cross-fade between two windows is corrected for how well they really match. A pair that
     lines up (voiced speech) is summed as before; a pair that does not (fricatives, breath) is summed
     power-complementary. A plain overlap-add loses up to 3 dB in the middle of every such cross-fade, once per
     synthesis hop, and that is a steady line (50 Hz for a 20 ms hop) in the loudness envelope.
     split_hz: the match is judged separately below and above that frequency. The strong low band decides where a
     window goes, so in a voiced sound the hiss on top of it can still be joined out of step; judged alone it
     gets its own correction. (Measured: the last 1.7 dB hop line in the 4-11 kHz band disappears.)
     peak_cap: the correction never lifts a cross-fade above the louder of its two pieces, so the chunk peak does
     not grow and level() leaves the chunk loudness alone.
  5. window_ms, search_ms and a random hop jitter are parameters, for the experiment arms.

Dependency: numpy only. Deterministic (the jitter generator is seeded from the input length). No GPU.
"""
from __future__ import annotations

import numpy as np

__all__ = ["timescale", "timescale_ola", "fade_edges", "level", "enhance"]

PEAK = 0.95


def fade_edges(samples: np.ndarray, rate: int, fade_in_ms: float = 3.0, fade_out_ms: float = 10.0) -> np.ndarray:
    """Raised-cosine fade at both ends, so a chunk can never start or stop on a step."""
    out = np.array(samples, dtype="float32", copy=True)
    count = min(int(rate * fade_in_ms / 1000.0), len(out) // 2)
    if count > 1:
        out[:count] *= (0.5 - 0.5 * np.cos(np.pi * np.arange(count) / count)).astype("float32")
    count = min(int(rate * fade_out_ms / 1000.0), len(out) // 2)
    if count > 1:
        out[-count:] *= (0.5 + 0.5 * np.cos(np.pi * (np.arange(count) + 1) / count)).astype("float32")
    return out


def _lowpass(samples: np.ndarray, rate: int, hz: float) -> np.ndarray:
    """Zero-phase windowed-sinc low-pass (about 4 ms long), numpy only."""
    taps = int(rate * 0.004) // 2 * 2 + 1
    n = np.arange(taps) - taps // 2
    kernel = np.sinc(2.0 * hz / rate * n) * np.hanning(taps + 2)[1:-1]
    return np.convolve(samples, (kernel / kernel.sum()).astype("float32"), mode="same").astype("float32")


def timescale_ola(samples: np.ndarray, rate: int, factor: float, *, window_ms: float = 40.0, search_ms: float = 8.0,
                  step: int = 1, normalised: bool = True, compensate: bool = False, peak_cap: bool = True,
                  split_hz: float = 0.0, jitter: float = 0.0, fade_in_ms: float = 3.0,
                  fade_out_ms: float = 10.0) -> np.ndarray:
    """Waveform-similarity overlap-add with a flushed, faded tail. See the module docstring.

    Layout: the output is a chain of cross-fades of length `overlap`; between two cross-fades the input is copied
    as it is for (hop - overlap) samples. Without jitter hop == overlap == window/2, which is the classic
    50 %-overlap Hann scheme of the reader."""
    samples = np.asarray(samples, dtype="float32").reshape(-1)
    if abs(factor - 1.0) < 0.01 or samples.size < rate // 4:
        return fade_edges(samples, rate, fade_in_ms, fade_out_ms)
    half = int(window_ms / 1000.0 * rate) // 2
    search = int(search_ms / 1000.0 * rate)
    target = int(round(len(samples) / factor))
    spread = int(round(half * jitter))
    overlap = half - spread                                  # cross-fade length; hop is overlap .. overlap + 2*spread
    max_hop = overlap + 2 * spread
    padded = np.concatenate([samples, np.zeros(search + overlap + 2 * max_hop + 8, dtype="float32")])
    limit = len(padded) - overlap - max_hop
    energy = np.concatenate([[0.0], np.cumsum(padded.astype("float64") ** 2)]) if normalised else None
    ramp = (np.arange(overlap, dtype="float32") + 0.5) / overlap
    rise = (0.5 - 0.5 * np.cos(np.pi * ramp)).astype("float32")           # rise + fall == 1 exactly
    fall = (1.0 - rise).astype("float32")
    cross, squares = 2.0 * rise * fall, rise ** 2 + fall ** 2
    rng = np.random.default_rng(len(samples)) if spread else None
    bands = [padded]
    if compensate and split_hz and split_hz < 0.45 * rate:
        low = _lowpass(padded, rate, split_hz)
        bands = [low, padded - low]                           # the two always add up to the signal itself

    def next_hop() -> int:
        return overlap + (int(rng.integers(0, 2 * spread + 1)) if rng is not None else 0)

    out = np.zeros(target + overlap + max_hop, dtype="float32")
    hop = next_hop()
    out[:hop] = padded[:hop]
    read, write = 0, hop
    # Output position -> ideal input position. Both ENDS are anchored: output 0 reads input 0 and the last piece
    # reads the last piece of the input. (With a plain `write * factor` the final half window of the input,
    # about 20 ms at 2.05, would never be played.)
    slope = (len(samples) - half) / max(1.0, float(target - half))
    while write < target:
        read_old = read + hop
        template = padded[read_old:read_old + overlap]       # what would follow naturally: the new window must match it
        centre = min(int(round(write * slope)), limit)
        start, stop = max(0, centre - search), min(limit, centre + search)
        scores = np.correlate(padded[start:stop + overlap], template, mode="valid")[::step]
        if normalised:
            starts = np.arange(start, stop + 1, step)
            scores = scores / np.sqrt(np.maximum(energy[starts + overlap] - energy[starts], 1e-9))
        best = int(np.argmax(scores))
        read = start + best * step if scores[best] > 0.0 else centre
        incoming = padded[read:read + overlap]
        mixed = template * fall + incoming * rise
        if compensate:
            lifted = np.zeros_like(mixed)
            for band in bands:                                # one band, or low + high judged separately
                old, new = band[read_old:read_old + overlap], band[read:read + overlap]
                part = old * fall + new * rise
                e_old, e_new = float(np.dot(old, old)), float(np.dot(new, new))
                if e_old > 1e-9 and e_new > 1e-9:
                    rho = min(max(float(np.dot(old, new)) / float(np.sqrt(e_old * e_new)), 0.0), 1.0)
                    part = part / np.sqrt(squares + rho * cross)          # rho=1: unchanged; rho=0: equal power
                lifted += part
            if peak_cap:
                # never louder than the louder of the two pieces being joined: a lifted vowel peak would make
                # level() turn the whole chunk down, and chunks would stop being equally loud
                ceiling = max(float(np.max(np.abs(template))), float(np.max(np.abs(incoming))))
                top, plain_top = float(np.max(np.abs(lifted))), float(np.max(np.abs(mixed)))
                if top > ceiling and top > plain_top:
                    lifted = mixed + (lifted - mixed) * max(0.0, (ceiling - plain_top) / (top - plain_top))
            mixed = lifted
        out[write:write + overlap] = mixed
        hop = next_hop()
        out[write + overlap:write + hop] = padded[read + overlap:read + hop]
        write += hop
    return fade_edges(out[:target], rate, fade_in_ms, fade_out_ms)


def timescale(samples: np.ndarray, rate: int, factor: float) -> np.ndarray:
    """Same signature as zip_engine.timescale. The settings are the arm that won the measurements (OLA4 in
    README.md): 30 ms windows, +/-8 ms normalised search at every sample, match-compensated cross-fade judged
    separately below and above 3 kHz, with the peak cap, 3 ms fade-in, 30 ms fade-out.
    At factor 1.0 only the two fades are applied."""
    return timescale_ola(samples, rate, factor, window_ms=30.0, search_ms=8.0, step=1, normalised=True,
                         compensate=True, peak_cap=True, split_hz=3000.0, jitter=0.0, fade_in_ms=3.0, fade_out_ms=30.0)


def level(samples: np.ndarray) -> np.ndarray:
    """Same as zip_engine.level: peak to 0.95 only when it is higher."""
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    return samples * (PEAK / peak) if peak > PEAK else samples


def enhance(samples: np.ndarray, rate: int, factor: float = 2.05) -> tuple[np.ndarray, int]:
    """Hub-style entry point: model-pace audio in, listening-pace audio out, levelled like the reader does."""
    return level(timescale(samples, rate, factor)), rate
