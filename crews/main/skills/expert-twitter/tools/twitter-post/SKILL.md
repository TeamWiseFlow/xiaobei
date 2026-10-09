---
name: twitter-post
description: X/Twitter内容发布：脚本预览、媒体上传、提交结果保存和 published-track 入库。
---

# X/Twitter发布

登录使用 `x-hunter login/export`，执行前检查 `twitter-post check`。

`twitter-post methods` 返回普通发帖与长文的支持参数及取值。

```bash
twitter-post publish --text "正文" --source-folder /绝对路径/twitter/outputs/作品 --account default
twitter-post publish --text "正文" --source-folder /绝对路径/twitter/outputs/作品 --account default --confirm
```

**未订阅或未确认 X Premium 长推权限时，每条正文必须保持在 280 权重内。超过该值会自动走长推通道，未开通权限的账号会被平台拒绝；不要用提交失败来试探订阅权限。**

先检查预览的 `text_check.posts`：每条包含 `position`、`weighted_length` 和 `mode`（standard/long）。`requires_premium:true` 时同时返回 `warnings`；`premium_status:not_checked` 表示工具没有验证账号订阅，`twitter-post check` 也仅验证登录态。权限未确认或未订阅时，先精简超限正文再预览；改为帖串须核对并批准完整帖串，不能自动拆帖提交。帖串的每一条分别计算权重，不能只检查首条。

中文通常按每字2权重，纯中文约140字已达上限；空格、标点、话题、手动 @提及和链接也要计入。常见拉丁字母/数字通常为1，emoji通常为2，识别出的链接按23权重。不要使用普通字符数或“约140字”代替预览检查，建议留余量。预览沿用当前发布路由的计数函数，边界与特殊 Unicode/链接形式以平台实际判断为准。规则参考 [官方计数说明](https://docs.x.com/fundamentals/counting-characters) 与 [长推订阅要求](https://help.x.com/en/using-x/types-of-posts)。

默认只预览，不访问平台。`--text @/绝对路径/content.md` 读取正文文件；媒体用真实本地文件。`--record-title` 可指定记录标题。最多4张图片，图片和视频互斥；--thread 可重复，媒体与 --quote 只作用于首条。`--article` 发布 Markdown Articles，需要当前账号具备 Articles 权限；该能力与长推分开确认，参见 [官方 Articles 权限说明](https://help.x.com/en/using-x/articles)。长推、Articles 和视频上传须分别核验，不能用普通图文发布成功推断这些分支可用。普通回复由 expert-bd 的 twitter-interact comment 执行。

独立发帖间隔至少30分钟，单日不超过50帖；这是本工具的操作上限，不代表平台保证不会限频。长文 Markdown 的相对插图路径以正文文件所在目录解析，预览时核对插图与封面。Thread 中途失败时可能已有前几条发布，先在原平台核查，不重发整个帖串。

核对文本、媒体、账号、可见范围与声明后，已有发布授权时加 --confirm。需要平台 AI 声明而接口没有声明字段时停止，交用户在原平台完成；不要将简介里的“AI”字样当作平台声明。不要填不存在的参数或模拟上传成功。

脚本串行发布并保存 `publish-result.x.json`，返回真实作品 ID 与 URL 后自动调用 published-track record，关联作品目录的 dna-meta.json 和账号 alias。`published:true, recorded:false` 表示内容已发出、记录失败，重跑同一目录只补入库。已有 submitting/unknown 结果文件时禁止重发，先检查本人作品或原平台并由用户核实结果。下一条作品使用新的作品目录。

提交结果与实际可见、审核通过分开记录。返回失败、风控或超时后停止，不换通道重发。发布调用和结果文件不负责平台指标采集。

遇到 `Blue claim is not enabled for note tweet`，按长推订阅权限不足处理，不当作 Cookie 失效或要求重新登录。已有 unknown 收据时仍先核查结果，不能删收据后换短文重发；确认结果后按发布记录规则处理新作品。
