---
name: douyin-video-publish
description: 通过 Camoufox 持久化 session douyin 上传视频、真实键盘填表、设置横竖双封面、标注 AIGC、发布与短信验证续接，并核查本次作品链接。
---

# 抖音视频发布

前置执行 `douyin-publish check`，未登录用 `douyin-publish login` 完成登录。登录态只留在 Camoufox profile，不使用 login-manager 或 hunter 的 API 会话。

完整流程优先使用统一入口预览，已有发布授权时加 `--confirm`：

```bash
douyin-publish video --video /绝对路径/video.mp4 --title "标题" --caption "简介 #话题" --cover-vertical /绝对路径/cover-vertical.jpg --cover-horizontal /绝对路径/cover-horizontal.jpg
```

必须提供竖封面和横封面。按 **3:4 竖封面 + 4:3 横封面**制作，两张都要核对；关键文字避开四周 15% 边缘区。比例不符时脚本等比缩放、补浅灰底，保留完整内容；不要居中裁切导致边缘文字缺失。补底不能代替平台的文字安全区检测，出现 `COVER_TEXT_UNSAFE` 时修改封面后再设置。

上传必须等视频可播放且上传/转码状态结束，不能把标题框出现当作上传完成。脚本通过真实键盘输入并读回标题和简介；提交前检查视频、标题、双封面与 AIGC 声明，任一缺失停止。

简介按完整正文校验，忽略 Slate 话题节点引入的 Unicode 空白和不可见格式字符；短标题、空简介和短信验证码同样支持。设置封面后若视频元素消失，脚本只在已确认的当前草稿页重开一次，等待视频恢复，再核对视频时长、标题、简介、双封面及 AIGC 声明。返回 `DRAFT_CHANGED_AFTER_COVER` 时保留页面核查，不重传或提交。

需要页面诊断或分步处理时，用对应 wrapper 子命令。各步骤的中间态由脚本保存，不自行拼 JS、file input 序号或发布结果：

| 操作 | 命令 |
|---|---|
| 打开上传页 | `douyin-video-publish open-page` |
| 上传视频并等待就绪 | `douyin-video-publish upload --video /绝对路径/video.mp4` |
| 续编未提交草稿 | `douyin-video-publish edit-draft` |
| 在当前草稿补传缺失视频 | `douyin-video-publish upload --resume-draft --video /绝对路径/video.mp4` |
| 填表和声明 | `douyin-video-publish fill --title "标题" --caption "简介 #话题"` |
| 上传并保存双封面 | `douyin-video-publish cover --cover-vertical /绝对路径/vertical.jpg --cover-horizontal /绝对路径/horizontal.jpg` |
| 检查当前页面与任务 | `douyin-video-publish status` |
| 校验后实际提交 | `douyin-video-publish publish` |
| 核查本次提交结果 | `douyin-video-publish resume` 或 `douyin-video-publish get-link` |

`publish` 和 `run` 会实际发布，先核对账号、成片、双封面及文案并取得授权。共享持久化 session `douyin`，不改 session 名，不并行发布或取数。AIGC 声明失败即停，不删除声明绕过。发现旧草稿返回 `DRAFT_PRESENT`，不自动放弃；续编前核对草稿与本次成片。

补传视频可能重建表单，清空标题、简介、封面和 AIGC 声明；`upload --resume-draft` 后重新执行 `fill` 和 `cover`，再 `publish`。封面上传超时时直接续编当前页面；脚本为每次上传重新观察预览，不使用上次运行的 localStorage 图像列表。

## 短信验证与结果核查

返回 exit 4 / `SMS_VERIFICATION_REQUIRED` 表示本次提交等待用户验证，**没有确认发布成功**。脚本保留浏览器页面和提交上下文，不重跑 upload/run，不重复点发布，不调用 `douyin-publish check/login` 关闭或重开验证页。

- 用 `douyin-video-publish verify-send` 真实点击「获取验证码」，核对页面倒计时；工具不会自动重复发送。
- 请用户提供验证码，将其写入当前用户拥有、权限 `0600` 的普通文件；用 `douyin-video-publish verify-code --code-file /绝对路径/私有验证码文件` 真实键盘输入并点击「验证」。验证码不放命令参数、报告、记忆或 Git，使用后删除临时文件。
- 用户也可在当前窗口完成验证，再执行 `douyin-video-publish resume`。续接只验证与核查原提交，不重新发布。

exit 2 表示需要恢复登录；exit 3 / `unconfirmed` 表示结果未确认，先用 `resume/get-link` 核查原任务，再检查管理页和草稿，禁止自动重发。提交过的任务未结案时会阻止新的上传、填表和发布。

未结案任务也会阻止普通登录、取数和图文操作关闭共用浏览器。仅验证页面已丢失或登录失效时，用 `douyin-publish login --resume-video` 恢复原账号，再 `resume` 核查原提交。提交记录会保留，当前短信弹窗仍在时恢复入口拒绝关闭它。

仅人工核实管理页没有本次作品、确认原提交未发布后，使用 `edit-draft --confirm-unpublished` 结案并续编。工具会先查询本次作品，若已经发布则返回确认的链接；短信验证仍在时不清除任务。不要把超时当作“确认未发布”。

`get-link` 只核查保存的本次提交：按提交前作品 ID、提交时间与完整标题筛选；没有提交记录、无匹配或有多个候选都不返回旧作品作为成功。仅 `state: published` 且有完整 ID 和 `/video/` URL 时记录成功。运行状态保存在 `~/.camoufox-cli/publications/douyin-video.json`，仅含任务资料，不保存登录凭据；不要手工删除未结案状态以重发。

正常完整发布后关闭浏览器、保留 profile；准备失败、等待验证或结果未知时保留当前页面。
