# HTTP 发布

`login` 返回二维码文件后交用户扫码，再执行 `douyin-login poll --timeout 120` 完成身份确认；扫码成功须返回真实 UID。登录 MFA 按 `douyin-login` 手册续接。已有未知提交时只在原账号登录失效、用户要求恢复时使用 `douyin-publish login --resume-video`，再核查原任务，不能换号处理该提交。

当前发布默认采用 HTTP，直接使用本说明，无需设置后端开关。登录入口仍是 `douyin-publish login`，通过与采集共用的 API 会话扫码；随后 `douyin-publish check` 验证本人 UID、创作者会话和作品读取。不得从浏览器或其他账号手工拼接 Cookie、UA 或密钥。浏览器分步编辑、配乐与草稿命令不适用于此模式；不支持的动作会停止。

## 人脸与设备扫码验证

`gateway_biz_verify_with_face` 先执行对应类型的 `verify-prepare`，使用平台查询返回的可用方法。即使原始决策列出 `mobile_sms_verify`，本关卡也禁止发短信或复用旧短信票据。

人脸方式：

```bash
douyin-publish video verify-prepare
douyin-publish video verify-face-prepare
```

将返回的 `qr_file` 交用户用抖音 App 扫码并完成本人刷脸；二维码票据只写入仓外 0600 文件，不复制到日志或正文。用户完成后执行：

```bash
douyin-publish video verify-face-check
```

返回 `awaiting-face` 时仍在等待，至少隔 3 秒再查；`ticket-issued` 只表示验证出票，作品尚未发布。不重新生成二维码催促用户。

设备扫码方式：查询确实返回 `qr_code_verify` 时，执行 `verify-qr`，将 `qr_file` 交用户用已登录原账号的抖音 App 扫码，并在手机确认；之后 `verify-poll` 查询。`awaiting-scan` 是等待扫码，`scanned` 是等待手机确认，两者至少隔 3 秒再查。`refused` 表示用户拒绝，`expired` 表示入口失效；停止并按用户意愿显式 `verify-prepare --restart` 重建验证准备，不自动刷新或切换方式。

图文将以上命令的 `video` 换成 `note`。验证全部不重传素材、不提交作品；出票后仅在已有发布授权和未发布确认下用 `retry-verified`。旧 `gateway_biz_verify` 的独立扫码仍使用 `verify-qr` / `verify-poll`，它与新设备扫码由工具自动区分，不需要拼接参数。

未知 `*_with_face`、缺少已接入的方法或不完整材料仍返回 `VERIFICATION_METHOD_UNSUPPORTED`；保留收据，禁止改走短信、登录 MFA、手工复制票据或重新 `run`。短信验证后出现新的挑战时，保留历史续接次数；每个挑战 log_id 仍只允许一次续接，新本地验证 ID 不能重置同一挑战的次数。

## 准备与提交

视频与原声图文沿用 SKILL.md 的 `video run` / `note run` 参数。默认只做本地预览，无网络副作用。已有发布授权后加 `--confirm`；要先准备上传而不提交，另加 `--prepare-only`。此时返回 `state: prepared`、`submission_attempted: false`，核对后用同类型的 `publish --confirm` 提交保存的原请求。可传 `--visibility public|private|friends`，默认 public。视频仍要求 AI 声明及双封面，图文默认 AI 声明；工具把声明和双封面字段写进最终请求。

收据返回 `receipt` 路径和 `attempt_id`，仅在本机 0600 文件中保存。上传、处理超时或准备失败时先查看 `video status` / `note status`；没有提交的失败任务经确认后可 `close --outcome cancelled --confirmation "确认说明" --confirm` 结案，再重新准备。已准备任务保留原文件和请求，不手改收据。

提交前工具持久化意图。出现网络中断、空响应或未知结果时，`publish`、`resume`、`get-link` 均只核查原提交，不再次 POST。使用 `video resume` / `note resume` 查本人作品，工具仅接受完整 ID、同账号、对应文案和提交时间内的唯一新作品；不拿全局最新作品替代。多候选或无候选继续保留未知状态。

发布响应原始决策头保存在返回的 `diagnostic_file` 私有文件中，即使正文为空或客户端未识别挑战也保留。`verification:null` 不代表响应没有验证头；`header_names` 只说明头名存在，具体识别状态看 `response_info.verification_decision`。遇到未识别的决策保留原任务并反馈诊断，不把旧任务的过期验证、票据或 log_id 拼到当前作品，也不靠结案后反复上传重发排障。

