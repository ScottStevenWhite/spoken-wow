@echo off
rem Double-click to try the Spoken pause prototype. Needs Python and ffmpeg (see TRY-IT.md).
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 spoken_pause.py %*
) else (
    python spoken_pause.py %*
)
echo.
pause
