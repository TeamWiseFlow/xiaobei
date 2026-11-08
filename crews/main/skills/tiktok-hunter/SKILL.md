---
name: tiktok-hunter
description: TikTok 登录、内容搜索与采集：作品、账号、评论、媒体下载；互动写操作走 expert-bd，内容创作与发布使用 expert-tiktok。
metadata:
  openclaw:
    emoji: 🔎
    requires:
      bins:
        - node
---

请求、票据、直播/私信连接与上传签名统一由 Relay 计算，使用 `OFB_KEY` 与可选 `RELAY_BASE_URL`。平台请求仍在客户端；Relay 失败或配额不足时停止，不改成本地计算，不把签名服务错误当作账号登出。验证码不自动求解。


# TikTok内容采集

**登录必须在 Camoufox 专属 session `tiktok` 的持久窗口内完成。不要用通用 browser 工具或其他会话打开登录页；其他窗口中的登录不会被本技能导出。**

**profile 中有 Cookie 不代表登录有效，未到期也不能据此复用登录态。不要读取 `cookies.sqlite` 推断登录成功；已保存 API 会话以 `tiktok-hunter check --account <alias>` 在线校验为准。`check` 成功不能证明新开的浏览器窗口已登录，`login-status:ready` 也只确认窗口；新窗口必须经 export 在线验证。**

首次登录执行 `tiktok-hunter login --account default`，只有返回 `browser_status:ready`、`browser_launched:true`、`headed:true`、`persistent:true` 才向用户说明窗口已打开，并告知 session 和 `url`。等用户确认在该窗口完成登录后执行 `tiktok-hunter export --account default`（也可使用 `login-confirm`），再运行 `tiktok-hunter check --account default`。发布和 BD 工具复用同一账号会话。

窗口不清晰时执行 `tiktok-hunter login-status --account default`，该命令不导航、不导出、不关闭窗口；未就绪时按返回状态和错误指引处理，再运行 login。不要自行换会话；如必须直接排查 Camoufox，后续命令保持 `--session tiktok --persistent --headed`，遗漏 `--headed` 会重启有头会话。export 报缺登录 Cookie 时，先检查窗口模式和 profile；专属持久窗口就绪仍缺字段时，请用户在该窗口完成登录并确认后再导出。不要从 sqlite 或其他窗口复制旧 Cookie 补齐。不要自动轮询或导入 Cookie 造浏览器登录；导出失败保留旧账号和浏览器，成功后关闭。多账号始终显式传 `--account`。详细规则见 [运行库登录说明](../platform-runtime/references/login.md)。

需要发布或互动写能力时，运行 `tiktok-hunter prepare-write --account default` 打开同一 profile 的 Studio 页面；等用户确认页面已就绪后运行 `tiktok-hunter export --account default --require-write`。缺少同次票据/私钥时退出2并保留浏览器；普通 export 允许明确只读会话。不能将 Cookie 登录成功当作写能力已就绪。

```bash
tiktok-hunter check
tiktok-hunter search '关键词' --limit 20
tiktok-hunter user '<用户ID或主页链接>'
tiktok-hunter user-posts '<用户ID或主页链接>' --limit 20
tiktok-hunter comments '<作品链接>' --limit 20
tiktok-hunter fetch '<作品链接>' --output-dir /绝对路径/样本 --download-media
tiktok-hunter fetch '<视频链接>' --output-dir /绝对路径/样本 --download-media --video-only
tiktok-hunter methods
tiktok-hunter call <resource> <action> [平台选项]
```

普通查询返回 JSON 信封，`data` 是数组或对象，`page` 保留游标；fetch 返回 `note`、`media_paths`，保存 `note.json` 和有序媒体文件。保留真实来源、完整字符串 ID 与原始计数，缺项为 null，不补零。终端缩略 ID 不能用于下一步。核对账号作品的作者身份；数字 uid、用户名与 secUid 不能互换。

列表默认 20 条，`--limit` 范围 1–100；按实际 `page` 游标有界续读，不使用 --all。`call` 只允许 methods 列出的读取接口，不能借此发评论、私信、点赞或关注。会话缺失/明确过期返回 2，风控和网络故障保留独立错误，不触发盲重登。

搜索接口可能同时返回非零业务状态码与有效结果，或以203表示空结果；以工具解析的 data/page 为准，不仅凭 status_code 判断登录失效。HTTP 403、明确登录过期和风控仍按独立错误处理。会话中的 msToken 随响应 Cookie 轮换，不用导出时的旧存储值覆盖它。

读取与写入均需真实账号验收。用户搜索未实现；user get 仅给 secUid 时不能取得完整资料。notice list/count、收藏夹、合集、推荐与关注流可读。本人已发作品指标通过专家 engagement 获取。写操作需要同次 ticket-guard 材料。

视频先下载再交 `viral-chaser` 本地 analyzer，采用返回的实际视频路径；`--video-only` 在下载前拒绝图文。图文和文字采样在 `expert-tiktok` 或调用方 workflow 回读原文与图片分析。创作/发布/本人数据走 `expert-tiktok`；互动写操作走 expert-bd，公开直播读取走本 hunter，调研分析走 expert-osbi。下载依赖平台返回的实际可访问媒体 URL，失败不回报下载成功。

## 公开直播读取

`live get/list/search/categories/history/rank/gifts/media/listen` 只读入口使用 `tiktok-hunter live`；先读 [直播读取说明](references/live.md)。send/like 不在 hunter 白名单中，仍由 expert-bd 的 tiktok-live 执行。