`accepted: true` 仅表示平台已返回或核实真实作品 ID，不表示已公开、可播放或审核通过。只有真实 ID 和完整链接才能调用 `published-track` 入库，按既有工作流去重。用户提供确认链接时，使用对应类型的 `close --outcome published --url "完整链接" --confirmation "用户确认原文" --confirm`；不因此把公开/播放状态设为真。

## 创作者二次验证

`state: awaiting_verification` 保留原提交和挑战。按照 `verification.reason` 与实际返回方式操作，短信登录和登录 MFA 命令不能替代本任务验证。

- `gateway_biz_verify`：运行对应类型的 `verify-qr`，把返回 `qr_file` 交用户扫码；用户完成后运行 `verify-poll`。过期则保留原提交并报告，不反复生成二维码。验证完成后 `resume`，不会自动重发作品。
- `gateway_biz_verify_with_face`：按上方人脸/设备扫码步骤处理，不使用短信。
- `gateway_web_authlv_check`：运行 `verify-prepare`；仅使用返回的支持方式；平台提供人脸或设备扫码时也可按上方对应步骤处理。选择接收短信后用 `verify-send --method mobile_sms_verify --confirm`；将用户验证码写入仓外 0600 文件，再用 `verify-code --code-file /受控目录/code.txt`。选择上行短信则用 `verify-send --method mobile_up_sms_verify --confirm`，读取仅供用户的交互文件，用户确认发送后 `verify-confirm --method mobile_up_sms_verify --confirm`。
- 平台返回不支持方式、拒绝、过期或请求结果未知时停止，保留诊断，不自动发码、改方式、重建登录或重发作品。验证票据与扫码通过都不等于发布成功，继续 `resume` 核查。

### 验证后的原作品续接

`ticket-issued` 后，先按原任务核查。用户明确确认原作品未发布并要求继续时，执行：

```bash
douyin-publish video retry-verified --not-published-confirmation "用户确认原作品未发布并要求继续的原文" --confirm
```

图文将 `video` 换成 `note`。已有用户确认与授权时直接使用，不重复询问。没有 `--confirm` 时只读本地预览。程序要求有效的同账号、同挑战票据，复核本人作品，并保留原 creation_id、视频和封面、文案及完整正文；不新增手工票据参数。匹配到已发布作品时直接确认；多候选或账号不符时停止。

每个验证流程只允许一次这种明确授权的续接，发送前先保存意图。中断、网络失败、再次出现验证或结果未知时不自动再 POST；后续 `resume`、`publish` 和重复同一 `retry-verified` 只核查。`publish_gate_verified=false` 表示尚未证实发布放行，不修改它来伪装成功。只有平台作品 ID 或核查匹配才能确认发布。

准备、等待验证码、等待上行短信、人脸、扫码或票据阶段已过期，且没有挂起的请求时，可用 `verify-prepare --restart` 重新查询原作品挑战。它归档旧验证上下文，保留原作品收据和上传材料，不发送短信；之后按实际方式明确发码、验码，再使用新票据续接。尚有效的流程或已发送但结果未知的请求不能用此选项重置。

重复 `verify-prepare` 会复用尚有效的验证摘要。结果核查可能返回 `cached=true` 与 `retry_after_seconds`，应等提示时间再查，不把缓存结果当作一次新平台核查。

若只读 `verify-prepare` 已保存 HTTP 200 响应，但因计算故障停住且准备上下文已经过期，可由用户明确选择 `video verify-prepare --restart`（图文使用 `note`）重新准备。此选项也可恢复旧发码计划漏带编码标记、且平台明确返回错误码 1003 的已保存失败响应；客户端和 Relay 都会检查原请求、响应及原作品挑战。它先归档原现场，再仅执行新的只读查询；不发送验证码、不重传素材、不重发作品。尚有效的验证流程、其他失败或请求结果未知的流程不能通过此选项重置。准备成功后仍需用户明确执行发码并完成验证，按上节核查或续接原提交。

验证命令的 `ok=true` 只表示本次验证步骤完成，作品是否确认由 `publication_confirmed` 和作品 ID 判断。旧发布错误会放在 `publication_error`，不能据此重复执行已经完成的发码或验码步骤。

主登录会话不会被二次扫码结果替换。`API_ACCOUNT_MISMATCH` 时停止当前任务，恢复原账号后核查；不能跨账号续传或提交。`PUBLISH_PENDING_API` 表示原 HTTP 任务尚未结案，不切到浏览器再发同一作品。
