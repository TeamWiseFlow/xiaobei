---
name: kuaishou-publish
description: 快手内容发布：脚本预览、媒体上传、提交结果保存和 published-track 入库。
---


# 快手发布

**本版本快手视频固定采用「先发私密作品，再把简介交给用户手动补齐并公开」的协作流程。** 接到视频发布任务时说明这一限制；已有该流程的发布授权就直接执行，不逐条重复询问是否改走私密暂存。具体顺序：

1. 准备成片与最终简介（含话题），保留简介供交付；平台提交为空简介、`--visibility private`。
2. 按下述方式本地预览，按需登录，再加 `--confirm` 提交私密作品。
3. 确认私密提交结果后，把**完整可复制的简介正文（含话题）直接发给用户**，同时说明：请在快手 App 找到这条私密作品，手动补简介、按需完成平台声明，再自行改为公开。不能只给简介文件路径或让用户自行找文案。
4. 如实告知审核/作品识别状态，保留原收据与发布记录；用户完成公开后沿用原记录核实，不另发一条作品。

**话题上限：快手平台单条视频描述最多支持4个 hashtag（`#话题`）。准备和交付简介时先核对数量，超过4个须精简至4个以内；交给用户在 App 手动补填的简介同样适用。**

索取扫码前，先按目标内容运行不带 `--confirm` 的发布预览，完成媒体、可见性、简介和参数能力检查。预览不访问平台；通过后才检查 `kuaishou-publish check`，需要登录时使用 `kuaishou-hunter login`。

`kuaishou-publish methods` 返回支持参数及取值。

```bash
kuaishou-publish publish --text @/绝对路径/body.txt --image /绝对路径/image.jpg --source-folder /绝对路径/kuaishou/outputs/作品 --account default
kuaishou-publish publish --text @/绝对路径/body.txt --image /绝对路径/image.jpg --source-folder /绝对路径/kuaishou/outputs/作品 --account default --confirm
```

默认只预览，不访问平台。多行正文先保存为 UTF-8 纯正文文件，用 `--text @/绝对路径/body.txt` 由脚本读取；不要用 `$(cat ...)` 或将多行文案拼进命令。路径含空格时给整个 `@路径` 参数加引号；文件只放正文和话题。媒体用真实本地文件。`--record-title` 可指定记录标题。视频与图集二选一；图集 1–31 张、每张不超过 15MB，可见范围 public/private/friends。没有 --cover/--mention/--poi 等选项。私密图集接口有平台验证记录；没有自动删除接口。

视频接口目前仅覆盖空简介、仅自己可见、立即发布的分支，已实号确认可提交并进入审核。审核通过与实际可见仍须分别核查。已有上述协作流程的发布授权时使用：

```bash
kuaishou-publish publish --video /绝对路径/video.mp4 --visibility private --record-title "测试记录标题" --source-folder /绝对路径/kuaishou/outputs/测试 --account default
```

`--record-title` 只用于本地记录，不向平台提交标题。视频不要传 `--title`、非空 `--text`、`--tag`、`--topic` 或 `--schedule`；未指定 `--visibility private` 也会在上传前拒绝。正式公开视频及带简介的视频交用户在原平台完成，不建议靠养号、等待或改参数绕过未支持的分支。

参数支持范围以 `kuaishou-publish methods` 的 constraints 为准，本地能力限制应明确说明来源，不能表述成平台已拒绝本轮内容。

私密视频暂存默认 `distribute_status=1`（当前无需分发）；有实际分发计划时可显式传 `--distribute-status 0`，2 表示已分发。该参数仅用于本地记录，不提交平台；其他发布分支保持 published-track 原默认值，补录时按实际需求填写。

核对文本、媒体、账号、可见范围与声明后，已有发布授权时加 --confirm。

对通过聊天预览确认的成片，先用 `video-edit` 的发布版本流程登记确认，再给发布预览和提交命令传母带 `--video` 与 `--video-approval`。核对结果随 `publish-result.kuaishou.json` 保留。

脚本串行发布并保存 `publish-result.kuaishou.json`。平台明确接受提交、且取得创作者作品 ID 后可入库；私密/审核中的数字 `publishId` 或 `workId` 不等于公开短链 ID，`url:null` 不表示发布失败，不拼造 `/short-video/<数字ID>` 分享链接。无公开链接时 published-track 仍记录作品目录、账号和创作者 ID（保存在 notes 的 platform_runtime 字段），供本人取数匹配；以后取得真实公开链接再补入库。

`published:true, recorded:false` 表示作品已识别、记录失败，重跑同一目录只补入库。`accepted:true, resolution_pending:true` 表示平台已接受提交，但作品 ID 尚待确认；保存 accepted 收据，不能将上传 fileId 当作品 ID，先检查 `kuaishou-engagement list` 或原平台，不重发。已有 submitting/unknown 结果文件时禁止重发，先核查并由用户确认结果；不要删除收据换目录重发。下一条独立作品使用新的作品目录。

提交结果与实际可见、审核通过分开记录。返回失败、风控或超时后停止，不换通道重发。发布调用和结果文件不负责平台指标采集。

兼容字段 `published:true` 表示已取得可记录的作品 ID。实际状态看 `result.publication` 的 `accepted`、`id_resolved`、`private`、`public`、`review_pending`、`playable`；null 表示未验证。`ownership_status:ownership_unverified` 表示主站登录 ID 与创作者作者 ID 的映射尚未验证，不能凭同昵称或跨命名空间字符串直接认定同号/错号。用户在 App 完成公开后，用 `kuaishou-engagement` 取本人作品核实并沿用原记录补充。

失败时查看返回的 `diagnostic` 和收据中的 `error_message` / `diagnostic`：保留脱敏消息、平台 result、HTTP 状态、请求阶段与路径；不含原始响应正文或凭据。只有 `RISK_CONTROL` 或平台明确说明验证/风控时才按风控处理，裸 `UPSTREAM` 不能据此判断。私密作品核查使用 `kuaishou-engagement list` 的创作者会话；公开 hunter 列表为空不能证明提交失败。保留收据，不自行删除后重发。
