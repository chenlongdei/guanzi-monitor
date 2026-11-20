---
name: guanzi-monitor
description: 观自行深监控台：在本机打开一个网页工作台，采集抖音、小红书、视频号的内容和数据，并且可以监控。能粘链接采单条、按关键词搜热门（抖音走抖音指数视频搜索）、拉博主作品、监控关键词和博主、转逐字稿、导出 Excel。Claude 可以替用户启动、关闭和排查问题，也可以直接通过本地接口帮用户采集，再读结果做判断。用于「打开监控台」「启动观自行深」「帮我采这几条链接」「搜一下 XX 近 7 天的抖音热门」「盯住这个博主」「这批里哪些值得学」「导出表格」「监控台打不开 / 采不到」；不用于 YouTube、B 站等其他平台，也不用于写文案。
---

# 观自行深监控台

## 它是什么

一个跑在用户自己电脑上的网页（默认 http://127.0.0.1:8765）。数据和 Key 都只存在本机：
- 程序装在 `~/.guanzi-monitor/venv`，运行信息在 `~/.guanzi-monitor/run.json`
- 采到的内容、逐字稿 md、数据库都在 `~/观自行深监控台/`（用户可以在设置里改）

`<skill>` 指本文件所在的文件夹。

## 铁律

1. **先报价再花钱**：采关键词、博主前先调 `/api/estimate`，把条数和预计花费告诉用户；超过 20 条或超过 $0.1，等用户确认再开始。单条链接直接采。
2. **Key 不出现在对话里**：不打印、不复述用户的 Key，也不写进任何文件。让用户在网页的欢迎页或设置页自己粘贴。用户把 Key 发在对话里时，提醒他们以后直接填网页，这次可以帮他们通过 `PUT /api/settings` 存进去，但回复里不要重复 Key。
3. **只采集，不替用户下结论**：用户问「哪些值得学」时才分析，分析要基于接口返回的数据（收藏率、转发率、超常倍数等），说清楚依据。
4. **出错先自己查**：看 `--status`、任务日志、`~/.guanzi-monitor/server.log`，查到原因再告诉用户，不要让用户自己翻日志。

## 安装（Agent 照着做）

用户发来仓库地址 https://github.com/chenlongdei/guanzi-monitor 让你安装时：

1. **确定装到哪**：Claude Code → `~/.claude/skills/guanzi-monitor`；Codex → `~/.codex/skills/guanzi-monitor`；WorkBuddy → `~/.workbuddy/skills/guanzi-monitor`；其他 → `~/.agents/skills/guanzi-monitor`。Windows 上 `~` 是 `%USERPROFILE%`。已经存在就是更新，走第 4 步。
2. **下载**：`git clone --depth 1 https://github.com/chenlongdei/guanzi-monitor.git <目标文件夹>`
   - 没有 git 或 clone 失败：下载 `https://codeload.github.com/chenlongdei/guanzi-monitor/zip/refs/heads/main`，解压后把里面的 `guanzi-monitor-main` 改名放到目标位置
   - GitHub 访问不了：在地址前加 `https://ghfast.top/` 再试
3. **启动**（第一次会自动装好 Python 环境，1–2 分钟，不需要用户预先装任何东西）：
   - macOS / Linux：`bash <目标文件夹>/scripts/start.sh --bg`
   - Windows，你的命令行是 Git Bash：同上
   - Windows，你的命令行是 PowerShell / cmd：`Start-Process "<目标文件夹>\启动监控台.bat"`（会弹出一个窗口，告诉用户别关它）。查状态用 `& "$env:USERPROFILE\.guanzi-monitor\venv\Scripts\guanzi-monitor.exe" --status`
   - 输出里 `"running": true` 和 `url` 就是成功，浏览器会自动打开
4. **更新**：`git -C <目标文件夹> pull`，然后先 `--stop` 再启动。数据和 Key 不受影响
5. **告诉用户**：网页停在「欢迎」页，按提示填 Monid Key（必需）和阿里云百炼 Key（可选），申请方法见 `references/申请Key.md`；以后说「打开监控台」就行

装的时候遇到报错，先看 `references/排错.md`，按用户的系统自己处理，不要把报错原样丢给用户。

