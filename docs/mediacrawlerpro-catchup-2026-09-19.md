# MediaCrawlerPro-Python 跟进（2026-09-19）

## 核对范围

参考仓 `/home/ctyun/wiseflow-pro/MediaCrawlerPro-Python`，origin 为 `daxiongdi666/MediaCrawlerPro-Python`。本地原 HEAD `6e5b419` → fetched `46b08f1`，共 22 个提交（含 merge）。客户端比较基线 `0f43aa9`；OpenCLI 已吸收的本地提交为 `dd59847`、`b026f01`。仅提炼平台字段与请求处理知识，在当前 TypeScript/HTTP 架构内实现。

## 适用性与落地

| 上游提交 | 更新 | 当前调用链与处理 |
| --- | --- | --- |
| [a040581](https://github.com/daxiongdi666/MediaCrawlerPro-Python/commit/a040581) | 小红书视频 stream 从 h264/h265 切到 EF*，origin_video_key 可能消失 | 已吸收到 `_shared/xhs-html-note.ts`：遍历全部数组分档、过滤无效 URL，按数值化 height/bitrate 排序，兼容 camelCase/snake_case；保留 og:video 兜底。viral-chaser 与 xhs-content-ops 共用解析器 |
| [46b08f1](https://github.com/daxiongdi666/MediaCrawlerPro-Python/commit/46b08f1) | 快手 `/f/<token>` 分享链接需从重定向拿作品 ID | 当前 viral-chaser 的 Platform/下载分支仅 douyin、bilibili、xhs，没有快手。记录供未来快手 adapter 使用，不把分享 token 当 photoId，也不只加域名制造“能解析不能下载”的半支持 |
| [a1ba42e](https://github.com/daxiongdi666/MediaCrawlerPro-Python/commit/a1ba42e) | 快手搜索/作者列表从 GraphQL 迁往签名 REST | 当前无这两个列表消费者，不搬签名或端点。`/rest/v/search/feed`、`/rest/v/profile/feed` 需要 `__NS_hxfalcon`；result 50 是拒绝，不能当列表结束 |
| [dd65435](https://github.com/daxiongdi666/MediaCrawlerPro-Python/commit/dd65435) | 快手请求抖动，列表 result 2 有界退避 | 该错误码语义只针对上述接口，不套到抖音或小红书。上游为原间隔加 1–3 秒、最多 3 次 5/10/20 秒加抖动重试。现有快手仅 login-manager 的 GraphQL `visionProfileUserList` 探活及未接入定时入口的旧取数函数，均不等于被迁移的两个接口；未据此修改 |
| [75a1f81](https://github.com/daxiongdi666/MediaCrawlerPro-Python/commit/75a1f81) | 快手 photo/author 为 null 不应整轮崩溃 | 无 viral-chaser 快手分支；旧 fetch-retro-data.ts 已用可选链读取 photo，并有 try/catch，无同型空值崩溃 |
| 6a932ee、b115261、a831892 | 小红书搜索末页、空评论页循环、断点提交 | xhs-content-ops 当前是单笔记 HTML 图片/正文下载，没有关键词/评论分页或 checkpoint，不能直接移植。通用“无新增/游标不前进即停止”用于本地抖音评论防死循环 |
| cb6f3b0 | 海外 RedNote 域名与 API 路由 | 本次没有海外账号/域名需求，未改国内 cookie、签名或路由 |
| 5039107、5b57be2 | Reddit、VoxAgent 持久化采集 | 非当前三平台技能链路，未引入 |
| defcde3、缓存/文件落盘修复与相关 merge、5b34301 | Python 依赖、事件循环缓存、原子 checkpoint、注释 | 客户端不运行该 Python 爬虫框架，不同步其依赖、缓存和存储实现 |

## 与昨天 OpenCLI 更新的关系

OpenCLI `75c85e5` / `3ec6eb0` 提供速度型软风控识别（300017/300031 / 安全限制）、8–18 秒冷却与恰好一次重试。MediaCrawlerPro 的 EF 分档更新提供视频结构兼容，两者互补。

- 保留现有 HTML 读取路线、单次冷却上限与“不因软风控换 cookie/重登”。
- 补齐 viral-chaser CLI 的 `SECURITY_BLOCK` 结构化输出与 exit 3，避免外层泛化成普通错误。xhs-content-ops 已有此行为。
- xhs-content-ops 短链域名补齐 xhslink.cn，与 viral-chaser 已有支持一致。
- 不用快手的 result 2 重试次数覆盖小红书的单次冷却规则。
- OpenCLI 的抖音 creator item/list 改造是创作者指标链路，不是评论接口替代方案。

## 抖音评论核查

**确实采用同接口、同类方案**：本地 `expert-douyin/tools/douyin-comments/scripts/fetch_comments.ts` 调用 `_shared/douyin-web.ts`，走 HTTP + cookie + relay a_bogus，请求 `/aweme/v1/web/comment/list/`，参数含 aweme_id/cursor/count/item_type。上游 `media_platform/douyin/client.py:get_aweme_comments` 使用同端点及 verifyFp/fp。不是运行时调用上游 Python，但有同类可用性风险。viral-chaser 的抖音视频详情和 published-track 的 creator 指标链路是不同接口，不应一起判失效。

本地确定问题及修正：

1. 删除把首屏任何非零状态码/空响应误判为 SESSION_EXPIRED 的处理；不再套用作品管理 work_list 的 status 8 自动重试经验。
2. 接口不可用、请求中断、分页停滞返回 exit 3，保留结构化错误与已抓部分结果；缺本地 cookie 才保留 exit 2。
3. 页间加 1–3 秒间隔、按 cid 去重、停滞即停；保留最后一页、正确标记 limit 截断。空响应不等于零评论。
4. 对标与起号流程遇 exit 3 停止本轮评论采样，标注数据不可得，继续其他分析。

**issue 核实限制**：GitHub API 返回 fork `has_issues=false`，父仓 `MediaCrawlerPro/MediaCrawlerPro-Python` issues 在当前凭据下为 404；公开搜索未找到可核验的对应 issue。已向用户索取具体链接/编号。不能据此确认“所有账号均无法抓取”或宣布已有替代接口，也未进行真实 cookie 评论请求。以上修正是错误处理与停止策略，不是恢复评论抓取的承诺。

## 验证

`node --experimental-strip-types --test test/skills/test-upstream-catchup.ts`：覆盖 EF/未知桶、h265 兜底、数值字符串排序、og:video、正文不误判软风控、OpenCLI 单次冷却上限、评论空体/状态 8、不重试、去重/游标停滞、部分结果、末页和 limit。

未发布内容、未改运行配置、未使用真实账号发起平台采集；上游 issue 与 live 评论可用性仍待核实。

## MediaCrawlerPro-Downloader 交叉核对

用户追加指定仓库后完整 clone 到 `/home/ctyun/wiseflow-pro/MediaCrawlerPro-Downloader`，HEAD `dc1cdff`。当前 viral-chaser 的 `platforms/douyin.ts` / `platforms/bilibili.ts` 文件头明确标注参考 `DownloadServer/pkg/media_platform_api/`，因此下载链路以它为直接参考来源更准确。未找到 Downloader 的历史精确 catchup commit，不能把本次全新 clone 的全部历史当作“自上次以来新增”。

| 关注项 | Python 仓 | Downloader 仓 | 本次结论 |
| --- | --- | --- | --- |
| 快手 `/f/<token>` → 重定向真实作品 ID | 46b08f1 | [dc1cdff](https://github.com/daxiongdi666/MediaCrawlerPro-Downloader/commit/dc1cdff) | 已同步；当前 viral-chaser 尚无快手 adapter，未只接解析 |
| 小红书 EF* 分档 | a040581 | [4c8e76c](https://github.com/daxiongdi666/MediaCrawlerPro-Downloader/commit/4c8e76c) | 已同步；当前共享 HTML 解析器已吸收，同时覆盖两仓知识 |
| 快手 creator/search 签名 REST | a1ba42e | 未同步；作者列表仍走 visionProfilePhotoList GraphQL | 不以 Downloader 的旧列表实现覆盖较新的 Python 知识 |
| 快手 result 2 退避与抖动 | dd65435 | 未同步；request 捕获异常后立即 continue，最多三次，没有 sleep | 不复制立即重试行为，也不把列表错误码套到其他接口 |
| 快手 null photo/author | 75a1f81 | photo 已有空值判断；author=null 仍可在 `_extract_author_info` 出错 | 不能认定 Downloader 已完整同步该修正 |
| 抖音评论 | client.py 有 comment/list | `DownloadServer` 当前未发现评论列表抓取实现 | 本地 douyin-comments 是独立的同接口实现，不是 Downloader 内置能力；下载成功不能证明评论可用 |

Downloader fork 同样 `has_issues=false`。两个 fork 均不能直接提供用户提及的 issue；具体反馈仍需 issue 链接或可读内容。此次没有新增快手平台支持，也没有宣称恢复抖音评论接口。
