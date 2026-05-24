@echo off
chcp 65001 >nul
echo ========================================
echo   Code Dependency Graph 停止脚本
echo ========================================
echo.

echo [停止] 正在停止 Python 服务...
taskkill /F /IM python.exe >nul 2>&1

echo [完成] 服务已停止
echo.
pause
