# 登录与会话管理

X、TikTok、微博使用 Camoufox 有头持久 profile，登录态导出和在线验证由运行库统一完成。入口使用各自 hunter，发布、本人数据与 BD 工具复用同一账号会话。快手使用 `kuaishou-hunter login/login-confirm` 的 QR/SMS 流程，具体见其技能说明。

**登录必须发生在对应平台的专属窗口。禁止用通用 browser 工具或其他 session 打开登录页；其他窗口的登录态不会被这里的 export 读取。**

| 平台 | hunter | 专属 session / 持久 profile |
|------|--------|--------------------------|
| X/Twitter | `x-hunter` | `twitter` |
| TikTok | `tiktok-hunter` | `tiktok` |
| 微博 | `weibo-hunter` | `weibo` |

```bash
x-hunter login --account default
```

继承部署的 DISPLAY，不手工指定显示、不创建 Xvfb/noVNC。login 在打开页面后核验 daemon、有头窗口与持久 profile，返回 `session`、`profile`、`browser_status`、`browser_launched`、`headed`、`persistent`、`url` 和 `login_url`。`url` 是实际页面来源与路径，省略用户名、密码、查询参数和片段。只有 `browser_status:ready`、`browser_launched:true`、`headed:true`、`persistent:true` 才向用户说明该 session 的窗口已打开；这些字段不代表账号已登录。等用户在该窗口完成手动登录并确认后执行：

```bash
x-hunter export --account default
x-hunter check --account default
```

TikTok、微博分别将命令替换为 `tiktok-hunter`、`weibo-hunter`。`login-confirm` 是 `export` 的别名；不自动轮询、不在用户确认前尝试导出。

窗口不清晰时调用对应 hunter 的 `login-status --account <alias>`。它只检查专属窗口，不导航、不导出、不关闭窗口；窗口检查与 API `check` 分别使用。`not_running` / `unavailable` 时检查显示环境和浏览器依赖后重新 login；`not_headed` 时重新 login 会恢复有头模式；`wrong_profile` 时先结束该 session 的其他操作，再关闭它并重新 login。不要改用其他会话绕过失败。如必须直接排查 Camoufox，后续命令始终带 `--session <专属名称> --persistent --headed`；漏带 `--headed` 会重启有头 daemon，使已打开的窗口消失。

**profile 中有 Cookie 不代表登录有效。** 不要据 profile 目录或 `cookies.sqlite` 中历史 Cookie 判断登录成功，过期时间未到也不保证有效。export 只读取当前运行窗口的 Cookie 并在线校验；已保存的 API 登录态以 `<hunter> check --account <alias>` 为准。旧 API 会话仍有效也不能证明新窗口已登录，`login-status:ready` 也不判定登录有效。当前窗口缺登录 Cookie 时先检查窗口模式和实际 profile；专属持久窗口就绪仍缺字段时，请用户在该窗口完成登录并确认后再 export。不要从 sqlite 或另一个窗口补 Cookie，也不要自动删除旧 profile。

export 先确认专属有头持久窗口就绪，再完成当前平台来源检查、HttpOnly Cookie 导出、同次 UA/身份读取、关键字段检查、隔离导入和在线用户校验，成功才原子写入 `~/.openclaw/logins/platform-api/`。窗口未就绪时停止，不自动启动其他窗口。成功返回 `browser_session` 和 `credential_file`；原 `session` 字段保留为凭据文件路径。临时文件置于私有目录并清理，凭据文件为0600。不同用户不能覆盖同一 alias；使用新 alias。多账号导出不切换已有默认账号，各业务工具明确传 `--account`。

失败不覆盖旧会话、不关闭浏览器。成功关闭浏览器，若 close 失败返回 `browser_closed:false`，处理该 session 即可，不重登。网页登录成功、API 在线校验和业务写能力分别确认。凭据只给脚本 HTTP 调用，禁止导入 Cookie 来创建新的浏览器会话，不输出 Cookie、私钥或原始请求头。

浏览器与 API 使用同一平台代理配置，媒体下载也沿用它。Camoufox 登录只支持 HTTP(S) 代理；配置更改后先关闭旧 session 再打开，正在运行的 daemon 不会切换出口。

## TikTok 写会话

```bash
tiktok-hunter prepare-write --account default
```

该命令打开同一持久 profile 的 Studio 上传页。用户确认页面已就绪后执行：

```bash
tiktok-hunter export --account default --require-write
```

导出器尝试读取同次 localStorage/sessionStorage 与 security-sdk 相关 IndexedDB 中可访问的私钥和票据；不可导出的密钥不补造，不从其他设备或历史会话拼凑。`--require-write` 要求 ticket_guard_private_key、ticket_guard_encrypt_ticket、ticket_guard_ts_sign 全部存在，缺项退出2并保留浏览器。

不加该参数时允许在线校验后导入只读会话，返回 `write_ready:false` 和缺项名称。TikTok 写工具在请求前再次检查材料。采集器对真实 Camoufox security-sdk 存储布局仍需实号验证。

## 错误处理

退出2为明确会话缺失/过期或写材料缺失；风控、网络异常和依赖缺失独立报告，不反复重登。登录不自动重试。

`BROWSER_FAILED` 表示窗口、模式、profile 或显示环境异常，不等于账号登出。`AUTH_REQUIRED` 且缺少登录 Cookie 时检查是否在专属窗口完成登录，保留浏览器等待用户确认；不要从 sqlite 或另一个窗口复制 Cookie 补齐。
