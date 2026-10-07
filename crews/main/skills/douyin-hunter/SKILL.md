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

使用 `expert-douyin` 的 `douyin-login` 独立 API 会话。平台请求由本机直发，动态字段交 Relay。缺会话或平台明确拒绝登录时退出 2；Relay 故障、风控和接口异常不能当作登出。

```bash
douyin-hunter check
douyin-hunter search --type video --keyword "关键词" --count 20
douyin-hunter search --type user --keyword "关键词" --count 20
douyin-hunter fetch --url "https://www.douyin.com/video/作品ID" --output-dir /绝对路径/作品 --download-media
douyin-hunter comments --id 作品ID --count 20 --output /绝对路径/comments.json
douyin-hunter comments --id 作品ID --comment-id 评论ID --count 20
douyin-hunter user-posts --user "https://www.douyin.com/user/用户ID" --count 20
douyin-hunter collect user_posts --params '{"sec_user_id":"用户ID"}' --count 50 --output-dir /绝对路径/采集
```

`fetch` 返回 `note` 和 `media_paths`；保存 `note.json`、`video.mp4` 或有序 `image-01.jpg` 等图片，供 `viral-chaser` 使用。图文按图片形态识别，不因附带动态封面误判成视频。公开详情只记录实际提供的点赞、评论、分享和收藏，不将详情中的播放数作为可靠播放量。本人已发作品使用 `douyin-engagement` 从创作者作品列表读取播放量并回填发布记录；其他账号播放量及后台深指标当前不自动获取。

`douyin-hunter methods` 查看只读方法及必填参数；`douyin-hunter call <method> --params '{...}'` 读取原始响应。用户/作品 ID 全程使用字符串，禁止先转 JavaScript Number。搜索类型支持 video/general/user/live。列表翻页每次最多 100 条、10 页；缺列表字段或游标异常报错，不当作空数据成功。
