---
name: platform-runtime
description: TikTok、快手、X、微博和 YouTube 平台工具的内部运行库，统一管理登录和会话，由各 hunter、发布、engagement 与 BD wrapper 调用。
user-invocable: false
disable-model-invocation: true
metadata:
  openclaw:
    requires:
      bins:
        - node
---

平台任务调用对应技能的 wrapper。本目录提供共用传输、能力检查和登录会话管理，不作为业务入口。浏览器登录与导出经 `x-hunter` / `tiktok-hunter` / `weibo-hunter` 的 `login`、`login-status`、`export`（别名 `login-confirm`）执行，专属 session 分别为 `twitter` / `tiktok` / `weibo`；禁止改用通用浏览器会话登录。快手经 `kuaishou-hunter login/login-confirm` 执行 QR/SMS 流程。登录与 TikTok 写材料准备规则见 [登录说明](references/login.md)。

五平台所有签名由 Relay 计算：环境使用 `OFB_KEY` 和可选 `RELAY_BASE_URL`，默认官方地址。平台 HTTP、Cookie 更新、上传、下载与业务状态仍由客户端完成，不能要求 Relay 代发。缺 key、Relay 不可用、签名材料缺失或配额不足时停止；不要切换本地签名、反复重登或直接重试写操作。`RELAY_RATE_LIMITED` 是 Relay 配额，不等于平台风控。YouTube 游客读取和无需签名的微博读取不强制调用 Relay。

不处理滑块、图片点选或 BotGuard 等验证码，不自动刷新验证码、生成拖动轨迹或提交验证结果。快手400002和其他验证码返回 RISK_CONTROL，交用户在平台完成人工验证。运行库不携带签名脚本、视觉识别、OpenCV/Canvas 或 ONNX 模型；媒体图片转码只复用已安装的 ffmpeg/ffprobe。

状态默认保存在 `~/.openclaw/logins/platform-api/`，随 `.openclaw` 持久化。`PLATFORM_API_HOME` 可指定隔离状态目录。依赖通过项目安装流程按本目录 `package.json` 和固定五平台配置安装；使用已按五平台范围准备的分发包，安装前校验完整性、平台范围、适配协议和依赖。不要手工 npm install 或在执行平台任务时临时安装软件；依赖缺失时重新运行项目安装流程。

YouTube 公开读取可免登录，账号操作通过 `youtube-hunter login/login-status/export` 管理专属 session/profile `youtube`；下载保留独立声画轨。Studio 自动发布/删除未开放，不启用运行库中的本地浏览器校验分支，不另装 Chromium 或执行 BotGuard。

代理按 `PLATFORM_API_<平台大写ID>_PROXY`、`PLATFORM_API_PROXY`、对应 Camoufox session/default 配置依次选择；快手没有浏览器 session 配置。空环境变量表示直连，HTTP(S)_PROXY 不作为隐式默认。代理配置与凭据不得输出到日志。
