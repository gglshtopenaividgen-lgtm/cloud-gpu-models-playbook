@echo off
title Browser operator & Multi-Account Hub
echo ============================================================
echo   STARTING ANTIGRAVITY ARGON BRIDGE DAEMON ^& GUI
echo   Port: 9229 (ws://127.0.0.1:9229/ws)
echo ============================================================

cd /d "%~dp0"

echo [1/2] Starting local WebSocket/REST daemon in background...
start /b python server.py > daemon.log 2>&1

timeout /t 2 /nobreak > nul

echo [2/2] Opening Multi-Account Switcher GUI...
python dashboard_gui.py
