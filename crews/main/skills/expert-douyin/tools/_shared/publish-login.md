# 共用抖音 API 登录

采集、创作者发布与本人取数共用 `douyin-login` 管理的 API 会话。先用 `douyin-publish check` 验证原账号和创作者通道；已有有效登录不重新扫码。明确未登录或用户要求重新登录时，`douyin-publish login` 生成二维码，交用户扫码后用 `douyin-login poll --timeout 120` 确认 UID。登录 MFA 按 douyin-login 手册续接。

主站与创作者分别维护 token 和证书，工具自动处理，不从浏览器 profile 或其他账号拼接材料，不使用 login-manager。未知提交保留原收据，恢复原账号后只核查，不重新发布。
