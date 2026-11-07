# 抖音图文 HTTP 发布

使用 `douyin-publish note run --images ... --title ... --caption @正文文件 --original-sound`，按给定顺序上传图片。默认声明 AI，非 AI 内容可用 `--declaration none`；本入口只支持原声，不提供浏览器配乐选择或表单编辑。

不带 `--confirm` 只预览；已有授权后加 `--confirm`。要先上传准备，加 `--prepare-only`，再用 `note publish --confirm` 提交原任务。准备、收据与验证规则见 [HTTP 发布](http.md)。

`note status/resume/get-link` 核查同一任务。未知结果不根据标题猜最新作品或再次发布；用户确认时用 `note close` 提供完整链接及确认原文。作品 ID 确认后再调用 `published-track record`，公开、播放与审核状态分别核实。
