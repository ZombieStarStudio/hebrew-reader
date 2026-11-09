"""Measure the voice תאיר on the CPU: real-time factor and Whisper word accuracy (local ASR on port 8768).

    .venv\Scripts\python.exe -X utf8 tools\bench.py [--int8 0|1] [--steps 16] [--threads 4] [--out dir]
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import paths  # noqa: E402,F401

SENTENCES = [
    "הספר הזה מספר על ילדה שגרה ליד הים ואוהבת לאסוף צדפים.",
    "המורה ביקשה מכל התלמידים לקרוא את הפרק השני עד יום ראשון.",
    "כשהשמש שוקעת, השמיים נצבעים בכתום, בוורוד ובסגול.",
    "אנחנו לומדים היום על מחזור המים בטבע ועל העננים.",
    "חשוב לשתות הרבה מים בימים חמים ולנוח בצל.",
]


def norm(s):
    s = re.sub(r"[֑-ׇ]", "", s)
    s = re.sub(r"[^א-תa-zA-Z0-9 ]", " ", s)
    return s.split()


def wer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / max(1, len(r))


def asr(wav_bytes):
    req = urllib.request.Request("http://127.0.0.1:8768/transcribe", data=wav_bytes, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8")).get("text", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--int8", type=int, default=1)
    ap.add_argument("--steps", type=int, default=16)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--engine", default="zip")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    if a.threads:
        os.environ["HR_THREADS"] = str(a.threads)
    import soundfile as sf

    if a.engine == "zip":
        import zip_engine

        zip_engine.QUANTIZED = bool(a.int8)
        zip_engine.NUM_STEPS = a.steps
        eng = zip_engine.ZipEngine()
        t0 = time.time()
        eng.ensure_loaded()
        synth = lambda t: eng.synthesize(t, 1.0)  # noqa: E731
    else:
        import engine

        eng = engine.Engine()
        t0 = time.time()
        eng.ensure_loaded()
        synth = lambda t: eng.synthesize(t, 1.12)  # noqa: E731
    load = time.time() - t0
    out = Path(a.out) if a.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    gen = dur = 0.0
    wers = []
    for i, s in enumerate(SENTENCES):
        t = time.time()
        samples, rate, _ = synth(s)
        gen += time.time() - t
        dur += len(samples) / rate
        buf = io.BytesIO()
        sf.write(buf, samples, rate, format="WAV")
        if out:
            (out / f"s{i}.wav").write_bytes(buf.getvalue())
        try:
            hyp = asr(buf.getvalue())
            wers.append(wer(s, hyp))
            print(f"  {i}: wer {wers[-1]:.2f}  | {hyp}", flush=True)
        except Exception as e:
            print("  asr failed", e)
    print(json.dumps({"engine": a.engine, "int8": a.int8, "steps": a.steps, "threads": os.environ.get("HR_THREADS", "default"),
                      "load_s": round(load, 1), "audio_s": round(dur, 1), "gen_s": round(gen, 1),
                      "sec_per_audio_sec": round(gen / dur, 2), "mean_wer": round(sum(wers) / max(1, len(wers)), 3)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
