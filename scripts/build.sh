#!/usr/bin/env bash
# 开发用：打包前端进后端，并检查仓库里没有 Key 和个人路径。提交前跑一次。
set -e
cd "$(dirname "$0")/.."
VER="$(grep '^version' backend/pyproject.toml | sed 's/.*"\(.*\)"/\1/')"
grep -q "VERSION = \"$VER\"" backend/guanzi_monitor/db.py || { echo "❌ pyproject 版本 $VER 和 db.py 的 VERSION 不一致"; exit 1; }
echo "→ 打包前端"; (cd web && npm run build >/dev/null)
echo "→ 检查 Key 和个人路径"
# Key 的格式 + 本机用户目录 + 外接盘路径（运行时取，不把个人信息写进脚本）
PAT="monid_live_[A-Za-z0-9]{8,}|sk-[A-Za-z0-9]{16,}|sk-ant-[A-Za-z0-9_-]{16,}|$HOME/|/Volumes/[^ \"'<>/).]+"
[ -f scripts/.private-patterns ] && PAT="$PAT|$(paste -sd'|' scripts/.private-patterns)"
FILES="$(git ls-files -co --exclude-standard 2>/dev/null || find . -type f -not -path './web/node_modules/*' -not -path './backend/.venv/*')"
HIT="$(echo "$FILES" | grep -v '^scripts/build.sh$' | tr '\n' '\0' | xargs -0 grep -lE "$PAT" 2>/dev/null || true)"
[ -z "$HIT" ] || { echo "❌ 这些文件里有 Key 或个人路径："; echo "$HIT"; exit 1; }
echo "✓ v$VER 可以提交"
