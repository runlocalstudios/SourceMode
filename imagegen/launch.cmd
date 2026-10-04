@echo off
rem imagegen - local character photo generation through the OpenAI Images API.
rem Double-click to start. Set IMAGEGEN_MOCK=1 first to run without any API calls.
cd /d "%~dp0"
if not exist ".env" if "%OPENAI_API_KEY%"=="" (
  echo No .env and no OPENAI_API_KEY in the environment. See README.md - or set IMAGEGEN_MOCK=1 to try the UI.
)
start "" http://127.0.0.1:8790/
uv run python -m app.main
pause
