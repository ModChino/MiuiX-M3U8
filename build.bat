@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo 请先运行一次 run.bat 完成环境初始化。
    pause & exit /b 1
)
"%PY%" -m pip install pyinstaller -q
REM --onefile：app + PySide6 + extension + 图标 全部塞进一个 exe。
REM tools\ 刻意**不打包** —— ffmpeg 与 N_m3u8DL-RE 加起来 200MB+，单文件每次启动
REM 都要把它们解到临时目录，纯属浪费；而且解包路径每次都变，会把配置里记住的
REM 工具路径搞失效。放 exe 旁边的 tools\ 子目录里，既快又稳。
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name MiuiX-M3U8 ^
  --icon "docs\icon\MiuiX-M3U8.ico" ^
  --add-data "extension;extension" ^
  --add-data "docs\icon;docs\icon" ^
  --collect-submodules app ^
  launcher.py
if errorlevel 1 ( echo [错误] 打包失败。 & pause & exit /b 1 )
if not exist "dist\tools" mkdir "dist\tools"
copy /y "tools\*.exe" "dist\tools\" >nul 2>&1
echo.
echo 打包完成： dist\MiuiX-M3U8.exe
echo 注意：ffmpeg 与 N_m3u8DL-RE **不在 exe 里**，已复制到 dist\tools\。
echo       分发时把 exe 和 tools\ 一起给出去，两者必须同级。
pause
