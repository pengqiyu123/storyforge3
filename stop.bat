@echo off
echo [StoryForge3] Stopping dev server...

REM Kill processes by port (kills the full process tree, including uvicorn workers)
REM Port 8000 = backend API, Port 5173 = frontend Vite dev server
for %%P in (8000 5173) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%P " ^| findstr "LISTENING"') do (
        taskkill /PID %%a /T /F >nul 2>&1
    )
)

REM Also kill the storyforge3 dev entrypoint if still running
taskkill /F /IM storyforge3.exe >nul 2>&1

echo [StoryForge3] Done.
ping -n 3 127.0.0.1 >nul
