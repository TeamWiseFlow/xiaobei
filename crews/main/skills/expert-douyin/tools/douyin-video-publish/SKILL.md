---
name: douyin-video-publish
description: 通过 Camoufox 持久化 session douyin 在创作者中心上传、填表、标注 AIGC、发布视频并取链。
---

# 抖音视频发布

前置执行 `douyin-publish check`，未登录用 `douyin-publish login` 打开有头窗口完成登录。登录态只留在 Camoufox profile，不使用 login-manager 或 API cookie。

完整流程优先使用 `douyin-publish video --video /绝对路径/video.mp4 --title "标题" --caption "简介 #话题"` 预览；已有发布授权时加 `--confirm`。全流程由脚本保存中间态并执行。

需要页面诊断或分步处理时：

```bash
douyin-video-publish open-page
douyin-video-publish upload --video /绝对路径/video.mp4
douyin-video-publish fill --session douyin --title "标题" --caption "简介 #话题"
douyin-video-publish publish --session douyin
douyin-video-publish get-link --session douyin
```

`publish` 和 `run` 会实际发布，必须先核对目标和文案并取得授权。分步共享 session `douyin`；不改 session 名，不并行发布或取数。AIGC 声明失败即停；不要删除声明绕过。

完整流程结束关闭进程、保留持久 profile。exit 2 表示需在同一 profile 重新登录；exit 3 或超时代表结果未确认，到管理页核实并用 `get-link` 取链，禁止自动重发。只在确认作品 ID 和公开链接后记录成功。