## 启动、关闭、状态

```bash
bash "<skill>/scripts/start.sh" --bg        # 后台启动并打开浏览器
bash "<skill>/scripts/start.sh" --status    # 是否在运行、网址、数据目录（JSON）
bash "<skill>/scripts/start.sh" --stop      # 关闭
bash "<skill>/scripts/start.sh" --demo --bg # 演示模式：假数据，不联网不花钱
```

- 已经在运行时再启动，只会重新打开浏览器，不会重复启动。
- 8765 被占用会自动换到 8766、8767…，**以 `--status` 返回的 `url` 为准**，下面的 `$URL` 都指它。
- Windows 不用 Git Bash 时，把 `bash .../start.sh` 换成第 3 步里的写法；用户自己双击用 `启动监控台.bat`、`关闭监控台.bat`。

第一次启动后，网页会停在「欢迎」页，让用户填：
1. **Monid Key**（必需，`monid_live_` 开头，在 app.monid.ai 注册充值获得）
2. **阿里云百炼 Key**（可选，转逐字稿用，`sk-` 开头）

填好之前其他页面打不开。具体怎么申请见 `references/申请Key.md`。

## 帮用户采集（本地接口）

所有接口都是 JSON，完整参数见 `references/接口.md`。常用：

| 用户说 | 做法 |
|---|---|
| 采这几条链接 | `POST $URL/api/jobs/single {"text": "<原样粘贴的分享文案或链接>", "transcribe": true}` |
| 搜「X」近 7 天抖音热门 | 先 `POST $URL/api/estimate {"kind":"keyword","platform":"douyin","keyword":"X","days":7,"limit":20}`，报价后 `POST $URL/api/jobs/keyword`（同样的参数） |
| 拉这个博主的作品 | `POST $URL/api/jobs/blogger {"input": "<主页链接>", "limit": 30}` |
| 盯住这个关键词 / 博主 | `POST $URL/api/monitors`（博主要先采进库，拿到作者 id） |
| 看结果 | `GET $URL/api/jobs/<job_id>` 直到 `status` 不是 queued / running；内容在 `GET $URL/api/contents?...` |
| 导出 Excel | 告诉用户在「内容库」点导出，或给链接 `$URL/api/contents/export?keyword=X` |

任务是异步的：创建后返回 `job_id`，每 3–5 秒查一次。完成后给用户：采到几条、失败几条和原因、花了多少钱，并提醒在网页哪一页能看到。

### 读懂数据

`/api/contents` 每条带 `ins`（不额外花钱，用已有数据算的）：
- `save_rate` 收藏/点赞：高 → 干货，用户想留着照做
- `share_rate` 转发/点赞：高 → 有社交货币，愿意转给别人
- `comment_rate` 评论/点赞：高 → 有话题或争议
- `like_fan` 点赞/粉丝：> 1 → 火出了自己的粉丝盘子
- `multiple` 这条点赞 / 博主平均点赞：看是不是博主自己的异常爆款
- `per_day` 日均点赞：新发且高 → 正在起量

所有渠道都**拿不到抖音播放量**，不要编。

## 常见问题

| 现象 | 处理 |
|---|---|
| 启动时卡在安装 | 网络问题。脚本已经用国内镜像，再试一次；还不行看 `references/排错.md` |
| 浏览器打不开 | `--status` 看实际网址；`running:false` 就看 `~/.guanzi-monitor/server.log` 最后 30 行 |
| 「没有填 Monid Token」 | 让用户去欢迎页或设置页填 |
| Monid 返回 402 / BLOCKED / 余额不足 | 让用户去 app.monid.ai 充值，不要反复重试 |
| 502 / all providers failed | 上游临时故障，程序已自动重试和换接口；过几分钟在网页上点「重试」 |
| 转写 403 / AccessDenied | 百炼 Key 所在空间没开通语音识别，或欠费；设置页「测试连接」会给出具体原因 |
| 视频号不能转逐字稿 | 已知限制，视频号的视频是加密的 |

更多见 `references/排错.md`。

## 更新

用户说「更新监控台」：`--stop` → `git -C <skill> pull` → 启动。代码是可编辑安装，拉下来就生效；依赖有变化时 `start.sh` 会自动重装。
