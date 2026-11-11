---
name: douyin-interact
description: 对抖音作品点赞、收藏、评论或回复评论；先预览目标与文字，再执行已确认的操作。
---

# 抖音作品互动

先用 `douyin-hunter fetch` 与 `douyin-hunter comments` 核实作品及目标评论。接口写入与采集、创作者共用 `douyin-hunter` 的 `douyin-login` API 会话。文字和目标必须由用户确认或来自用户已经批准的运营策略。

```bash
douyin-interact like --url "https://www.douyin.com/video/<id>"
douyin-interact comment --url "https://www.douyin.com/video/<id>" --text "已确认的评论"
douyin-interact reply --url "https://www.douyin.com/video/<id>" --comment-id <id> --text "已确认的回复"
```

默认只输出预览。核对目标、文字和账号后，在同一命令末尾加 `--confirm` 才发送。`unlike`、`favorite`、`unfavorite` 同样需要 `--confirm`。写操作依赖 Relay v2 `web.request` 完成端点联调；服务未就绪时 `SIGN_UNAVAILABLE` 或 `UNSUPPORTED_OPERATION` 不视作成功。一次调用只提交一次；超时或结果不明时先到平台核实，不自动重试。平台风控、Relay 故障与登录失效分别处理，不把接口空响应当作成功。

结果按以下规则解读：

- `accepted=true` 表示平台 `status_code=0`、已接受本次操作；`response` 保留原始字段。不能把请求受理等同于已核实的操作后状态。
- 点赞、收藏及其取消操作返回 `account_state_verified=false`，表示工具未核验当前账号的最终状态。不要将原始 `is_digg=0`、`collects_flag=false` 翻译为未点赞、未收藏或操作失败。
- 评论/回复单独返回 `comment_id`（若平台提供），`visibility_verified=false` 表示未核验公开可见性。不要凭 `comment.status=7` 等未确认的数字推断待审核、隐藏或发布失败。
- App 同步可能延迟；需要确认时核对本人 App 或明确的本账号状态，不用作品总数增减替代。已有用户核实结果应保留，不因原始字段为零或 false 再次操作。
- `accepted=null` 表示缺少明确的受理凭据，应报告结果未确认并停止重试。不要为核验而重复点赞、取消、收藏或发送同一评论。
