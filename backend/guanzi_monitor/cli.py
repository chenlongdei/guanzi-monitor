"""guanzi-monitor：一条命令启动本地监控台并打开浏览器。

  guanzi-monitor                 # 启动（默认 http://127.0.0.1:8765）
  guanzi-monitor --demo          # 演示模式：假数据、不联网、不花钱，独立数据库
  guanzi-monitor --data <目录>    # 指定采集结果保存位置（会记住）
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import threading
import time
import webbrowser


def _free(host: str, port: int) -> bool:
    with socket.socket() as so:
        return so.connect_ex((host, port)) != 0


def _alive(url: str) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(url + "/api/settings", timeout=2) as r:
            return r.status == 200
    except Exception:  # noqa
        return False


def main():
    ap = argparse.ArgumentParser(prog="guanzi-monitor", description="观自行深监控台")
    ap.add_argument("--port", type=int, default=int(os.environ.get("DEI_WB_PORT", 8765)))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--demo", action="store_true", help="演示模式：假数据，不联网")
    ap.add_argument("--data", help="采集结果保存目录（记住到 ~/.guanzi-monitor/config.json）")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--stop", action="store_true", help="关掉正在运行的监控台")
    ap.add_argument("--status", action="store_true", help="看监控台有没有在运行（输出 JSON）")
    a = ap.parse_args()
    if a.demo:
        os.environ["DEI_WB_DEMO"] = "1"
    from . import db
    if a.data:
        cfg = db.boot_config()
        cfg["data_root"] = os.path.abspath(os.path.expanduser(a.data))
        db.save_boot_config(cfg)
    root = db.data_root()
    if not a.demo and root.anchor and not os.path.exists(root.anchor if root.anchor != "/" else "/"):
        raise SystemExit(f"保存位置不可用：{root}")
    if not a.demo and str(root).startswith("/Volumes/") and not os.path.exists("/".join(str(root).split("/")[:3])):
        raise SystemExit(f"外接盘没插：{root}")
    run_file = db.BOOT / ("run_demo.json" if a.demo else "run.json")
    if a.stop or a.status:
        info = json.loads(run_file.read_text()) if run_file.exists() else {}
        alive = bool(info) and _alive(info["url"])
        if a.status:
            print(json.dumps({"running": alive, **info, "data": str(root), "version": db.VERSION}, ensure_ascii=False))
            return
        if not alive:
            print("监控台没有在运行")
            run_file.unlink(missing_ok=True)
            return
        import signal
        os.kill(info["pid"], signal.SIGTERM)
        print("监控台已关闭")
        return
    # 已经开着就直接打开，不重复启动
    if run_file.exists():
        try:
            old = json.loads(run_file.read_text())["url"]
            if _alive(old):
                print(f"监控台已经在运行 → {old}")
                if not a.no_browser:
                    webbrowser.open(old)
                return
        except Exception:  # noqa
            pass
    port = a.port
    while not _free(a.host, port) and port < a.port + 20:
        port += 1
    url = f"http://{a.host}:{port}"
    db.BOOT.mkdir(parents=True, exist_ok=True)
    run_file.write_text(json.dumps({"url": url, "pid": os.getpid(), "started": time.time(), "data": str(root)}))
    print(f"观自行深监控台 → {url}\n数据：{db.db_path()}\n{'【演示模式】' if a.demo else ''}")
    if not a.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    import uvicorn
    try:
        uvicorn.run("guanzi_monitor.app:app", host=a.host, port=port, log_level="warning")
    finally:
        try:
            if json.loads(run_file.read_text()).get("pid") == os.getpid():
                run_file.unlink()
        except Exception:  # noqa
            pass


if __name__ == "__main__":
    main()
