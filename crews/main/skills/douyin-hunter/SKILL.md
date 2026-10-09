---
name: douyin-hunter
description: 抖音内容搜索与采集。读取作品、用户、评论与回复、搜索、收藏、关注关系、推荐流和通知，并下载视频或图文素材。
metadata:
  openclaw:
    emoji: 🔎
    requires:
      bins:
        - python3
---

# 抖音采集

使用本技能包内 `tools/douyin-login` 的 `douyin-login` 独立 API 会话。平台请求由本机直发，动态字段交 Relay。缺会话或平台明确拒绝登录时退出 2；Relay 故障、风控和接口异常不能当作登出。

## ID 使用规则

用户、作品和评论 ID 必须从原始响应或完整链接读取，按字符串原样保存和传递。禁止截断、添加省略号或先转 JavaScript Number；终端摘要和日志中的缩略 ID 不能作为后续调用参数。若只拿到缩略值，重新读取原始 JSON 或重新搜索，禁止凭前缀补全。

`user-posts --user` 和 `user_profile` 的 `sec_user_id` 参数使用完整的 `sec_uid`，不要替换成数字 `uid`。仅有 `MS4w` 前缀不代表 ID 完整有效。

- ✅ 从搜索原始 JSON 读取完整 `sec_uid`，原样传给 `--user` 或 `sec_user_id`；显示摘要时仍保留原始完整值供后续调用。
- ❌ 把展示用的 `sec_uid[:25]`、`MS4w…` 或截断主页链接复制到查询命令。

获取指定账号作品后，核对每条作品的 `author.sec_uid` 或 `author.uid` 与目标账号一致。作者不符时停止后续账号分析，先核对传入 ID 是否为原始完整值；接口返回成功不能替代作者核验。

## 调用方式

```bash
douyin-hunter check
douyin-hunter search --type video --keyword "关键词" --count 20
douyin-hunter search --type user --keyword "关键词" --count 20
douyin-hunter fetch --url "https://www.douyin.com/video/作品ID" --output-dir /绝对路径/作品 --download-media
douyin-hunter comments --id 作品ID --count 20 --output /绝对路径/comments.json
douyin-hunter comments --id 作品ID --comment-id 评论ID --count 20
douyin-hunter user-posts --user "https://www.douyin.com/user/完整sec_uid" --count 20
douyin-hunter collect user_posts --params '{"sec_user_id":"完整sec_uid"}' --count 50 --output-dir /绝对路径/采集
```

`fetch` 返回 `note` 和 `media_paths`；保存 `note.json`、`video.mp4` 或有序 `image-01.jpg` 等图片，视频供 `viral-chaser` 使用，图文供 `expert-douyin` workflow 分析。图文按图片形态识别，不因附带动态封面误判成视频。公开详情只记录实际提供的点赞、评论、分享和收藏，不将详情中的播放数作为可靠播放量。本人已发作品使用 expert-douyin 的 `douyin-engagement` 通过 HTTP 接口取数，临时读取发布 profile 的 cookie/UA；其他账号播放量及后台深指标不自动获取。`fetch --video-only` 在下载前拒绝图文。评论读取、点赞收藏提醒和新增关注通知归本技能；点赞、收藏、发表评论、私信和直播互动调用 expert-bd。

`douyin-hunter methods` 查看只读方法及必填参数；`douyin-hunter call <method> --params '{...}'` 读取原始响应。搜索类型支持 video/general/user/live。列表翻页每次最多 100 条、10 页；缺列表字段或游标异常报错，不当作空数据成功。
