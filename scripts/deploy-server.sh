#!/usr/bin/env bash
# 网页版发版：打包前端 → 同步后端到服务器 → 重装 → 重启。数据在 /srv/guanzi，不受影响。
#   用法：bash scripts/deploy-server.sh            （服务器地址取 GM_DEPLOY_HOST，默认读 scripts/.deploy-host）
set -e
cd "$(dirname "$0")/.."
HOST="${GM_DEPLOY_HOST:-$(cat scripts/.deploy-host 2>/dev/null)}"
[ -n "$HOST" ] || { echo "❌ 先设置 GM_DEPLOY_HOST=root@服务器IP，或写进 scripts/.deploy-host"; exit 1; }
echo "→ 打包前端"; (cd web && npm run build >/dev/null)
echo "→ 同步到 $HOST"
rsync -az --delete --exclude venv --exclude .venv --exclude __pycache__ --exclude dist --exclude '*.pyc' backend/ "$HOST:/opt/guanzi-monitor/"
echo "→ 重装并重启"
ssh "$HOST" 'cd /opt/guanzi-monitor && venv/bin/pip install -q ".[server]" && systemctl restart guanzi-monitor && sleep 3 && systemctl is-active guanzi-monitor && curl -s 127.0.0.1:8765/api/auth/me'
echo; echo "✓ 已发布（运行中的任务会被标成中断，监控到点会自动再跑）"
