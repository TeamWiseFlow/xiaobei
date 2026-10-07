---
name: douyin-publish
description: 抖音独立 API 视频与图文发布、上传、封面及发布结果核查。
---

# 抖音发布

先执行 `douyin-hunter check`，确认独立 API 会话。发布前执行 `douyin-publish check --kind video`；图文使用 `--kind note`，原创且无需声明时同时传 `--declaration none`。检查会验证本人身份、平台声明选项、创作者域 CSRF 与发布安全材料，不上传素材或提交作品。预览只校验本地输入，不能代替该检查。

`PUBLISH_SECURITY_MISSING` 的 `missing_fields` 只列缺失材料的名称；交研发按当前 API 会话补齐初始化或刷新流程，不手工伪造材料，不开启旧浏览器。声明获取失败或 `DECLARATION_UNAVAILABLE` 时停止发布并报告，不通过改成 `none` 绕过 AI 标注。

已有自动初始化会话的发布材料缺少或即将过期时，`check` 自动刷新当前账号；需要单独诊断时用 `douyin-login refresh`。刷新有效期与登录句柄期限分别校验。上传处理结束后、记录提交意图之前再次预检，随后针对完整业务体计算并发送相同字节；空体预检成功不代表平台已接受发布。`SECURITY_REFRESH_REQUIRED` 或 `SECURITY_REFRESH_FAILED` 时停止当前提交，不能通过重新初始化、改账号或填入材料名绕过。

```bash
douyin-publish video --video /绝对路径/video.mp4 --cover /绝对路径/cover.jpg --title "标题" --caption "简介 #话题"
douyin-publish note --images /绝对路径/1.jpg /绝对路径/2.jpg --title "标题" --caption "正文 #话题"
```

默认预览。用户已确认内容并要求发布后，在同一命令加 `--confirm`。默认公开可见；`--visibility 1` 仅自己可见，`2` 好友可见。`--timing` 为未来的秒级 Unix 时间戳，`--no-download` 关闭保存权限。视频标题 ≤30 字，图文标题 ≤20 字；描述 ≤1000 字；图文 1–35 张、单张 ≤50MB。默认按 `aigc` 声明，工具按本次发布任务从平台获取可用选项并写入提交字段，无需预置会话配置。纯实拍且无需声明才传 `--declaration none`。音乐只接受核实可用的平台 `--music-id`；不编造歌曲或推荐结果。

需要话题、提及、活动、地点、合集或热点等实际平台元数据时传 `--options-file /绝对路径/options.json`，使用 challenges、mentions、activity、poi、mix_id、hot_spot 字段；不要编造 ID。视频还支持 cover_delay、cover_tools_extend_info、cover_tools_info、chapter，图文支持已上传的 cover_uri。工具将这些字段一并预览；文件不能覆盖账号、发布任务 ID、安全材料或最终提交地址。

上传在本机完成：申请短期凭据、申请上传节点、分片上传、校验与提交。媒体字节不发给 Relay；Relay 只处理上传凭据与请求元数据。视频处理检测、封面与作品提交使用创作者 API。

任务文件保存在 `~/.openclaw/douyin-api/publish/`，权限 0600。账号任务串行，每 24 小时最多 5 次作品提交。提交前保存 `submission_unknown`，网络错误或中断不会自动重发；只有拿到平台确认的作品 ID 和 URL 才报告成功。

`PLATFORM_NON_JSON` 时检查返回的 `response_info`：区分 `body_kind: empty`、`html` 和其他非 JSON，保留 HTTP 状态、内容类型、字节数及可得的请求日志 ID。HTTP 200 不代表发布成功，非 JSON 也不能直接判为风控页。安全相关响应头出现不代表验证失败；需结合其值和平台证据排查，不能自行解读成签名失效、频控或二次验证。

响应前 512 字节及选定的安全验证响应头值仅保存到返回的 `diagnostic_file`（仓外、0600；每个头值最多 8192 字符），任务同时记录 `last_error`；命令仅返回摘要和文件路径。交接只提供摘要、日志 ID 和受控文件路径，不复制其中的完整响应、头值、Cookie 或安全材料。错误不会触发重发或自动解除未知任务。

