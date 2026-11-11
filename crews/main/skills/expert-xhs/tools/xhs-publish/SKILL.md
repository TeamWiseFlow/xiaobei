---
name: xhs-publish
description: 通过 Creator 本地 HTTP 会话发布小红书图文和视频笔记，并管理 Creator 扫码登录。
---

# 小红书发布

本工具由 `expert-xhs` 的发布 Workflow 调用。客户端负责 Creator HTTP 请求、媒体上传和发布，签名由 OFB Relay 提供（需配置 `OFB_KEY`）；`xhs-engagement` 复用同一登录态。会话存于 `~/.openclaw/logins/xhs-creator-local.json`（0600），Cookie 和会话状态持久化。只要 Cookie 有效，后续命令直接复用，不必每次扫码。

## 登录流程

1. 发布前运行 `xhs-publish check`。退出码 0 表示有效；2 表示缺少会话或明确认证失效；1 表示接口或环境故障，先排查。
2. 仅在需要重新登录时运行 `xhs-publish login`。在受管 `exec` 中设置 `background=true`、`timeoutSeconds=480`，用 `process log` / `process poll` 读取当前执行会话输出。二维码准备最多等待 90 秒，登录任务最多运行 7 分钟；命令输出 `awaiting_scan` 和 `qr_path` 后仍会运行到成功或失败。不要使用 shell `&`、`nohup` 或 `setsid`，不要并发启动多个登录。
3. 使用当前会话的图片发送工具，把 `qr_path` 指向的 PNG 作为图片发给用户，然后**停止业务操作并等待用户回复已扫码/已确认，同时保持原登录执行会话运行**。二维码路径按任务生成，不猜测固定文件名。脚本只生成图片，不代发飞书或微信消息。不要仅发路径给远程用户，也不要把登录二维码发给其他人。
4. 用户确认后另行运行 `xhs-publish login-confirm`。退出码 0 且 `ok: true` 才算登录成功；`LOGIN_PENDING` 仅表示后台任务存活且尚未取得最终结果，不能据此断言用户没有扫码或确认。进程退出、原命令结束、任务超时或状态损坏会返回具体错误；不要继续展示旧码或查询已失败的任务。失败后按原授权重新运行 `login` 并发送新图片。登录成功后会话原子落盘；旧会话只有新登录验过且仍属于当前有效任务时才替换。

二维码图片是短期临时文件，登录结束会删除；每个任务单独管理自己的图片。后台日志在 `~/.openclaw/logs/xhs-creator-login.log`；不向用户转发日志。`xhs-publish check` 使用签名 `user/info` 验证，不反复扫码排查非认证错误。查看登录帮助用 `xhs-publish login --help`；帮助和未知选项均不发起登录。Creator 若要求额外安全验证，保留原始提示并暂停业务，不调用 `xhs-hunter verify-*` 续接独立的 Creator 任务，不循环扫码或重复发布。

登录日志与 `xhs-creator-observe.jsonl` 均按 5 MiB 轮转，各保留 `.1`–`.3` 三份备份，连同当前文件每组最多约 20 MiB；后台登录执行期间也会持续轮转。

## 彻底清空本地账号与换号

用户要求彻底清空本地小红书账号时，先结束小红书业务请求和后台扫码任务，再删除创作者端 `~/.openclaw/logins/xhs-creator-local.json` 与采集端 `~/.openclaw/logins/xhs-pc-local.json`、对应登录状态及二维码、含凭据的备份；设置了 `XHS_CREATOR_SESSION_FILE` 或 `XHS_PC_SESSION_FILE` 时清理其实际路径，保留业务数据和其他平台会话。换号时先结束旧扫码任务，再按本节流程用目标账号重新登录；需要保留旧号时先将其会话以 0600 权限备份，不保留时先清空。创作者端与采集端独立登录，整体换号还须按 `xhs-hunter` 的登录流程切换采集端，确认两端均由目标账号扫码，并分别运行 `xhs-publish check` 和 `xhs-hunter check` 验证；只重登一端不会切换另一端。

## 发布

```bash
xhs-publish --mode image --title "标题" --body @/绝对路径/body.txt --images /绝对路径/1.png /绝对路径/2.png
xhs-publish --mode video --title "标题" --body @/绝对路径/body.txt --video /绝对路径/video.mp4 --cover /绝对路径/cover.jpg
# 笔记含 AI 合成内容时，在对应发布命令末尾加 --ai-declaration
```

先把已确认的纯正文和话题写入 UTF-8 `body.txt`，使用 `--body @/绝对路径/body.txt`；路径含空格时把整个参数加引号：`--body "@/绝对路径/作品目录/body.txt"`。脚本读取文件后校验长度、整理话题，保留文件中的真实换行和有意写下的 `\n`；文件缺失、不是普通文件或不是 UTF-8 时返回 `BODY_FILE_INVALID`，不提交。不要把含标题、分节说明的 `note.md` 整份作为正文，不用 `$(cat ...)` 或把多行正文拼进命令。短正文仍可直接传文字；仅此模式兼容归一化字面量 `\n`。以 `@` 开头的参数一律按文件路径处理。

标题 1–20 字，正文 1–1000 字；图文需 1–18 张图片，视频需 `--video`。`--topics` 可补充话题，合计最多 10 个；`--private` 设为仅自己可见。笔记含 AI 合成内容时加 `--ai-declaration`，发布请求会带上创作者端的“笔记含 AI 合成内容”声明；纯实拍内容不加。正文中的 `#话题` 自动整理为 Creator 可识别的内联话题格式。

