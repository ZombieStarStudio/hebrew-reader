@echo off
rem Builds HebrewReader (9.11.2026). public = the download (basic voice only); full = with the voice "תאיר", PRIVATE.
cd /d "%~dp0"
.venv\Scripts\python.exe -X utf8 tools\make_icon.py || exit /b 1
.venv\Scripts\python.exe -X utf8 tools\build.py %1 || exit /b 2
echo BUILD_DONE
