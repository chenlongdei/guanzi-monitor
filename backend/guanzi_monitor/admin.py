"""网页版管理命令（在服务器上跑，需要 GM_MODE=server）：

  python -m guanzi_monitor.admin invite --note 学员A         # 生成一个邀请码
  python -m guanzi_monitor.admin invite --note 我 --admin    # 管理员邀请码
  python -m guanzi_monitor.admin users                       # 看所有账号
  python -m guanzi_monitor.admin invites                     # 看所有邀请码
  python -m guanzi_monitor.admin reset-password <账号> <新密码>
"""
from __future__ import annotations

import argparse
import time

from . import auth, db


def _t(v):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(v)) if v else "—"


def main():
    if not db.SERVER:
        raise SystemExit("要在网页版环境下跑：GM_MODE=server")
    ap = argparse.ArgumentParser(prog="guanzi_monitor.admin")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("invite")
    i.add_argument("--note", default="")
    i.add_argument("--admin", action="store_true")
    sub.add_parser("users")
    sub.add_parser("invites")
    r = sub.add_parser("reset-password")
    r.add_argument("username")
    r.add_argument("password")
    a = ap.parse_args()
    if a.cmd == "invite":
        print(auth.create_invite(a.note, a.admin))
    elif a.cmd == "users":
        for u in auth.list_users():
            print(f"{u['id']:>3}  {u['username']:<16} {'管理员' if u['is_admin'] else '      '} "
                  f"{'停用' if u['disabled'] else '    '} 注册 {_t(u['created'])}  最近登录 {_t(u['last_login'])}")
    elif a.cmd == "invites":
        for v in auth.list_invites():
            print(f"{v['code']}  {v['note'] or '':<10} {'管理员' if v['is_admin'] else ''}  "
                  f"{'已用：' + (v['used_by_name'] or '') if v['used_by'] else '未用'}")
    elif a.cmd == "reset-password":
        auth.reset_password(a.username, a.password)
        print("已重置，旧登录全部失效")


if __name__ == "__main__":
    main()
