@echo off
REM ============================================================
REM  GameDataMonitor — Windows 一键打包脚本
REM  在 Windows 10/11 (x64) 上双击运行,产物输出到 dist\
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

echo.
echo ============================================================
echo  GameDataMonitor Windows 打包
echo ============================================================
echo.

REM ---------- 1. 检查 Node.js ----------
echo [1/5] 检查 Node.js...
where node >nul 2>nul
if errorlevel 1 (
    echo.
    echo [X] 没有检测到 Node.js
    echo     请先安装 Node.js 20 LTS:https://nodejs.org/zh-cn/download
    echo     安装后重新打开命令行窗口再跑本脚本。
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('node --version') do set NODE_VER=%%v
echo     Node.js !NODE_VER! 已安装

REM ---------- 2. 检查 tar(Windows 10 1803+ 自带) ----------
echo.
echo [2/5] 检查 tar.exe...
where tar >nul 2>nul
if errorlevel 1 (
    echo.
    echo [X] 没有检测到 tar.exe
    echo     Windows 10 1803 以上版本自带 tar。请升级 Windows 或手动安装。
    echo.
    pause
    exit /b 1
)
echo     tar 已就绪

REM ---------- 3. 安装 npm 依赖 ----------
echo.
echo [3/5] 安装 npm 依赖 (会自动重编 better-sqlite3 到 Electron ABI)...
echo     这一步如果失败,通常是缺 Visual Studio Build Tools。
echo     解决方法:用管理员开 PowerShell 跑 `npm install --global windows-build-tools`
echo             或下载安装 https://visualstudio.microsoft.com/visual-cpp-build-tools/
echo.
call npm install --no-audit --no-fund
if errorlevel 1 (
    echo.
    echo [X] npm install 失败,请看上面错误输出。
    pause
    exit /b 1
)

REM ---------- 4. 下载嵌入式 Python + 装依赖 ----------
echo.
echo [4/5] 下载 Python runtime 并装依赖 (首次约 40MB + 150MB,需要几分钟)...
call npm run fetch:python
if errorlevel 1 (
    echo [X] fetch:python 失败,请检查网络。
    pause
    exit /b 1
)
call npm run install:py-deps:strip
if errorlevel 1 (
    echo [X] install:py-deps:strip 失败。
    pause
    exit /b 1
)

REM ---------- 5. 打包 .exe ----------
echo.
echo [5/5] 调用 electron-builder 打包 Windows .exe...
call npx electron-builder --win --x64 --publish never
if errorlevel 1 (
    echo.
    echo [X] electron-builder 打包失败,请看上面错误输出。
    pause
    exit /b 1
)

REM ---------- 完成 ----------
echo.
echo ============================================================
echo  打包完成
echo ============================================================
echo.
echo  产物位置:
dir /b dist\*.exe 2>nul
echo.
echo  请用产物 .exe 在另一台干净的 Windows 上测试安装。
echo.
pause
endlocal
