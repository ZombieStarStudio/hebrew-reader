"""Build HebrewReader: PyInstaller onedir + models beside the exe + licences + a zip.

    .venv\\Scripts\\python.exe tools\\build.py public     -> release\\HebrewReader-1.0.0-win64.zip   (the download)
    .venv\\Scripts\\python.exe tools\\build.py full       -> release\\HebrewReader-1.0.0-win64-with-tair-PRIVATE.zip
                                                          (adds the voice "תאיר"; NOT for publishing, see README)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
SITE = VENV / "Lib" / "site-packages"
VERSION = "1.0.0"

LICENSES = {  # file in the zip's licenses\ folder -> source
    "HebrewReader-GPL-3.0.txt": ROOT / "LICENSE",
    "espeak-ng-GPL-3.0.txt": ROOT / "LICENSE",
    "phonemizer-GPL-3.0.txt": SITE / "phonemizer_fork-3.3.2.dist-info" / "licenses" / "LICENSE",
    "phonikud-CC-BY-4.0.txt": SITE / "phonikud-0.4.1.dist-info" / "licenses" / "LICENSE",
    "onnxruntime-MIT.txt": SITE / "onnxruntime" / "LICENSE",
    "onnxruntime-ThirdPartyNotices.txt": SITE / "onnxruntime" / "ThirdPartyNotices.txt",
    "numpy-BSD.txt": next((SITE).glob("numpy-*.dist-info/licenses/LICENSE.txt")),
    "scipy-BSD.txt": next((SITE).glob("scipy-*.dist-info/LICENSE.txt")),
    "soundfile-BSD.txt": next((SITE).glob("soundfile-*.dist-info/LICENSE")),
    "libsndfile-and-codecs.txt": SITE / "_soundfile_data" / "COPYING",
    "sounddevice-MIT.txt": next((SITE).glob("sounddevice-*.dist-info/licenses/LICENSE")),
    "portaudio-MIT.txt": SITE / "_sounddevice_data" / "portaudio-binaries" / "README.md",
    "num2words-LGPL.txt": next((SITE).glob("num2words-*.dist-info/COPYING")),
    "regex-Apache.txt": next((SITE).glob("regex-*.dist-info/licenses/LICENSE.txt")),
    "python-PSF.txt": Path(sys.base_prefix) / "LICENSE.txt",
    "tcl-tk-BSD.txt": Path(sys.base_prefix) / "tcl" / "tk8.6" / "license.terms",
}
CC_BY = """Creative Commons Attribution 4.0 International (CC BY 4.0)
https://creativecommons.org/licenses/by/4.0/legalcode

