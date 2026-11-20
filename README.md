<p align="center"><img src="backend/guanzi_monitor/web/logo-ink.png" alt="观自行深" height="56"></p>

# 观自行深监控台

在自己电脑上打开一个网页，采集抖音、小红书、视频号的内容和数据，并且能一直盯着：

- **单条采集**：粘贴分享链接，拿到点赞、评论、收藏、分享和逐字稿
- **关键词**：搜一个词近几天的热门（抖音走「抖音指数」视频搜索，能筛低粉爆款）
- **博主**：拉一个博主的最新作品，看他平时什么水平、哪条是爆款
- **监控**：关键词和博主每天自动看一次，新内容标「新」
- **数据有判断**：收藏率高 = 干货，转发率高 = 愿意转，赞粉比 > 1 = 火出了粉丝盘子
- **导出 Excel**，逐字稿存成 Markdown

所有数据和 Key 只存在你自己的电脑上。

## 安装：一句话交给 AI

把下面这句话发给你的 AI Agent（Claude Code、Codex、WorkBuddy 都可以）：

> 帮我安装这个 skill：https://github.com/chenlongdei/guanzi-monitor ，按里面 SKILL.md 的「安装」步骤操作，装好后打开监控台。

它会按你的系统（Mac 或 Windows）自动装好、启动，浏览器会打开监控台。第一次大约 1–2 分钟，不需要你提前装 Python。

然后在网页的「欢迎」页按提示填两个 Key：

1. **Monid Key**（必需）：去 https://app.monid.ai 注册、充值、复制 Key
2. **阿里云百炼 Key**（可选，转逐字稿用）

详细步骤见 [references/申请Key.md](references/申请Key.md)。填好后粘一条抖音链接试试，看到数据就装好了。

## 平时怎么用

跟 AI 说：

- 「打开监控台」/「关掉监控台」/「更新监控台」
- 「帮我把这几条链接采了，转成逐字稿」
- 「搜一下『AI 副业』近 7 天抖音热门，先告诉我多少钱」
- 「盯住这个博主，每天看一次」
- 「这批里哪几条收藏率最高？为什么？」

不想通过 AI 也行：Mac 双击 `启动监控台.command`，Windows 双击 `启动监控台.bat`。弹出的命令窗口不要关（可以最小化），关了监控台就停了。

- 数据保存在：`你的用户文件夹/观自行深监控台/`（设置里可以改）
- 花多少钱：见 [references/费用.md](references/费用.md)，一般每月几美元；超过 20 条会先问你
- 遇到问题：见 [references/排错.md](references/排错.md)，或者直接把报错发给你的 AI

## 不用 AI 手动安装

```bash
git clone https://github.com/chenlongdei/guanzi-monitor.git ~/.claude/skills/guanzi-monitor
bash ~/.claude/skills/guanzi-monitor/scripts/start.sh --bg
```

Windows：下载 [ZIP](https://codeload.github.com/chenlongdei/guanzi-monitor/zip/refs/heads/main)，解压到一个固定位置（之后别挪），双击 `启动监控台.bat`。

## 开发

见 [docs/开发.md](docs/开发.md)。

## 许可

代码采用 [MIT 许可](LICENSE)。「观自行深」名称和 logo 不在 MIT 范围内，未经许可不得用于其他产品。
