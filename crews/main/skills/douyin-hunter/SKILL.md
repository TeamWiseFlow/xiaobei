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

用户、作品和评论 ID 必须从原始响应或受支持的作品链接读取，按字符串原样保存和传递。禁止截断、添加省略号或先转 JavaScript Number；终端摘要和日志中的缩略 ID 不能作为后续调用参数。若只拿到缩略值，重新读取原始 JSON 或重新搜索，禁止凭前缀补全。

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

`fetch` 和 `comments` 的 `--url` 支持 `www.douyin.com` 完整作品链接（含 `modal_id`）、`https://v.douyin.com/` 分享短链及 `www.iesdouyin.com` / `iesdouyin.com` 的 HTTPS 分享作品链接；纯数字作品 ID 使用 `--id`。短链由脚本匿名还原，最多跟随 5 次跳转，只接受上述官方域名的 HTTPS 地址。直接传入短链，不需要手动打开网页或复制作品 ID。

短链错误按返回码处理：`SHORT_URL_EXPIRED` 请用户重新分享；`SHORT_URL_TIMEOUT` / `SHORT_URL_NETWORK_ERROR` 表示还原时网络失败；`SHORT_URL_HTTP_ERROR` 表示分享服务返回 HTTP 错误；`SHORT_URL_INVALID_REDIRECT` / `SHORT_URL_REDIRECT_MISSING` / `SHORT_URL_REDIRECT_LOOP` / `SHORT_URL_TOO_MANY_REDIRECTS` / `SHORT_URL_ITEM_ID_MISSING` 表示跳转异常或未找到作品 ID，停止并报告原错误。不要将短链还原失败当作采集登录失效，也不要自行改用浏览器绕行。

`fetch` 返回 `note` 和 `media_paths`；保存 `note.json`、`video.mp4` 或有序 `image-01.jpg` 等图片，视频供 `viral-chaser` 使用，图文供 `expert-douyin` workflow 分析。图文按图片形态识别，不因附带动态封面误判成视频。公开详情只记录实际提供的点赞、评论、分享和收藏，不将详情中的播放数作为可靠播放量。本人已发作品使用 expert-douyin 的 `douyin-engagement` 通过 HTTP 接口取数，复用与采集共用的 API 会话；其他账号播放量及后台深指标不自动获取。`fetch --video-only` 在下载前拒绝图文。评论读取、点赞收藏提醒和新增关注通知归本技能；点赞、收藏、发表评论、私信和直播互动调用 expert-bd。

`douyin-hunter methods` 查看只读方法及必填参数；`douyin-hunter call <method> --params '{...}'` 读取原始响应。搜索类型支持 video/general/user/live。列表翻页每次最多 100 条、10 页；缺列表字段或游标异常报错，不当作空数据成功。

## 公开直播读取

房间、商品、PK/榜单、最近消息、流地址和有界事件监听使用 `douyin-hunter live`；先读 [直播读取说明](references/live.md)。商业调研与分析交 `expert-osbi`，弹幕和点赞仍由 `expert-bd` 的 douyin-live 执行，hunter 不暴露直播写操作。

## 搜索筛选与会话恢复

`search --type general` 支持 `--length all|short|medium|long`、`--range all|seen|unseen|following`、`--content-type all|video|image`，可组合原有排序与发布时间参数。`--type video` 支持时长和范围；`--type user` 支持 `--fans 0_1k|1k_1w|1w_10w|10w_100w|100w_`、`--user-type common|enterprise|personal`。平台未返回匹配结果时不宣称筛选成功。

主站只读请求缺少 UIFID 时，工具最多请求一次公开 feed 补全后重试原读取；写操作不自动重试。可执行 `douyin-login refresh --scope web` 续接主站会话。403 风控、429 限频和登录失效分别处理，不自动换号或改用浏览器绕行。直播读取采用扩展消息协议解码；不增加直播写操作。

用户筛选统一编码为数组形式 search_filter_value。返回的 filter_check 保留请求条件并核验实际粉丝数与认证信息：mismatch 表示出现明确不匹配，任务返回 SEARCH_FILTER_MISMATCH，保留原结果供诊断，不偷偷删除不匹配项；unverified 表示证据不足，不能宣称筛选已生效。视频和综合搜索的条件是否实际生效也须根据结果证据判断。

推荐流 collect feed 解包 cards 中的作品，兼容对象与 JSON 字符串。非作品卡片不作为内容；按客户端 refresh_index 有界翻页，返回 cursor 是下一次刷新索引。has_more 表示平台仍可继续请求，complete 表示达到请求数量或已结束；页数上限时 complete 为 false。推荐流持续变化，不当作稳定完整快照；游标或无进展错误时停止，不无限重复。

PLATFORM_STATUS_2096 等业务拒绝不等于整体登出。错误结果保留脱敏 request_info、response_info 和私有 diagnostic_file；平台原始消息仅存于 0600 诊断文件，不复制 Cookie、token、签名链接或原始账号参数进公开报告。
