# Content Production
读取定位、业务知识和指定 DNA 文档/template，提出选题与传播理由。用 kuaishou-hunter 核查事实与素材，存 kuaishou/outputs/<作品>/；明确素材授权。文字/图文由 main 完成正文、图片顺序与首图，图像可用 awk-img-gen/native-ui-card；不机械复制其他平台标题与字数限制。视频全案只出 Brief 和口播稿，附素材绝对路径与验收标准后委托 content-producer；旁白由 CP 写。

落 dna-meta.json，核对成品、正文、账号、可见范围和 AI 声明。图集读取 kuaishou-publish 工具说明后预览，已有发布授权时 --confirm。视频接口只覆盖空简介、私密、立即发布的测试分支，仍需本机实号验收；正式公开视频及带简介的视频交用户在原平台完成，不将正式作品改成空简介私密发布。

检查真实 ID/URL、审核状态与 recorded 字段。未知结果查看脱敏诊断，核查本人列表与原平台，保留结果文件，不重发；列表为空不单独证明提交未发生。完成后按 Review 复盘，不附带任何未授权互动。
