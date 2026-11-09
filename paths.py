"""Where the app's files live, both from source and as a built HebrewReader.exe.

The build (build.bat) puts models/, voices/ and lexicon.txt beside the exe, not inside PyInstaller's _internal, so a
student can see them and the zip stays a plain folder. From source they sit beside this file.
"""
from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE = Path(sys.executable).resolve().parent
else:
    BASE = Path(__file__).resolve().parent
    vendor = str(BASE / "vendor")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)

MODELS = BASE / "models"
VOICES = BASE / "voices"
LEXICON = BASE / "lexicon.txt"
