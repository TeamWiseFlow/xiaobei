---
name: twitter-engagement
description: X/Twitter本人已发布作品数据获取和指标回填，不负责发布或其他账号数据分析。
---


# X/Twitter本人作品指标

```bash
twitter-engagement check --account default
twitter-engagement list --account default --limit 20
twitter-engagement fetch --record-id 12 --account default --limit 100
twitter-engagement daily --account default --limit 30
```

fetch 的 --record-id 是 published-track 表行 ID，不是平台作品 ID。脚本在线核验当前用户，获取本人作品列表，按完整发布 URL 匹配同 alias 的记录，再调用 published-track update-metrics。X 列表可能含他人转发，作者不符即停止。TikTok/快手使用当前已验证创作者会话的本人列表，存在作者字段时再核对。

默认只取 20 条，最大 100 条；只更新真实匹配的记录，没取到的记录返回 skipped，不用标题猜匹配。只写接口提供的非负整数，真实 0 保留，null 不写、不覆盖历史值。结果保留 source、captured_at 与分页信息。不提供受众画像、收益或后台深指标；接口与字段仍需本地实号验收。

长文 article 链接尚无与本人推文列表的可靠 ID 映射，返回 skipped；帖串自动记录和取数只针对首条，不冒称已覆盖后续全部推文。