发布前核对用户已认可的标题、正文、图片顺序及可见性；已有授权不重复索要同一批准。提交成功必须同时有 `ok: true` 和 `note_id`，再记录返回的 `url`。成功回执的 `status: submitted`、`accepted:true` 表示平台已接受；播放核实可以另行完成，不能把它退回“发布失败”或要求重发。

失败按回执处理：

| 回执 | 含义与处理 |
|---|---|
| `TOPIC_NOT_FOUND` / `TOPIC_LOOKUP_FAILED` | `stage:topics`、`submission_attempted:false`，话题在上传前核对。按原授权修正标签；不存在的标签可经已有授权改为普通正文，保留内容意图，不自动选相似话题 |
| `PRE_SUBMISSION_FAILED` | 看 `stage`（upload/location/payload/sign 等），笔记 POST 未开始；媒体可能已上传。修正对应问题后在原授权内继续，不要求用户在 App 查一条尚未提交的作品 |
| `VIDEO_READINESS_UNCONFIRMED` | 媒体已上传但未提交笔记，按 readiness 处理 |
| `SUBMISSION_UNKNOWN` | 笔记 POST 已开始或调用阶段无法确认，不能重发；按下节核查 |
| `SUBMISSION_UNCONFIRMED` | 平台已接受但 ID 缺失，先恢复 ID 与记录，不能重发 |
| `PUBLISH_REJECTED` | 平台明确拒绝，按错误码修正 |

回执中的 `attempt_id` 关联本次调用，`stage`、`submission_attempted`、`media_uploaded` 用于交接，不用“发生异常”推断是否发布。`TITLE_INVALID` 等本地参数错误尚未上传或提交，按既有认可范围修正即可；只有内容、账号或可见性超出原授权时才补充确认。

发布 Workflow 负责判断内容是否需要 AI 声明，并在调用发布命令时传入 `--ai-declaration`。

视频转码与笔记提交分别判断：`readiness.state:ready` 表示查询返回就绪证据；Creator 会话缺少 www 查询认证时允许服务端异步转码提交，但返回 `readiness_unknown/auth_unavailable`。网络、服务错误、空数据和持续 pending 不按 ready 处理，提交前停止并返回 `VIDEO_READINESS_UNCONFIRMED`、`submission_attempted:false`。`accepted:true` 与作品 ID 只证明平台接受，`public`/`playable:null` 仍需核实；不要因可播放未知自动重发。

`auth_unavailable` 表示转码查询需要的 PC 网页认证不可用，不据此要求重新登录 Creator，也不拼接采集端 Cookie。已接受的笔记先用 `xhs-engagement list` 按真实作品 ID 只读核对本人列表；列表可能滞后，其存在本身也不足以确认公开可见或可播放。把原作品链接交用户在 App 打开核实，明确记录核实范围；没有公开或播放证据时继续保留未知，不自动重发或修改可见性。

对用户报告时先说明平台已接受和真实作品链接，再将 `auth_unavailable` 解释为“工具未能查询转码状态”，不称为发布失败或发布登录失效。用户已经明确确认发布成功时，按用户确认结案并报告成功，不重复要求打开 App 或再次确认；机器未核实的 `public` / `playable` 字段不自动改成 true。

## 提交结果不确定时

`SUBMISSION_UNKNOWN`（包括 `curl: (28) Operation timed out`）表示无法确认结果；`SUBMISSION_UNCONFIRMED` 表示平台返回成功但缺少作品 ID。两者都不能当作发布失败，**不要自动重发**，也不要因创作者列表未出现目标笔记就重发。

- 用现有 `xhs-engagement list` 查看当前账号的已发作品。候选笔记须结合账号、标题和实际内容核实；同名多条时不能自动取第一条。确认目标笔记后保留真实作品 ID 和链接，不再次提交。
- 列表可能滞后，没查到仍属于待核实。停止发布重试，请用户在 App 核对（必须用app，不可同时登陆网页端创作者后台，会造成平台风控）；用户确认已发布，就按此确认报告最终成功，不再反复询问是否发布或要求重发。有链接时恢复记录；缺少 ID/链接时继续只读取链，不编造。只有用户核实确实未发布并明确要求重试，才重新提交；接受正常自然语言，不要求复述固定口令。触发风控时遵守 `expert-xhs` 的限频和停手规则。
- 确认成功后的记录沿用 `published-track`，先查询是否已有对应记录。补录使用原作品目录、实际发布日期和发布账号，内容类型与原图文 / 视频一致；历史发布显式传 `--publish-date`，不要把补录日当作发布日。同一目录和发布日的 `record` 会更新原行；不要新造目录或日期造成重复记录。分发状态按实际需求填写，不因超时恢复就统一设为无需分发。

操作结果写入 `~/.openclaw/logs/xhs-creator-observe.jsonl`：提交前错误对应 `not_submitted`，`SUBMISSION_UNKNOWN` 对应 `unknown`，成功但无 ID 对应 `unconfirmed`；包含阶段和调用关联 ID，不含正文或 Cookie。日志只说明本次请求结果，不能代替平台侧核实或用户后续确认。

委派执行时回传成功链接/记录 ID，或失败阶段、是否尝试提交、回执位置和下一步；结果待核实也须及时回报父任务，不能只等成功链接。main 统筹多平台发布时逐项回报当前状态，当前平台结束后继续其余已授权平台。

当前 HTTP 单次请求超时为 120 秒，媒体上传与发布提交均使用该设置；这不是整轮发布的总时限。若仍报约 15000 毫秒超时，请 IT engineer 核查实际加载版本和外层超时限制，不要由发布智能体临时改共享库来反复重试。即使延长超时，结果不确定时仍按上面的核查规则处理。
