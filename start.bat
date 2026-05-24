@echo off
chcp 65001 >nul
echo ========================================
echo   代码依赖图分析系统 - Windows 启动脚本
echo ========================================
echo.

:: 获取脚本所在目录
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

:: 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.9+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [√] Python 已就绪

:: 检查uv
where uv >nul 2>&1
if errorlevel 1 (
    echo [提示] 未找到uv，正在安装...
    powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set PATH=%USERPROFILE%\.local\bin;%PATH%
)
echo [√] uv 已就绪

:: 检查虚拟环境是否存在
if exist ".venv" (
    echo.
    echo [√] 虚拟环境已存在，跳过创建
) else (
    echo.
    echo [1/4] 创建虚拟环境 .venv ...
    uv venv .venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
)

echo.
echo [2/4] 安装依赖到虚拟环境...
uv pip install --python .venv fastapi uvicorn tree-sitter sqlalchemy pydantic pysqlite3-binary
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo.
echo [3/4] 启动后端服务 (http://localhost:8000)...
echo    按 Ctrl+C 可停止服务
echo.
.venv\Scripts\uvicorn main:app --host 0.0.0.0 --port 8000