---
name: douyin-engagement
description: 通过统一 API 会话读取本人已发布视频和图文的基础、深度指标，回填发布记录。
---

# 抖音本人作品取数

使用与 `douyin-hunter`、`douyin-publish` 共用的 `douyin-login` API 会话。先验证本人 UID，再刷新创作者 token 和对应证书，通过 HTTP 获取指标；不启动 Camoufox，不从 profile 读取 Cookie，不使用 login-manager，不因失败切换其他账号或凭据。

```bash
douyin-engagement check
douyin-engagement list
douyin-engagement fetch --row-id 12
douyin-engagement daily
```

已有 API 登录不重复扫码；明确认证失效时按 `douyin-login` 完成登录后重跑 check。`list` 只读取发布记录，row-id 是数据库行 ID，daily 扫描最近 30 条记录。API 会话/创作者通道/计算错误分开报告，不能把所有错误都当作登出。

创作者 item/list 最多 10 页、每页 50 条，以完整作品 ID 匹配本人账号。优先采用创作者播放、点赞、评论、分享、收藏；缺失的后四项可用同一 API 会话的公开详情补充，公开播放量不采用。403 风控、429 限频或认证拒绝时停止本轮，不继续公开补采或自动重登。

工具调用 `published-track update-metrics` 写库。平台实际返回的完播、跳出、封面点击率等写入 deep_metrics，来源 douyin:creator_item_list；基础字段来源逐项记录在 field_sources。以 metrics、deep、field_sources 和 unavailable_reasons 为准；明确零值正常写入，缺失不补零，旧值不算本次采集。未返回的深指标不承诺可用。

发布与取数使用同一 API 账号并串行执行。历史 profile 适配仅供维护者诊断，不作为新登录或普通取数流程，不与 API 凭据拼接。
