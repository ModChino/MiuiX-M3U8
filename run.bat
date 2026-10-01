@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
set "PYW=.venv\Scripts\pythonw.exe"

if not exist "%PY%" goto setup
"%PY%" -c "import PySide6" >nul 2>&1 || goto setup
start "" "%PYW%" -m app.main
exit /b 0

:setup
echo [MiuiX M3U8] 首次运行：创建虚拟环境并安装依赖，请稍候...
py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv 2>nul
if not exist "%PY%" (
    echo [错误] 未找到 Python 3.11+。请先安装 Python 并勾选 "Add Python to PATH"。
    pause & exit /b 1
)
"%PY%" -m pip install --upgrade pip -q
"%PY%" -m pip install -r requirements.txt || (
    echo [错误] 依赖安装失败，请检查网络后重试。
    pause & exit /b 1
)
if not exist "tools\N_m3u8DL-RE.exe" echo [提示] tools\ 下没有 N_m3u8DL-RE.exe，可在设置页指定路径，或运行 tools\get-tools.bat 自动下载。
start "" "%PYW%" -m app.main
exit /b 0
