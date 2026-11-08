---
name: youtube-hunter
description: YouTube 视频、Shorts、频道、评论、播放列表搜索与采集、分轨下载、直播聊天读取和账号通知。公开读取可免登录；创作与本人取数走 expert-youtube，互动写操作走 expert-bd。
metadata:
  openclaw:
    emoji: 🔎
    requires:
      bins:
        - node
---

# YouTube 内容采集

账号鉴权签名由 Relay 计算，使用 `OFB_KEY` 与可选 `RELAY_BASE_URL`，只传计算需要的 SID 字段；平台请求、Cookie 与内容下载仍在客户端。公开游客读取不先请求 Relay。签名失败或配额不足时停止，不回退本地签名；不提供 BotGuard 或其他验证码求解。

搜索、视频详情、评论、频道、公开播放列表和直播聊天支持游客态，不先运行 check 或要求登录。需要强制游客态时传 `--account guest`；个人推荐、订阅流、通知、历史、自己的点赞/稍后观看/订阅列表需要登录。`methods` 返回已接入接口与参数，`call` 只允许读取接口。

```bash
youtube-hunter search '关键词' --sort popular --time month --limit 20
youtube-hunter user '@频道handle'
youtube-hunter user-posts '@频道handle' --limit 20
youtube-hunter comments 'https://youtu.be/dQw4w9WgXcQ' --limit 20
youtube-hunter fetch 'https://youtu.be/dQw4w9WgXcQ' --output-dir /绝对路径/youtube/ref/样本 --download-media --video-only
youtube-hunter call series list '@频道handle' --limit 20
youtube-hunter call series items '<播放列表ID或链接>' --limit 20
youtube-hunter live get '<直播视频ID或链接>'
youtube-hunter live listen '<直播视频ID或链接>' --duration 1m
youtube-hunter methods
```

列表默认20条，`--limit` 为1–100，用返回的 `page.cursor` 有界续读，不用 `--all`。搜索排序仅 general/popular；频道 user-posts 只含「视频」tab，不含 Shorts/直播。Shorts 列表可能缺作者与日期，需要详情核对；相对时间和缩写计数是近似值，缺项保留 null。ID 保留完整字符串，以 `-` 开头的视频 ID 使用完整链接，避免被当成选项。

fetch 保存 `note.json`，返回真实 `video_paths`、`audio_paths`、`media_paths`。下载的视频轨没有声音，音频轨是独立文件；交给 `viral-chaser` 时同时传本次 `video_paths[0]` 和 `audio_paths[0]`，不猜文件名、不把静音视频当成无口播。媒体采用分段下载，年龄限制、会员专享及人机验证可能失败，停止本次采样，不自动换浏览器或出口。直播 listen 轮询服务端消息，不含开始监听前的历史；需要近期消息用 live history。Super Chat 等事件只作为读取样本。

## 登录与出口

登录必须由本技能打开 Camoufox 专属持久 session/profile `youtube`。先执行 `youtube-hunter login --account <alias>`；只有返回窗口 ready、有头、持久身份已确认，才告知用户窗口已打开。等用户在该窗口手动完成 Google/YouTube 登录后，执行 `youtube-hunter export --account <alias>`（别名 login-confirm），再 `youtube-hunter check --account <alias>`。窗口检查用 login-status，不从 profile 数据库或其他浏览器拼 Cookie。

export 先在隔离状态目录导入并在线核验用户，再替换此 alias；失败保留旧会话和窗口，成功关闭窗口。需要 SAPISID 或 __Secure-3PAPISID 及同次完整 HttpOnly 会话，不能只用 document.cookie。Google 可能轮换会话 Cookie；关闭成功导出的窗口，不在该窗口退出账号，失效后重新登录导出，不盲目重试。多账号显式传 `--account`。

代理使用 `PLATFORM_API_YOUTUBE_PROXY`，其次 `PLATFORM_API_PROXY`，再按专属 Camoufox 配置选择；空变量表示直连，不隐式读取 HTTP(S)_PROXY。浏览器登录需 HTTP(S) 出口。会话与错误处理见 [运行库说明](../platform-runtime/references/login.md)。

自己频道视频/私享与草稿列表及指标回填使用 `expert-youtube` 的 youtube-engagement；评论、点赞、稍后观看、订阅和直播发言使用 expert-bd。自动发布/删除视频、资料修改、私信和送礼支付未接入，不通过 call 绕过。
