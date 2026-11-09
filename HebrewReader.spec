# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for HebrewReader (onedir). Run through tools\build.py, which sets HR_FLAVOR:
#   public - the download: the basic voice (Piper noa) only; zipvoice_onnx and zip_engine are left out
#   full   - for Tair's own PC: also the voice "תאיר" (ZipVoice). Not for publishing (licence: see README).
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

flavor = os.environ.get("HR_FLAVOR", "public")
excludes = ["librosa", "numba", "llvmlite", "sklearn", "torch", "matplotlib", "pandas", "IPython", "pytest",
            "PIL", "tokenizers", "phonikud_onnx", "style_onnx"]
if flavor == "public":
    excludes += ["zipvoice_onnx", "zip_engine", "pace_stretch", "scipy"]  # scipy is only used by the ZipVoice path

datas = collect_data_files("espeakng_loader") + [("icon.ico", ".")]
datas += collect_data_files("phonemizer") + collect_data_files("segments") + collect_data_files("csvw")
datas += collect_data_files("language_tags")
binaries = collect_dynamic_libs("espeakng_loader")

a = Analysis(
    ["app.py"],
    pathex=["vendor"],
    binaries=binaries,
    datas=datas,
    hiddenimports=[] if flavor == "public" else ["zip_engine", "pace_stretch", "zipvoice_onnx"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HebrewReader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=["icon.ico"],
    version=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="HebrewReader",
)
