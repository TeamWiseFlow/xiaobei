# 共用创作者登录

发布使用 Camoufox 持久化 session `douyin`，本人作品指标由 engagement 经 HTTP 取数并临时读取同一 profile 的 cookie/UA。执行 `douyin-publish login` 打开有头创作者中心，由用户完成扫码或页面验证，然后用 `douyin-publish check` 验证。关闭进程保留 profile，下次操作自动复用。

不要调用 login-manager，不导出或导入 cookie，不拿 hunter 的独立 API 会话覆盖浏览器 profile。hunter 与 expert-bd 互动的登录另走 `douyin-login`，两条会话独立。

发布和取数串行执行；点击发布后结果不明先核实管理页，不能重新登录后直接重发。
