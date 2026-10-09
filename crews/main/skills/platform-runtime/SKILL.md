---
name: platform-runtime
description: TikTok、快手、X 和微博平台工具的内部运行库，统一管理登录和会话，由各 hunter、发布、engagement 与 BD wrapper 调用。
user-invocable: false
disable-model-invocation: true
metadata:
  openclaw:
    requires:
      bins:
        - node
---

平台任务调用对应技能的 wrapper。本目录提供共用传输、能力检查和登录会话管理，不作为业务入口。浏览器登录与导出经 `x-hunter` / `tiktok-hunter` / `weibo-hunter` 的 `login`、`login-status`、`export`（别名 `login-confirm`）执行，专属 session 分别为 `twitter` / `tiktok` / `weibo`；禁止改用通用浏览器会话登录。快手经 `kuaishou-hunter login/login-confirm` 执行 QR/SMS 流程。登录与 TikTok 写材料准备规则见 [登录说明](references/login.md)。

状态默认保存在 `~/.openclaw/logins/platform-api/`，随 `.openclaw` 持久化。`PLATFORM_API_HOME` 可指定隔离状态目录。依赖通过项目安装流程按本目录 `package.json` 和固定四平台配置安装；安装器在解析依赖前裁剪其他平台及专属资源，并校验保留模块。不要手工 npm install 或在执行平台任务时临时安装软件；依赖缺失时重新运行项目安装流程。

代理按 `PLATFORM_API_<平台大写ID>_PROXY`、`PLATFORM_API_PROXY`、对应 Camoufox session/default 配置依次选择；快手没有浏览器 session 配置。空环境变量表示直连，HTTP(S)_PROXY 不作为隐式默认。代理配置与凭据不得输出到日志。
