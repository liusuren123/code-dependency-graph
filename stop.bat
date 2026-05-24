@echo off
chcp 65001 >nul
echo 正在停止服务...

:: 停止uvicorn进程
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM uvicorn.exe >nul 2>&1

echo 服务已停止
pause