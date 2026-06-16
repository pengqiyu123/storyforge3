@echo off
cd /d "%~dp0"
echo [StoryForge3] Starting dev server...
echo   Backend: http://127.0.0.1:8000
echo   Frontend: http://127.0.0.1:5173
echo   Press Ctrl+C to stop.
echo.
.\.venv\Scripts\storyforge3.exe dev
pause