{what}
Source: {url}
Used unchanged. Attribution: {credit}
"""


def run(cmd, **kw):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def prune(app: Path) -> None:
    """Drop what the app never loads: every eSpeak language but English, 32-bit/ARM/ASIO PortAudio builds."""
    internal = app / "_internal"
    data = internal / "espeakng_loader" / "espeak-ng-data"
    for f in data.glob("*_dict"):
        if f.name != "en_dict":
            f.unlink()
    locales = internal / "babel" / "locale-data"  # csvw imports babel; only these locales can ever be asked for
    for f in locales.glob("*.dat"):
        if not (f.stem in ("root", "en", "he") or f.stem.startswith(("en_", "he_"))):
            f.unlink()
    pa = internal / "_sounddevice_data" / "portaudio-binaries"
    for f in pa.glob("*.dll"):
        if f.name != "libportaudio64bit.dll":
            f.unlink()
    for f in pa.glob("*.dylib"):
        f.unlink()


def add_files(app: Path, flavor: str) -> None:
    models = app / "models"
    (models / "piper").mkdir(parents=True, exist_ok=True)
    for name in ("he_IL-noa-medium.onnx", "he_IL-noa-medium.onnx.json"):
        shutil.copy2(ROOT / "models" / "piper" / name, models / "piper" / name)
    shutil.copy2(ROOT / "models" / "renikud.onnx", models / "renikud.onnx")
    shutil.copy2(ROOT / "lexicon.txt", app / "lexicon.txt")
    shutil.copy2(ROOT / "CREDITS.txt", app / "CREDITS.txt")
    shutil.copy2(ROOT / "LICENSE", app / "LICENSE.txt")
    shutil.copy2(ROOT / "icon.ico", app / "icon.ico")
    lic = app / "licenses"
    lic.mkdir(exist_ok=True)
    for name, src in LICENSES.items():
        if flavor == "public" and name.startswith("scipy"):
            continue  # not in the public build
        shutil.copy2(src, lic / name)
    (lic / "piper-he-noa-CC-BY-4.0.txt").write_text(CC_BY.format(
        what="Piper Hebrew - noa (medium), models/piper/he_IL-noa-medium.onnx",
        url="https://huggingface.co/thewh1teagle/piper-he-noa", credit="thewh1teagle"), encoding="utf-8")
    (lic / "renikud-CC-BY-4.0.txt").write_text(CC_BY.format(
        what="ReNikud, models/renikud.onnx", url="https://huggingface.co/renikud/renikud",
        credit="Maxim Melichov, Yakov Kolani, Morris Alper"), encoding="utf-8")
    (app / "SOURCE.txt").write_text(
        "HebrewReader is free software under the GNU GPL v3 or later (LICENSE.txt).\n"
        "Complete source code: https://github.com/ZombieStarStudio/hebrew-reader (PLACEHOLDER until published)\n"
        "eSpeak NG source: https://github.com/espeak-ng/espeak-ng\n"
        "phonemizer source: https://github.com/bootphon/phonemizer\n", encoding="utf-8")
    if flavor == "full":
        zdir = models / "zipvoice"
        zdir.mkdir(exist_ok=True)
        for name in ("text_encoder_int8.onnx", "fm_decoder_int8.onnx", "model.json", "tokens.txt", "vocos_24khz.onnx"):
            shutil.copy2(ROOT / "models" / "zipvoice" / name, zdir / name)
        (app / "voices").mkdir(exist_ok=True)
        for name in ("tair.wav", "tair.txt"):
            shutil.copy2(ROOT / "voices" / name, app / "voices" / name)
        (app / "PRIVATE-NOT-FOR-PUBLISHING.txt").write_text(
            "This build holds the voice 'תאיר' (ZipVoice Hebrew checkpoint of unknown licence and vendored code without "
            "a licence). For Tair's own PC only. Do not upload it.\n", encoding="utf-8")


def folder_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def main() -> None:
    flavor = sys.argv[1] if len(sys.argv) > 1 else "public"
    assert flavor in ("public", "full")
    build, dist = ROOT / "build" / flavor, ROOT / "dist" / flavor
    env = dict(os.environ, HR_FLAVOR=flavor)
    run([str(VENV / "Scripts" / "pyinstaller.exe"), "--noconfirm", "--clean", "--log-level", "WARN",
         "--workpath", str(build), "--distpath", str(dist), str(ROOT / "HebrewReader.spec")], cwd=ROOT, env=env)
    app = dist / "HebrewReader"
    prune(app)
    add_files(app, flavor)
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    name = f"HebrewReader-{VERSION}-win64" + ("" if flavor == "public" else "-with-tair-PRIVATE") + ".zip"
    target = release / name
    if target.exists():
        target.unlink()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(app.rglob("*")):
            if f.is_file():
                z.write(f, Path("HebrewReader") / f.relative_to(app))
    info = {"flavor": flavor, "folder_mb": round(folder_size(app) / 1e6, 1), "zip": str(target),
            "zip_mb": round(target.stat().st_size / 1e6, 1)}
    print(json.dumps(info, ensure_ascii=False))
    print("BUILD_DONE")


if __name__ == "__main__":
    main()
