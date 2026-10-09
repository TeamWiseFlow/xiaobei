---
name: tiktok-publish
description: TikTok内容发布：脚本预览、媒体上传、提交结果保存和 published-track 入库。
---

# TikTok发布

登录使用 `tiktok-hunter login/export`；写会话准备与 `--require-write` 导出按 hunter 说明执行。发布前检查 `tiktok-publish check`。

`tiktok-publish methods` 返回支持参数及取值。check 会先检查同次写会话材料，缺项时不访问平台；只读采集仍可用 tiktok-hunter。

```bash
tiktok-publish publish --text "简介" --video /绝对路径/video.mp4 --cover /绝对路径/cover.jpg --source-folder /绝对路径/tiktok/outputs/作品 --account default
tiktok-publish publish --text "简介" --video /绝对路径/video.mp4 --cover /绝对路径/cover.jpg --source-folder /绝对路径/tiktok/outputs/作品 --account default --confirm
```

默认只预览，不访问平台。`--text @/绝对路径/content.md` 读取正文文件；媒体用真实本地文件。`--record-title` 可指定记录标题。视频与图文二选一，视频必须给 --cover。可见范围 public/private/friends。支持 --allow-comment/--allow-duet/--allow-stitch/--allow-content-reuse/--allow-ai-remix on|off；这些复用选项不等于 AI 内容声明。所有发布需同次 ticket-guard 材料，真实发布待验收。

核对文本、媒体、账号、可见范围与声明后，已有发布授权时加 --confirm。需要平台 AI 声明而接口没有声明字段时停止，交用户在原平台完成；不要将简介里的“AI”字样当作平台声明。不要填不存在的参数或模拟上传成功。

脚本串行发布并保存 `publish-result.tiktok.json`，返回真实作品 ID 与 URL 后自动调用 published-track record，关联作品目录的 dna-meta.json 和账号 alias。`published:true, recorded:false` 表示内容已发出、记录失败，重跑同一目录只补入库。已有 submitting/unknown 结果文件时禁止重发，先检查本人作品或原平台并由用户核实结果。下一条作品使用新的作品目录。

提交结果与实际可见、审核通过分开记录。返回失败、风控或超时后停止，不换通道重发。发布调用和结果文件不负责平台指标采集。
