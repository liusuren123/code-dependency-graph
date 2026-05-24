@echo off
chcp 65001 >nul
echo ========================================
echo   Code Dependency Graph 构建脚本
echo ========================================
echo.

cd /d "%~dp0.."

echo [1/3] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo   [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)
echo   [OK] Python 已找到

echo.
echo [2/3] 创建必要目录...
if not exist "data" mkdir data
if not exist "logs" mkdir logs
echo   [OK] 目录已创建

echo.
echo [3/3] 安装 Python 依赖...
cd backend
pip install -r requirements.txt -q
if errorlevel 1 (
    echo   [错误] 依赖安装失败
    pause
    exit /b 1
)
cd ..
echo   [OK] Python 依赖已安装

echo.
echo ========================================
echo   构建完成！
echo ========================================
echo.
echo 运行 start.bat 启动服务
pause
