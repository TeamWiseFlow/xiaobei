---
name: xhs-hunter
description: 小红书(xhs)内容采集与搜索。用于搜索笔记和用户、查看推荐流与频道、获取用户主页和作品、读取笔记正文/图片/视频/评论/消息、批量下载媒体及导出表格；为 main 的小红书运营和 BD 共用。
metadata:
  openclaw:
    emoji: 🔎
    requires:
      bins:
      - python3
---

# 小红书内容采集

通过本机 PC HTTP 会话调用小红书网页接口，签名由 OFB Relay 提供（需配置 `OFB_KEY`）。命令直接使用 `xhs-hunter`，常规命令输出 JSON。登录态保存在 `~/.openclaw/logins/xhs-pc-local.json`，与创作者端发布会话分开；无需 `login-manager` 或浏览器 Cookie 导出。

## 首次登录

```bash
xhs-hunter login
```

读取返回的 `qr_path`，将图片交给用户扫码。用户确认后执行：

```bash
xhs-hunter login-confirm
```

后续运行 `xhs-hunter check` 检查登录态。Cookie 有效时可重复使用；失效或二维码超时后重新运行 `xhs-hunter login` 扫码。扫码二维码文件只用于当前登录，路径不代表登录成功。终端直连场景还可运行交互式 `xhs-hunter login-phone`，按提示输入手机号和验证码；此命令的输入提示不是 JSON。

## 彻底清空本地账号与换号

用户要求彻底清空本地小红书账号时，先结束小红书业务请求和后台扫码任务，再删除采集端 `~/.openclaw/logins/xhs-pc-local.json` 与创作者端 `~/.openclaw/logins/xhs-creator-local.json`、对应登录状态及二维码、含凭据的备份；设置了 `XHS_PC_SESSION_FILE` 或 `XHS_CREATOR_SESSION_FILE` 时清理其实际路径，保留业务数据和其他平台会话。换号时先结束旧扫码任务，再按本节流程用目标账号重新登录；需要保留旧号时先将其会话以 0600 权限备份，不保留时先清空。采集端与创作者端独立登录，整体换号还须按 `xhs-publish` 的登录流程切换创作者端，确认两端均由目标账号扫码，并分别运行 `xhs-hunter check` 和 `xhs-publish check` 验证；只重登一端不会切换另一端。

## 常用命令

```bash
xhs-hunter search-notes '关键词' --count 20 --sort 0 --type 0
xhs-hunter search-users '关键词' --count 20
xhs-hunter fetch 'https://www.xiaohongshu.com/explore/笔记ID?xsec_token=...&xsec_source=pc_search'
xhs-hunter fetch 'https://www.xiaohongshu.com/explore/笔记ID?xsec_token=...&xsec_source=pc_search' --output-dir /path/to/note --download-media
xhs-hunter comments 'https://www.xiaohongshu.com/explore/笔记ID?xsec_token=...' --limit 20 --no-inner
xhs-hunter user-notes 'https://www.xiaohongshu.com/user/profile/用户ID?xsec_token=...' --count 20
xhs-hunter call get_user_info --args '["用户ID"]'
xhs-hunter call get_homefeed_all_channel
xhs-hunter feed homefeed_recommend --count 20
xhs-hunter call get_unread_message
```

搜索排序 `--sort`：0 综合、1 最新、2 点赞、3 评论、4 收藏。笔记类型 `--type`：0 全部、1 视频、2 图文。`search-notes` 的 `data` 是数组，每项的 `note_card.display_title` 是标题、`note_card.interact_info` 是互动数据；空标题和非笔记位会过滤，`filtered_out` 给出过滤数。`fetch` 支持完整链接与 `xhslink.com` / `xhslink.cn` 短链，返回正文、作者、话题、互动量、图片和视频地址；`--download-media` 要与 `--output-dir` 一起使用。外部笔记须使用该笔记对应的 `xsec_token`；错配或不可见导致详情为空时返回 `NOTE_UNAVAILABLE`，应从搜索或用户列表重新获取链接。素材需要后续给 Agent 查看时，将 `--output-dir` 设在工作区内。

`comments` 默认读取全部一级及二级评论；日常调研先用 `--limit 20 --no-inner` 采样，`--limit` 范围为 1–1000 条一级评论。大帖及高频读取容易返回“访问频繁”；相邻请求至少间隔 5 秒，超过 2000 条评论的帖子先限量采样。限流时停止并保留平台提示，不把空评论当作没有讨论。

`fetch` 的 `note.metrics` 保留平台原始字符串，并提供 `liked_count_num` 等数值字段；`user-notes` 的现有计数字段也增加对应 `_num` 字段。遇到 `"2.7万"` 等缩写时用 `_num` 运算，无法解析时 `_num` 为 `null`，不要猜测数值。

## 批量采集

```bash
xhs-hunter collect search '关键词' --count 20 --output-dir /path/to/output --download-media --xlsx
xhs-hunter collect user 'https://www.xiaohongshu.com/user/profile/用户ID?xsec_token=...' --count 30 --output-dir /path/to/output --xlsx
xhs-hunter collect urls /path/to/urls.txt --count 20 --output-dir /path/to/output --download-media
```

`urls.txt` 每行一条笔记链接。结果保存在 `notes.json`，每篇笔记独立存 `note.json`；`--xlsx` 另存 `notes.xlsx`。`--download-media` 会下载图片和视频。批量前先对一篇笔记运行 `fetch` 验证链接和登录态。高频采集请分批执行。

## 全部 PC 接口

```bash
xhs-hunter methods
xhs-hunter call <method> --args '[...]' --kwargs '{...}'
```

`methods` 给出所有公开 PC 接口及参数。包括推荐流、搜索建议与热词、用户资料/作品/点赞/收藏、笔记详情、一级和二级评论、未读消息与通知、图片无水印地址和视频地址等。`call` 的 `data` 是接口原始响应；`fetch` 是常用字段整理。部分 `get_all_*` 接口会连续翻页，调用前确认所需范围。接口若返回 `ok:false`，不要把空数据当成事实；核对消息和登录态。

`user-notes` 和 `feed` 默认最多取 20 条，可通过 `--count` 调整至 100；需要完整翻页时使用 `call get_user_all_notes` 等全量接口。

`call` 还暴露搜索历史同步和网页埋点上报等 PC 接口。只有任务确实需要时才调用这些会改变服务端状态的接口。阅读、采集和下载均不发布内容；创作者端发布与自有作品数据仍使用 `xhs-publish`、`xhs-engagement`。
