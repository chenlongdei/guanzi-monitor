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
export UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-https://mirrors.aliyun.com/pypi/simple/}"
export UV_PYTHON_INSTALL_MIRROR="${UV_PYTHON_INSTALL_MIRROR:-https://registry.npmmirror.com/-/binary/python-build-standalone}"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

BIN="$VENV/bin"; EXE=""
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) BIN="$VENV/Scripts"; EXE=".exe";; esac
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
STAMP="$SKILL|$(cksum < "$SKILL/backend/pyproject.toml")"
if [ ! -x "$APP" ] || [ "$(cat "$GM/installed.stamp" 2>/dev/null)" != "$STAMP" ]; then
  if ! command -v uv >/dev/null 2>&1; then
    echo "→ 安装 uv（Python 环境管理工具）…"
    curl -LsSf https://astral.sh/uv/install.sh | sh \
      || python3 -m pip install --user -q -i https://mirrors.aliyun.com/pypi/simple/ uv \
      || { echo "uv 安装失败：请检查网络，或按 references/排错.md 手动安装"; exit 1; }
    export PATH="$HOME/.local/bin:$PATH"
  fi
  echo "→ 正在安装（第一次约 1–2 分钟）…"
  [ -x "$BIN/python$EXE" ] || uv venv -q --python 3.11 "$VENV"
  uv pip install -q --python "$BIN/python$EXE" -e "$SKILL/backend"
  echo "$STAMP" > "$GM/installed.stamp"
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
