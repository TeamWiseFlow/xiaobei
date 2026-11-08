---
name: twitter-post
description: X/Twitter内容发布：脚本预览、媒体上传、提交结果保存和 published-track 入库。
---

# X/Twitter发布

登录使用 `x-hunter login/export`，执行前检查 `twitter-post check`。

`twitter-post methods` 返回普通发帖与长文的支持参数及取值。

```bash
twitter-post publish --text @/绝对路径/body.txt --source-folder /绝对路径/twitter/outputs/作品 --account default
twitter-post publish --text @/绝对路径/body.txt --source-folder /绝对路径/twitter/outputs/作品 --account default --confirm
```

**未订阅或未确认 X Premium 长推权限时，每条正文必须保持在 280 权重内。超过该值会自动走长推通道，未开通权限的账号会被平台拒绝；不要用提交失败来试探订阅权限。**

先检查预览的 `text_check.posts`：每条包含 `position`、`weighted_length` 和 `mode`（standard/long）。`requires_premium:true` 时同时返回 `warnings`；`premium_status:not_checked` 表示工具没有验证账号订阅，`twitter-post check` 也仅验证登录态。权限未确认或未订阅时，先精简超限正文再预览；改为帖串须核对并批准完整帖串，不能自动拆帖提交。帖串的每一条分别计算权重，不能只检查首条。

中文通常按每字2权重，纯中文约140字已达上限；空格、标点、话题、手动 @提及和链接也要计入。常见拉丁字母/数字通常为1，emoji通常为2，识别出的链接按23权重。不要使用普通字符数或“约140字”代替预览检查，建议留余量。预览沿用当前发布路由的计数函数，边界与特殊 Unicode/链接形式以平台实际判断为准。规则参考 [官方计数说明](https://docs.x.com/fundamentals/counting-characters) 与 [长推订阅要求](https://help.x.com/en/using-x/types-of-posts)。

默认只预览，不访问平台。多行正文先保存为 UTF-8 纯正文文件，用 `--text @/绝对路径/body.txt` 由脚本读取；不要用 `$(cat ...)` 或将多行文案拼进命令。路径含空格时给整个 `@路径` 参数加引号；文件只放正文和话题。媒体用真实本地文件。`--record-title` 可指定记录标题。最多4张图片，图片和视频互斥；--thread 可重复，媒体与 --quote 只作用于首条。`--article` 发布 Markdown Articles，需要当前账号具备 Articles 权限；该能力与长推分开确认，参见 [官方 Articles 权限说明](https://help.x.com/en/using-x/articles)。长推、Articles 和视频上传须分别核验，不能用普通图文发布成功推断这些分支可用。普通回复由 expert-bd 的 twitter-interact comment 执行。

独立发帖间隔至少30分钟，单日不超过50帖；这是本工具的操作上限，不代表平台保证不会限频。长文 Markdown 的相对插图路径以正文文件所在目录解析，预览时核对插图与封面。Thread 中途失败时可能已有前几条发布，先在原平台核查，不重发整个帖串。

Articles 中独占普通段落一行的完整 X/Twitter 帖子链接会嵌入为帖子卡片；正文中的行内链接、引用块和代码块保持原格式。嵌入使用链接里的完整数字帖子 ID，不截断、不替换目标。

核对文本、媒体、账号、可见范围与声明后，已有发布授权时加 --confirm。需要平台 AI 声明而接口没有声明字段时停止，交用户在原平台完成；不要将简介里的“AI”字样当作平台声明。不要填不存在的参数或模拟上传成功。

脚本串行发布并保存 `publish-result.x.json`，返回真实作品 ID 与 URL 后自动调用 published-track record，关联作品目录的 dna-meta.json 和账号 alias。`published:true, recorded:false` 表示内容已发出、记录失败，重跑同一目录只补入库。已有 submitting/unknown 结果文件时禁止重发，先检查本人作品或原平台并由用户核实结果。下一条作品使用新的作品目录。

失败时同时检查 `stage`、`submission_attempted`、`failure_reason` 与脱敏 `diagnostic`：

- `ACCOUNT_SUSPENDED`：上游明确返回账号暂停（如 HTTP 403、code 64）。停止本轮操作，交用户处理账号状态，不当作 Cookie 过期要求重登。
- `AUTH_REQUIRED` / `AUTH_EXPIRED`：认证失败。HTTP 403 本身不能证明认证过期，应结合平台错误码。
- `MEDIA_UPLOAD_FAILED`：媒体上传或元数据准备失败；`submission_attempted:false` 明确表示尚未提交帖子，保存为 `state:failed`，不能报告“帖子发布结果未知”。
- `PUBLISH_UNKNOWN`：可能已经发送帖子提交请求；保留收据并核查本人作品，禁止重发。进程失联且无法证明提交尚未开始时，也按此处理。

`stage:media_upload` 仍可能伴随 `submission_attempted:true`：帖串前几条可能已提交，后续才上传失败；不能据最后一次上传错误清除既有提交事实。已有 submitting/unknown 收据不会被新的账号状态或上传错误覆盖。`failed` 收据再次调用只返回原失败，不自动重试。

提交结果与实际可见、审核通过分开记录。返回失败、风控或超时后停止，不换通道重发。发布调用和结果文件不负责平台指标采集。

遇到 `Blue claim is not enabled for note tweet`，按长推订阅权限不足处理，不当作 Cookie 失效或要求重新登录。已有 unknown 收据时仍先核查结果，不能删收据后换短文重发；确认结果后按发布记录规则处理新作品。
