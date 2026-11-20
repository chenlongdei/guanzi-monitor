@echo off
chcp 65001 >nul
setlocal EnableExtensions
title 观自行深监控台
echo 观自行深监控台：这个窗口请保持打开（可以最小化），关掉窗口监控台就停了。
echo.
set "SKILL=%~dp0"
if "%SKILL:~-1%"=="\" set "SKILL=%SKILL:~0,-1%"
if defined GM_HOME (set "GM=%GM_HOME%") else (set "GM=%USERPROFILE%\.guanzi-monitor")
set "VENV=%GM%\venv"
set "APP=%VENV%\Scripts\guanzi-monitor.exe"
if not defined UV_DEFAULT_INDEX set "UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/"
if not defined UV_PYTHON_INSTALL_MIRROR set "UV_PYTHON_INSTALL_MIRROR=https://registry.npmmirror.com/-/binary/python-build-standalone"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
if not exist "%GM%" mkdir "%GM%"
if not exist "%SKILL%\backend\pyproject.toml" (echo 文件夹不完整：找不到 backend\pyproject.toml & goto fail)

rem 可编辑安装：git pull 后直接生效；依赖变了或文件夹挪了才重装
if not exist "%APP%" goto install
set "OLD="
if exist "%GM%\installed.path" set /p OLD=<"%GM%\installed.path"
if not "%OLD%"=="%SKILL%" goto install
fc /b "%SKILL%\backend\pyproject.toml" "%GM%\installed.pyproject" >nul 2>nul || goto install
goto run

:install
where uv >nul 2>nul
if errorlevel 1 (
  echo 正在安装 uv（Python 环境管理工具）...
  powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
)
where uv >nul 2>nul
if errorlevel 1 py -m pip install --user -q -i https://mirrors.aliyun.com/pypi/simple/ uv
where uv >nul 2>nul
if errorlevel 1 (echo uv 安装失败，请检查网络 & goto fail)
echo 正在安装（第一次约 1-2 分钟）...
if not exist "%VENV%\Scripts\python.exe" (uv venv -q --python 3.11 "%VENV%" || goto fail)
uv pip install -q --python "%VENV%\Scripts\python.exe" -e "%SKILL%\backend" || goto fail
>"%GM%\installed.path" echo %SKILL%
copy /y "%SKILL%\backend\pyproject.toml" "%GM%\installed.pyproject" >nul
echo 安装完成

:run
"%APP%" %*
echo.
pause
goto :eof

:fail
echo.
echo 安装失败：请把这个窗口截图发给老师，或者把报错发给你的 AI 助手
pause