提交返回 `reason: PLATFORM_VERIFICATION_REQUIRED` 时，保留原任务，通过下面的创作者验证入口继续同一 API 会话。`mobile_sms_verify` 为短信验证码，`mobile_up_sms_verify` 为用户手动发送平台指定上行短信。当前可选方法由准备结果提供；手机号登录和登录 MFA 分属其他流程。

```bash
douyin-publish verify-prepare --job-file /受控目录/job-ID.json
douyin-publish verify-status --job-file /受控目录/job-ID.json
douyin-publish verify-send --job-file /受控目录/job-ID.json --method mobile_sms_verify --confirm
douyin-publish verify-code --job-file /受控目录/job-ID.json --method mobile_sms_verify --code-file /受控目录/code.txt
```

`verify-prepare` 只查询当前验证方式；`verify-status` 本地只读。发送默认预览，用户授权后加 `--confirm`，验证码从仓外私有文件读取。选择上行短信时用 `verify-send --method mobile_up_sms_verify --confirm` 获取 `instruction_file`；号码和文本只在该 0600 文件中。用户按指示发送后执行 `verify-confirm --method mobile_up_sms_verify --confirm`。重复已完成发送会恢复当前结果；响应已保存时仅重交计算，发送结果未知则停止。

验证期限为准备起最多 10 分钟。取得 `ticket-issued` 仅确认本 API 会话取得验证票据，下一步是核查原作品结果；原任务保留 `submission_unknown`，作品核实和结案使用下方 `status` / `resolve`。工具不把验证完成当成发布成功，也不自动再次提交作品。

```bash
douyin-publish status --job-file /受控目录/job-返回的ID.json
```

结果未知时直接使用创作者本人作品列表核查最近 50 条作品，不依赖 `sec_uid` 或创作者资料接口；按账号、标题及发布时间筛出候选。候选不代表发布成功，列表也不保证包含私密或审核中的作品。已人工结案的 `not_published` 或已有确认 ID 的 `confirmed` 任务直接返回其保存状态，不重新判为未知。不得按列表首条、近似标题、首屏缺失或超时直接结案。未知提交会阻止同账号再次发布，先核实并处理任务状态。确认发布后用 `published-track record` 记录，再使用 `douyin-engagement` 取本人播放量及公开互动量。

`status` 会从该任务配套的私有诊断识别已发生的验证要求，包括旧代码只返回 `PLATFORM_NON_JSON` 的任务；只返回安全 `verification` 摘要，不改任务。该摘要描述提交当时的要求，不代表当前挑战仍有效或 App 验证已同步。验证完成后先核查、处理原未知任务，再按授权新建发布任务，原任务不重发。

用户核实了具体作品后，使用下面的命令解除未知状态。工具验证作品所属账号、标题与发布时间；仍无法确认时保持未知，不重发。

```bash
douyin-publish resolve --job-file /受控目录/job-ID.json --resolution confirmed --content-id 已核实作品ID --confirm
```

用户明确核实未发布时，可用 `--resolution not-published --evidence "核查依据" --confirm`。这会解除该任务的阻塞，不执行重新发布；不得仅凭超时、首屏未出现或列表读取失败执行此操作。

封面生成的多步任务使用脚本保存任务 ID 并轮询，避免手动拼接中间值：

```bash
douyin-publish cover-generate --body-file /受控目录/cover-input.json --output /受控目录/cover-result.json
```

请求文件是平台业务 JSON 对象，包含 cover_uri、img_uris、creation_id、uid，以及需要的 title、caption、audio_uri、ratio_type、action。先预览，经授权生成时加 `--confirm`。失败时从输出文件保留的 task_id 用 `cover_result` 核查，不重复创建生成任务。

`douyin-publish call <method> --params '{...}'` 支持创作者作品预览、封面引用/生成/结果、声明建议、转码信号、检测及媒体 URL 查询。写方法默认预览，执行加 `--confirm`；检测请求体用 `--body-file`。上传凭据不会通过此命令输出。具体方法通过 `douyin-publish call --help` 查看。
