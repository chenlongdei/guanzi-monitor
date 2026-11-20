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
rem 依赖源按顺序试：清华 → 阿里云 → 官方（阿里云的 anthropic 同步落后过，不能当唯一的源）
if defined UV_DEFAULT_INDEX (set "INDEXES=%UV_DEFAULT_INDEX%") else (set "INDEXES=https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.aliyun.com/pypi/simple/ https://pypi.org/simple")
set "UV_DEFAULT_INDEX="
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

rem 戳记和 scripts/start.sh 共用：installed.path + installed.pyproject
:install
call :finduv
if not defined UV (
  echo 正在安装 uv（Python 环境管理工具）...
  powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  call :finduv
)
if defined UV goto haveuv
call :findpy
if not defined PY (echo uv 安装失败，也没找到 Python，请检查网络 & goto fail)
for %%I in (%INDEXES%) do if not defined UV (
  "%PY%" -m pip install --user -q -i %%I uv
  call :finduv
)
if not defined UV (echo uv 安装失败，请检查网络 & goto fail)
:haveuv
echo 正在安装（第一次约 1-2 分钟）...
if not exist "%VENV%\Scripts\python.exe" ("%UV%" venv -q --python 3.11 "%VENV%" || goto fail)
set "OK="
for %%I in (%INDEXES%) do if not defined OK (
  "%UV%" pip install -q --python "%VENV%\Scripts\python.exe" --default-index %%I -e "%SKILL%\backend" && set "OK=1"
  if not defined OK echo 依赖源 %%I 装不上，换下一个再试...
)
if not defined OK goto fail
>"%GM%\installed.path" echo %SKILL%
copy /y "%SKILL%\backend\pyproject.toml" "%GM%\installed.pyproject" >nul
if exist "%GM%\installed.stamp" del "%GM%\installed.stamp"
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
goto :eof

rem 找 uv：PATH → %USERPROFILE%\.local\bin → pip --user 装的位置（%APPDATA%\Python\PythonXY\Scripts）
:finduv
set "UV="
for /f "delims=" %%U in ('where uv 2^>nul') do if not defined UV set "UV=%%U"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV for /d %%D in ("%APPDATA%\Python\Python3*") do if exist "%%D\Scripts\uv.exe" set "UV=%%D\Scripts\uv.exe"
goto :eof

rem 找 Python：py → python → python3（纯净 Windows 不一定有 py 启动器）
:findpy
set "PY="
for %%P in (py python python3) do if not defined PY (
  %%P -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>nul && set "PY=%%P"
)
goto :eof
