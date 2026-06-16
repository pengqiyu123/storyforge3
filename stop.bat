@echo off
echo [StoryForge3] Stopping dev server...
taskkill /F /IM storyforge3.exe 2>nul
taskkill /F /IM uvicorn.exe 2>nul
taskkill /F /IM node.exe /FI "WINDOWTITLE eq *vite*" 2>nul
echo [StoryForge3] Done.
timeout /t 3 >nul
