@echo off
chcp 65001 >nul
echo ========================================
echo   Code Dependency Graph 启动脚本
echo ========================================
echo.

cd /d "%~dp0.."

REM 检查 Python 是否运行
echo [检查] 清理旧进程...
taskkill /F /IM python.exe >nul 2>&1
timeout /t 1 >nul

REM 创建必要目录
if not exist "data" mkdir data
if not exist "logs" mkdir logs

REM 启动后端服务
echo [启动] 后端服务 (http://localhost:8000)...
cd backend
start "CodeGraph Backend" cmd /c "python main.py"
cd ..

REM 等待服务启动
timeout /t 3 >nul

REM 检查服务是否运行
curl -s http://localhost:8000/docs >nul 2>&1
if errorlevel 1 (
    echo [错误] 后端服务启动失败，请查看 logs/app.log
    pause
    exit /b 1
)

echo.
echo ========================================
echo   服务已启动！
echo ========================================
echo.
echo   前端: http://localhost:8000
echo   API:  http://localhost:8000/docs
echo.
echo   关闭此窗口不会停止服务
echo   使用 stop.bat 停止服务
echo.
pause
