# HTTP 发布

`login` 返回二维码文件后交用户扫码，再执行 `douyin-login poll --timeout 120` 完成身份确认；扫码成功须返回真实 UID。登录 MFA 按 `douyin-login` 手册续接。已有未知提交时只在原账号登录失效、用户要求恢复时使用 `douyin-publish login --resume-video`，再核查原任务，不能换号处理该提交。

当前发布默认采用 HTTP，直接使用本说明，无需设置后端开关。登录入口仍是 `douyin-publish login`，通过与采集共用的 API 会话扫码；随后 `douyin-publish check` 验证本人 UID、创作者会话和作品读取。不得从浏览器或其他账号手工拼接 Cookie、UA 或密钥。浏览器分步编辑、配乐与草稿命令不适用于此模式；不支持的动作会停止。

## 准备与提交

视频与原声图文沿用 SKILL.md 的 `video run` / `note run` 参数。默认只做本地预览，无网络副作用。已有发布授权后加 `--confirm`；要先准备上传而不提交，另加 `--prepare-only`。此时返回 `state: prepared`、`submission_attempted: false`，核对后用同类型的 `publish --confirm` 提交保存的原请求。可传 `--visibility public|private|friends`，默认 public。视频仍要求 AI 声明及双封面，图文默认 AI 声明；工具把声明和双封面字段写进最终请求。

收据返回 `receipt` 路径和 `attempt_id`，仅在本机 0600 文件中保存。上传、处理超时或准备失败时先查看 `video status` / `note status`；没有提交的失败任务经确认后可 `close --outcome cancelled --confirmation "确认说明" --confirm` 结案，再重新准备。已准备任务保留原文件和请求，不手改收据。

提交前工具持久化意图。出现网络中断、空响应或未知结果时，`publish`、`resume`、`get-link` 均只核查原提交，不再次 POST。使用 `video resume` / `note resume` 查本人作品，工具仅接受完整 ID、同账号、对应文案和提交时间内的唯一新作品；不拿全局最新作品替代。多候选或无候选继续保留未知状态。

`accepted: true` 仅表示平台已返回或核实真实作品 ID，不表示已公开、可播放或审核通过。只有真实 ID 和完整链接才能调用 `published-track` 入库，按既有工作流去重。用户提供确认链接时，使用对应类型的 `close --outcome published --url "完整链接" --confirmation "用户确认原文" --confirm`；不因此把公开/播放状态设为真。

## 创作者二次验证

`state: awaiting_verification` 保留原提交和挑战。按照 `verification.reason` 与实际返回方式操作，短信登录和登录 MFA 命令不能替代本任务验证。

- `gateway_biz_verify`：运行对应类型的 `verify-qr`，把返回 `qr_file` 交用户扫码；用户完成后运行 `verify-poll`。过期则保留原提交并报告，不反复生成二维码。验证完成后 `resume`，不会自动重发作品。
- `gateway_web_authlv_check`：运行 `verify-prepare`；仅使用返回的支持方式。选择接收短信后用 `verify-send --method mobile_sms_verify --confirm`；将用户验证码写入仓外 0600 文件，再用 `verify-code --code-file /受控目录/code.txt`。选择上行短信则用 `verify-send --method mobile_up_sms_verify --confirm`，读取仅供用户的交互文件，用户确认发送后 `verify-confirm --method mobile_up_sms_verify --confirm`。
- 平台返回不支持方式、拒绝、过期或请求结果未知时停止，保留诊断，不自动发码、改方式、重建登录或重发作品。验证票据与扫码通过都不等于发布成功，继续 `resume` 核查。

若只读 `verify-prepare` 已保存 HTTP 200 响应，但因计算故障停住且准备上下文已经过期，可由用户明确选择 `video verify-prepare --restart`（图文使用 `note`）重新准备。此选项也可恢复旧发码计划漏带编码标记、且平台明确返回错误码 1003 的已保存失败响应；客户端和 Relay 都会检查原请求、响应及原作品挑战。它先归档原现场，再仅执行新的只读查询；不发送验证码、不重传素材、不重发作品。已成功发码、已取得票据、其他失败或请求结果未知的流程不能通过此选项重置。准备成功后仍需用户明确执行发码并完成验证，再用 `resume` 核查原提交。

主登录会话不会被二次扫码结果替换。`API_ACCOUNT_MISMATCH` 时停止当前任务，恢复原账号后核查；不能跨账号续传或提交。`PUBLISH_PENDING_API` 表示原 HTTP 任务尚未结案，不切到浏览器再发同一作品。
