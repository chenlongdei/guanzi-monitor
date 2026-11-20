#!/usr/bin/env bash
# 观自行深监控台 启动脚本（macOS / Linux / Windows Git Bash）
#   start.sh            前台运行（关掉这个窗口，监控台就停了）
#   start.sh --bg       后台运行，启动好后打开浏览器
#   start.sh --status   是否在运行（JSON）
#   start.sh --stop     关闭
#   其他参数原样传给 guanzi-monitor（--demo、--port、--data、--no-browser …）
set -e
SKILL="$(cd "$(dirname "$0")/.." && pwd)"
GM="${GM_HOME:-$HOME/.guanzi-monitor}"
VENV="$GM/venv"
mkdir -p "$GM"

# 国内网络：Python 和依赖都走国内镜像（海外也能用，只是稍慢）
# 依赖源按顺序试：清华 → 阿里云 → 官方。阿里云的 anthropic 同步落后过，不能当唯一的源。
INDEXES="${UV_DEFAULT_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.aliyun.com/pypi/simple/ https://pypi.org/simple}"
unset UV_DEFAULT_INDEX
export UV_PYTHON_INSTALL_MIRROR="${UV_PYTHON_INSTALL_MIRROR:-https://registry.npmmirror.com/-/binary/python-build-standalone}"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

BIN="$VENV/bin"; EXE=""; WIN=0
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) BIN="$VENV/Scripts"; EXE=".exe"; WIN=1;; esac
APP="$BIN/guanzi-monitor$EXE"

BG=0; ARGS=()
for a in "$@"; do
  if [ "$a" = "--bg" ]; then BG=1; else ARGS+=("$a"); fi
done

# 只查状态 / 关闭：没装过就等于没在运行
for a in "${ARGS[@]}"; do
  if [ "$a" = "--status" ] || [ "$a" = "--stop" ]; then
    if [ -x "$APP" ]; then exec "$APP" "${ARGS[@]}"; fi
    if [ "$a" = "--status" ]; then echo '{"running": false, "installed": false}'; else echo "监控台没有在运行"; fi
    exit 0
  fi
done

# 代码是「可编辑安装」：git pull 之后直接生效；只有依赖变了或文件夹挪了才重装
# 戳记和「启动监控台.bat」共用：installed.path（skill 路径，Windows 写法）+ installed.pyproject（依赖清单副本）
SKILL_ID="$SKILL"
[ "$WIN" = 1 ] && command -v cygpath >/dev/null 2>&1 && SKILL_ID="$(cygpath -w "$SKILL")"
need_install() {
  [ -x "$APP" ] || return 0
  [ "$(tr -d '\r' < "$GM/installed.path" 2>/dev/null | sed 's/[[:space:]]*$//')" = "$SKILL_ID" ] || return 0
  cmp -s "$SKILL/backend/pyproject.toml" "$GM/installed.pyproject" || return 0
  return 1
}

find_python() {
  for p in python3 python py; do
    if command -v "$p" >/dev/null 2>&1 && "$p" -c "import sys; sys.exit(sys.version_info < (3, 8))" 2>/dev/null; then
      echo "$p"; return 0
    fi
  done
  return 1
}

# 找 uv：PATH 里的 → 常见安装位置 → pip --user 装的位置（Windows 在 %APPDATA%\Python\PythonXY\Scripts）
find_uv() {
  command -v uv 2>/dev/null && return 0
  for c in "$HOME/.local/bin/uv$EXE" "$HOME/.cargo/bin/uv$EXE"; do
    [ -x "$c" ] && { echo "$c"; return 0; }
  done
  PY="$(find_python)" || return 1
  local ub
  ub="$("$PY" -c "import site; print(site.getuserbase())" 2>/dev/null | tr -d '\r')" || return 1
  [ "$WIN" = 1 ] && command -v cygpath >/dev/null 2>&1 && ub="$(cygpath -u "$ub")"
  for c in "$ub"/Python3*/Scripts/uv.exe "$ub/Scripts/uv.exe" "$ub/bin/uv"; do
    [ -x "$c" ] && { echo "$c"; return 0; }
  done
  return 1
}

install_uv() {
  echo "→ 安装 uv（Python 环境管理工具）…"
  if [ "$WIN" = 1 ]; then
    # Windows 上 install.sh 的校验文件带 CRLF 会校验失败，用官方 PowerShell 安装器（和 .bat 一致）
    powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" || true
  else
    curl -LsSf https://astral.sh/uv/install.sh | sh || true
  fi
  find_uv >/dev/null && return 0
  PY="$(find_python)" || return 1
  for idx in $INDEXES; do
    "$PY" -m pip install --user -q -i "$idx" uv && find_uv >/dev/null && return 0
  done
  return 1
}

if need_install; then
  UV="$(find_uv)" || { install_uv && UV="$(find_uv)"; } || {
    echo "uv 安装失败：请检查网络，或按 references/排错.md 手动安装"; exit 1; }
  echo "→ 正在安装（第一次约 1–2 分钟）…"
  [ -x "$BIN/python$EXE" ] || "$UV" venv -q --python 3.11 "$VENV"
  ok=0
  for idx in $INDEXES; do
    if "$UV" pip install -q --python "$BIN/python$EXE" --default-index "$idx" -e "$SKILL/backend"; then ok=1; break; fi
    echo "→ 依赖源 $idx 装不上，换下一个再试…"
  done
  [ "$ok" = 1 ] || { echo "依赖安装失败：所有镜像都试过了，请检查网络"; exit 1; }
  printf '%s\r\n' "$SKILL_ID" > "$GM/installed.path"
  cp "$SKILL/backend/pyproject.toml" "$GM/installed.pyproject"
  rm -f "$GM/installed.stamp"
  echo "→ 安装完成"
fi

if [ "$BG" = 1 ]; then
  nohup "$APP" "${ARGS[@]}" > "$GM/server.log" 2>&1 &
  for i in $(seq 1 40); do
    sleep 0.5
    S="$("$APP" --status "${ARGS[@]}" 2>/dev/null || true)"
    case "$S" in *'"running": true'*) echo "$S"; exit 0;; esac
  done
  echo "启动超时，最后的日志："; tail -30 "$GM/server.log"; exit 1
fi
exec "$APP" "${ARGS[@]}"
