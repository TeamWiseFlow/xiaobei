---
name: xhs-hunter
description: 小红书(xhs)内容采集与搜索。用于搜索笔记和用户、查看推荐流与频道、获取用户主页和作品、读取笔记正文/图片/视频/评论、评论与@提醒、点赞收藏提醒、新增关注通知、批量下载媒体及导出表格。
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

在受管 `exec` 中以 `background=true`、`timeoutSeconds=480` 执行该命令，取得执行会话后用 `process log` / `process poll` 读取输出。不要使用 shell `&`、`nohup` 或在显示二维码后结束执行会话。命令输出 `awaiting_scan` 和 `qr_path` 后仍会运行，直到登录成功、需要安全验证、失败或达到 7 分钟任务期限；二维码准备最多等待 90 秒。

读取输出中的 `qr_path`，将图片交给用户扫码，并保持原执行会话运行。用户确认后另行执行：

```bash
xhs-hunter login-confirm
```

`login-confirm` 返回 `pending` 只表示后台任务仍在运行、尚未取得最终结果，不能据此断言用户没有扫码或没有确认。后台进程退出、原执行会话结束或任务超时会返回具体失败原因并清除本次二维码；不要继续展示旧码或反复查询已失败的任务。返回 `awaiting_verification` 时按下一节续接；返回 `authenticated` 才表示正式会话已就位。当前任务结束后可用 `process poll` 回收执行结果，不主动终止仍在等待扫码的会话。

后续运行 `xhs-hunter check` 检查登录态。Cookie 有效时可重复使用；失效或二维码超时后重新运行 `xhs-hunter login` 扫码。扫码二维码文件只用于当前登录，路径不代表登录成功。终端直连场景还可运行交互式 `xhs-hunter login-phone`，按提示输入手机号和验证码；此命令的输入提示不是 JSON。

后台登录日志 `~/.openclaw/logs/xhs-pc-login.log` 在登录执行期间按 5 MiB 轮转，保留 `.1`–`.3` 三份备份，连同当前文件最多约 20 MiB。日志为私有排障材料，不向用户转发原文。

## 安全验证与续接

后台扫码登录或读取返回 `VERIFICATION_REQUIRED` 时暂停原业务命令，使用本技能处理当前验证任务。不要重新扫码登录、重复发短信、连续重试读取或自动重发作品。交互式 `login-phone` 若返回 `supported:false`，按返回的同账号网页链接完成验证后重新发起登录，不调用后台验证命令。

```bash
xhs-hunter verify-start
```

此命令只为当前任务准备一次验证。返回 `awaiting_code` 时将脱敏手机号告知用户，取得验证码后保存为当前用户所有、权限 0600 的普通文件，再执行：

```bash
xhs-hunter verify-code --code-file /绝对路径/验证码文件
```

不要把验证码写入命令行参数、日志或长期记忆。验证码错误最多提交三次；提交后删除自建的验证码文件。发送结果未知时停在 `preparing`，不得重复发送；先核查当前任务，必要时请用户重新发起登录。

返回 `awaiting_scan` 时把 `qr_path` 图片交给用户；用户确认后执行：

```bash
xhs-hunter verify-confirm
```

`verify-confirm` 每次只查询一次状态，轮询至少间隔 1.5 秒。二维码过期、取消或失败时不自动换码。`authenticated` 表示原扫码登录已续接并验证正式账号；`verified` 表示读取验证完成，需要重新执行原读取命令，工具不会自动重放业务请求。账号、登录任务变化或超过任务有效期后，旧验证不能继续。

只支持当前任务的短信验证和 App 扫码验证。其他验证类型按返回的同账号网页链接请用户处理，不自动绕行。私有验证材料由脚本管理，不打开或转发其 JSON 原文。

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

搜索排序 `--sort`：0 综合、1 最新、2 点赞、3 评论、4 收藏。笔记类型 `--type`：0 全部、1 视频、2 图文。`search-notes` 的 `data` 是数组，每项的 `note_card.display_title` 是标题、`note_card.interact_info` 是互动数据；空标题和非笔记位会过滤，`filtered_out` 给出过滤数。`fetch` 支持完整链接、`xhslink.com` / `xhslink.cn` 短链和含链接的复制分享文本，返回正文、作者、话题、互动量、图片和视频地址；短链跳到登录页时脚本自动提取 `redirectPath` 中的笔记地址和对应 token，不要求调用方抄 token。`--download-media` 要与 `--output-dir` 一起使用。外部笔记须使用该笔记对应的 `xsec_token`；错配或不可见导致详情为空时返回 `NOTE_UNAVAILABLE`，应从搜索或用户列表重新获取链接。素材需要后续给 Agent 查看时，将 `--output-dir` 设在工作区内。

`comments` 默认读取全部一级及二级评论；日常调研先用 `--limit 20 --no-inner` 采样，`--limit` 范围为 1–1000 条一级评论。大帖及高频读取容易返回“访问频繁”；相邻请求至少间隔 5 秒，超过 2000 条评论的帖子先限量采样。限流时停止并保留平台提示，不把空评论当作没有讨论。

`fetch` 的 `note.metrics` 保留平台原始字符串，并提供 `liked_count_num` 等数值字段；`user-notes` 的现有计数字段也增加对应 `_num` 字段。遇到 `"2.7万"` 等缩写时用 `_num` 运算，无法解析时 `_num` 为 `null`，不要猜测数值。

## 互动通知读取

笔记评论、评论与 @ 提醒、点赞收藏提醒及新增关注通知均由本技能读取。

```bash
xhs-hunter call get_unread_message
xhs-hunter call get_metions --args '[""]'
xhs-hunter call get_likesAndcollects --args '[""]'
xhs-hunter call get_new_connections --args '[""]'
```

`get_unread_message` 返回未读通知统计；其余三个命令分别读取首批评论/@提醒、点赞收藏提醒和新增关注通知。保留实际方法名 `get_metions`。结果以平台响应为准，失败不当作没有通知。

私信会话、私信历史及私信未读查询由 expert-bd 的 `xhs-im` 提供；笔记评论发布、点赞、收藏和关注等写操作按 expert-bd 能力表执行，目前缺少接口的项目保留为不支持。

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

本技能是一级内容采集、互动通知读取与下载入口；私信、评论发布/回复、点赞、收藏、关注等写操作及直播互动走 expert-bd，创作、发布、本人作品数据与创作者服务走 expert-xhs。`fetch --video-only --download-media` 仅接受视频且只下载视频文件，供 viral-chaser 使用；图文默认 fetch 下载有序图片，分析在 expert-xhs workflow 完成。

## 公开直播读取

房间/商品信息、观看状态与有界事件监听通过 `xhs-hunter live`；先读 [直播读取说明](references/live.md)。复用本技能 PC 会话，商业调研交 expert-osbi；直播文字发送仍由 expert-bd 的 xhs-live 执行。hunter 不接受直播发送方法。
