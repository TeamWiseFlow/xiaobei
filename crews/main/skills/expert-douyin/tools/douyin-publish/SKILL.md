---
name: douyin-publish
description: 抖音独立 API 视频与图文发布、上传、封面及发布结果核查。
---

# 抖音发布

先执行 `douyin-hunter check`，确认独立 API 会话；需要验证创作者资料读取时执行 `douyin-publish call creator_profile`。写操作还要求该会话的安全材料和创作者域 CSRF 握手。工具在上传前验证发布材料；失败时使用 `douyin-login` 或交 IT engineer 修复，不开启旧浏览器。

```bash
douyin-publish video --video /绝对路径/video.mp4 --cover /绝对路径/cover.jpg --title "标题" --caption "简介 #话题"
douyin-publish note --images /绝对路径/1.jpg /绝对路径/2.jpg --title "标题" --caption "正文 #话题"
```

默认预览。用户已确认内容并要求发布后，在同一命令加 `--confirm`。默认公开可见；`--visibility 1` 仅自己可见，`2` 好友可见。`--timing` 为未来的秒级 Unix 时间戳，`--no-download` 关闭保存权限。视频标题 ≤30 字，图文标题 ≤20 字；描述 ≤1000 字；图文 1–35 张、单张 ≤50MB。默认按 `aigc` 申明，纯实拍且无需声明才传 `--declaration none`。音乐只接受核实可用的平台 `--music-id`；不编造歌曲或推荐结果。

需要话题、提及、活动、地点、合集或热点等实际平台元数据时传 `--options-file /绝对路径/options.json`，使用 challenges、mentions、activity、poi、mix_id、hot_spot 字段；不要编造 ID。视频还支持 cover_delay、cover_tools_extend_info、cover_tools_info、chapter，图文支持已上传的 cover_uri。工具将这些字段一并预览；文件不能覆盖账号、发布任务 ID、安全材料或最终提交地址。

上传在本机完成：申请短期凭据、申请上传节点、分片上传、校验与提交。媒体字节不发给 Relay；Relay 只处理上传凭据与请求元数据。视频处理检测、封面与作品提交使用创作者 API。

任务文件保存在 `~/.openclaw/douyin-api/publish/`，权限 0600。账号任务串行，每 24 小时最多 5 次作品提交。提交前保存 `submission_unknown`，网络错误或中断不会自动重发；只有拿到平台确认的作品 ID 和 URL 才报告成功。

```bash
douyin-publish status --job-file /受控目录/job-返回的ID.json
```

结果未知时使用本人作品列表核查最近 50 条作品，按账号、标题及发布时间筛出候选；候选不代表发布成功，列表也不保证包含私密或审核中的作品。不得按列表首条、近似标题、首屏缺失或超时直接结案。未知提交会阻止同账号再次发布，先核实并处理任务状态。确认发布后用 `published-track record` 记录，再使用 `douyin-engagement` 取公开互动量。

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
