@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  MiuiX M3U8 外部工具自动下载 (Windows x64)
echo ============================================

echo.
echo [1/2] 下载 N_m3u8DL-RE v0.6.0-beta ...
if exist "N_m3u8DL-RE.exe" ( echo     已存在，跳过。 ) else (
    curl -L --retry 3 -o nm.zip "https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.6.0-beta/N_m3u8DL-RE_v0.6.0-beta_win-x64_20260629.zip"
    if errorlevel 1 ( echo     [失败] 请手动下载后放入本目录。 ) else (
        powershell -NoProfile -Command "Expand-Archive -Force -Path nm.zip -DestinationPath ." && del nm.zip
    )
)

echo.
echo [2/2] 下载 ffmpeg (essentials build, 约 80MB) ...
if exist "ffmpeg.exe" ( echo     已存在，跳过。 ) else (
    curl -L --retry 3 -o ff.zip "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    if errorlevel 1 ( echo     [失败] 请手动下载 ffmpeg.exe 后放入本目录。 ) else (
        powershell -NoProfile -Command "Expand-Archive -Force -Path ff.zip -DestinationPath ff-tmp; Get-ChildItem -Path ff-tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1 | Copy-Item -Destination . -Force; Get-ChildItem -Path ff-tmp -Recurse -Filter ffprobe.exe | Select-Object -First 1 | Copy-Item -Destination . -Force"
        rmdir /s /q ff-tmp
        del ff.zip
    )
)

echo.
echo 完成。当前 tools\ 目录：
dir /b
echo.
echo 可选：mp4decrypt.exe（解密需要） https://www.bok.net/Bento4/binaries/
pause
