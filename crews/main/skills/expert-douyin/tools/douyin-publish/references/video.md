# 抖音视频 HTTP 发布

使用 `douyin-publish video run`，传入视频、标题、正文和双封面；完整流程及二次验证见 [HTTP 发布](http.md)。缺少视频、标题、任一封面或 AI 声明即停止。封面按 3:4 与 4:3 等比补底，不裁掉边缘文字。

`run --confirm --prepare-only` 只上传并准备请求，`publish --confirm` 才提交保存的任务。`status` 不打开浏览器或访问平台，`resume/get-link` 只读核查原提交；等待处理、验证或结果未知时不重复上传和发布。

历史浏览器任务由维护者明确选择旧收据核查。旧 `video status` 在浏览器未运行时只返回本地收据与 `page_checked: false`，不会启动、导航或关闭浏览器。`receipt_submission_attempted` 描述历史任务，`current_action_submission_attempted: false` 表示本次查询没有发布；已结案记录不要求重登。旧模式只接受视频 `status/resume/get-link/close`，不再接受新登录、填表或发布。

`close --outcome published --url "完整链接" --confirmation "用户确认原文" --confirm` 按用户确认结案；`cancelled` 只取消本地任务，不撤回线上作品，也不证明原提交未发布。缺少确认参数只预览。
