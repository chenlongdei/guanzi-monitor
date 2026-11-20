#!/bin/bash
# 双击启动观自行深监控台。这个窗口开着，监控台就开着（可以最小化，别关）。
cd "$(dirname "$0")"
echo "观自行深监控台：这个窗口请保持打开（可以最小化），关掉窗口监控台就停了。"
echo
bash scripts/start.sh "$@"
echo; read -n 1 -s -r -p "按任意键关闭窗口"
