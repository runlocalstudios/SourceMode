@echo off
rem Same UI, no API calls, no key needed: every "generation" returns a labelled grey image.
cd /d "%~dp0"
set IMAGEGEN_MOCK=1
start "" http://127.0.0.1:8790/
uv run python -m app.main
pause
