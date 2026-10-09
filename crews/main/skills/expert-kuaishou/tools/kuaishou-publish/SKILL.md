---
name: kuaishou-publish
description: 快手内容发布：脚本预览、媒体上传、提交结果保存和 published-track 入库。
---


# 快手发布

登录使用 kuaishou-hunter login，执行前检查 `kuaishou-publish check`。

`kuaishou-publish methods` 返回支持参数及取值。

```bash
kuaishou-publish publish --text "简介" --image /绝对路径/image.jpg --source-folder /绝对路径/kuaishou/outputs/作品 --account default
kuaishou-publish publish --text "简介" --image /绝对路径/image.jpg --source-folder /绝对路径/kuaishou/outputs/作品 --account default --confirm
```

默认只预览，不访问平台。`--text @/绝对路径/content.md` 读取正文文件；媒体用真实本地文件。`--record-title` 可指定记录标题。视频与图集二选一；图集 1–31 张、每张不超过 15MB，可见范围 public/private/friends。没有 --cover/--mention/--poi 等选项。私密图集接口有平台验证记录；没有自动删除接口。

视频接口目前仅覆盖空简介、仅自己可见、立即发布的分支，已实号确认可提交并进入审核。审核通过与实际可见仍须分别核查。只在已有私密发布授权时使用：

```bash
kuaishou-publish publish --video /绝对路径/video.mp4 --visibility private --record-title "测试记录标题" --source-folder /绝对路径/kuaishou/outputs/测试 --account default
```

`--record-title` 只用于本地记录，不向平台提交标题。视频不要传 `--title`、非空 `--text`、`--tag`、`--topic` 或 `--schedule`；未指定 `--visibility private` 也会在上传前拒绝。正式公开视频及带简介的视频交用户在原平台完成，不建议靠养号、等待或改参数绕过未支持的分支。

核对文本、媒体、账号、可见范围与声明后，已有发布授权时加 --confirm。需要平台 AI 声明而接口没有声明字段时停止，交用户在原平台完成；不要将简介里的“AI”字样当作平台声明。不要填不存在的参数或模拟上传成功。

脚本串行发布并保存 `publish-result.kuaishou.json`。平台明确接受提交、且取得创作者作品 ID 后可入库；私密/审核中的数字 `publishId` 或 `workId` 不等于公开短链 ID，`url:null` 不表示发布失败，不拼造 `/short-video/<数字ID>` 分享链接。无公开链接时 published-track 仍记录作品目录、账号和创作者 ID（保存在 notes 的 platform_runtime 字段），供本人取数匹配；以后取得真实公开链接再补入库。

`published:true, recorded:false` 表示作品已识别、记录失败，重跑同一目录只补入库。`accepted:true, resolution_pending:true` 表示平台已接受提交，但作品 ID 尚待确认；保存 accepted 收据，不能将上传 fileId 当作品 ID，先检查 `kuaishou-engagement list` 或原平台，不重发。已有 submitting/unknown 结果文件时禁止重发，先核查并由用户确认结果；不要删除收据换目录重发。下一条独立作品使用新的作品目录。

提交结果与实际可见、审核通过分开记录。返回失败、风控或超时后停止，不换通道重发。发布调用和结果文件不负责平台指标采集。

失败时查看返回的 `diagnostic` 和收据中的 `error_message` / `diagnostic`：保留脱敏消息、平台 result、HTTP 状态、请求阶段与路径；不含原始响应正文或凭据。只有 `RISK_CONTROL` 或平台明确说明验证/风控时才按风控处理，裸 `UPSTREAM` 不能据此判断。私密作品核查使用 `kuaishou-engagement list` 的创作者会话；公开 hunter 列表为空不能证明提交失败。保留收据，不自行删除后重发。
