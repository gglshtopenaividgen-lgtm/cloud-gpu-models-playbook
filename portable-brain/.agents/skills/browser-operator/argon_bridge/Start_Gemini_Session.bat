@echo off
title Antigravity Gemini Session Host (WinSta0\Default)
echo ============================================================================
echo  ANTIGRAVITY GEMINI SESSION HOST (Interactive Desktop: WinSta0\Default)
echo  Powers multi-profile Argon/Neon automation + hands-free .lnk rotation
echo ============================================================================
echo.

set "BRIDGE_DIR=./.agents\skills\browser-operator\argon_bridge"

echo [1/4] Stopping any previous bridge daemon on 127.0.0.1:9229...
python -c "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:9229/shutdown', method='POST', data=b'{}'), timeout=2)" >nul 2>&1
timeout /t 1 /nobreak >nul
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr /R "127\.0\.0\.1:9229.*LISTENING"') do (
    echo [1/4] Releasing port 9229 from stale PID %%P...
    taskkill /PID %%P /F >nul 2>&1
)

echo [2/4] Refreshing Chrome profile .lnk shortcuts...
python "%BRIDGE_DIR%\profile_rotator.py" generate-shortcuts >nul

echo [3/4] Starting Argon Bridge daemon on http://127.0.0.1:9229 ...
echo       Keep this window open (you can minimize it) while Antigravity runs.
echo.
python "%BRIDGE_DIR%\server.py"

echo.
echo [Bridge exited unexpectedly] Review the error above before closing.
pause
