@echo off
chcp 65001 >nul
if defined GM_HOME (set "GM=%GM_HOME%") else (set "GM=%USERPROFILE%\.guanzi-monitor")
"%GM%\venv\Scripts\guanzi-monitor.exe" --stop
timeout /t 2 >nul
