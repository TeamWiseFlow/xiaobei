---
name: smart-search
description: 通过xiaobei受管浏览器搜索和阅读网页：选择站点、构造搜索 URL、使用默认或平台专用的持久化 session 并提取真实结果。如果已有 douyin-hunter、xhs-hunter、tiktok-hunter、kuaishou-hunter、x-hunter、weibo-hunter、youtube-hunter 或 wx-mp-hunter 技能，对应平台的内容搜索应该优先调用上面这些技能。
metadata:
  openclaw:
    emoji: 🔍
    requires:
      bins:
        - camoufox-cli
---

# xiaobei_browser 浏览器搜索

用于需要实际打开网页、登录站内搜索、使用页面筛选条件或读取渲染结果的任务。交互操作优先调用 `xiaobei_browser`；浏览器登录、验证码、懒加载与付费墙的操作细节读取公共 `browser-guide`。站点文档中的 `camoufox-cli` 示例供已有脚本使用；工具调用按相同 URL、session 和页面语义执行，不改用原生 browser。两项技能独立保留：本技能负责搜索方法与站点规则，browser-guide 负责通用页面操作。

原始搜索结果只作为线索；需要全文、准确日期或具体数字时打开对应原文核实。本技能不发布、不发评论或私信，不把搜索卡片当作原文或完整统计。

## 先检查是否可调用如下技能

| 平台 | 优先技能 | 实际登录/会话约定 |
|---|---|---|
| 抖音 | `douyin-hunter` | 使用 `douyin-login` 独立 API 会话；浏览器 `douyin` profile 不替代该会话 |
| 小红书 | `xhs-hunter` | 使用其 PC 扫码/短信会话；浏览器 `xhs-browse` profile 不替代 PC 登录 |
| TikTok | `tiktok-hunter` | login/export 使用固定 Camoufox session/profile `tiktok` |
| 快手 | `kuaishou-hunter` | 使用其独立 QR/SMS 登录；不要求从浏览器导出会话 |
| X/Twitter | `x-hunter` | login/export 使用固定 Camoufox session/profile `twitter`，不是 x |
| 微博 | `weibo-hunter` | login/export 使用固定 Camoufox session/profile `weibo` |
| YouTube | `youtube-hunter` | 公开读取免登录；账号操作 login/export 使用专属 `youtube` profile |
| 微信公众号 | `wx-mp-hunter` | fetch 为文章读取，posts-list 依赖微信客户端，homepage 自管临时会话；不代表支持全网关键词搜索 |

- 当前 crew 可用且任务命中接口能力时，先读该技能 SKILL.md，再按其命令执行。不要给 API 命令拼入 `--session` / `--persistent`，也不要自行导出 Cookie。
- 已配置技能报登录失效、限频或风控时按它的错误规则处理，不自动换浏览器路径重试。
- 未配置时，已有浏览器规则的平台可按下表搜索；不能调用其他 crew 的命令或更改自身 allowlist。需要超出浏览器规则的采集时，按当前 crew 的委托权限交 main，或报告缺口。
- TikTok、快手、微信公众号目前未维护专门的站内浏览器关键词搜索规则；缺少相应技能时可用 Bing 搜索公开索引 `site:tiktok.com` / `site:kuaishou.com` / `site:mp.weixin.qq.com`。索引不代表完整作品或发布列表。
- 微信视频号目前没有搜索与内容获取方案，不将创作者后台当作内容搜索。

## 默认与平台专用 session / profile

**普通站点直接使用 Camoufox 内置 `default` session/profile：省略 `--session`，每条页面操作命令带 `--persistent`。** 未指定路径的 `--persistent` 使用 `~/.camoufox-cli/profiles/default/`；只省略 `--session` 不会自动启用持久化。需要登录的普通站点也在默认 profile 中登录，不另建搜索专用、站点专用或类别专用 profile。

下表列明默认 profile 与平台专用名称，不表示 profile 已创建或已经登录；首次登录与验证按 browser-guide 及平台技能执行。

| 浏览器站点 | session / profile 名 |
|---|---|
| 通用搜索、知乎、B站、YouTube、Reddit、LinkedIn、雪球、GitHub、新闻、商品、学术、技术社区、政策，以及六类新增专业站点 | `default` |
| 微信公众号已知文章、快手已知公开页面（尚无站内搜索规则） | `default` |
| 抖音（仅不可使用 douyin-hunter 时） | `douyin` |
| 小红书（仅不可使用 xhs-hunter 时） | `xhs-browse` |
| X（仅不可使用 x-hunter 时） | `twitter` |
| 微博（仅不可使用 weibo-hunter 时） | `weibo` |
| TikTok（平台登录或已知页面，尚无站内搜索规则） | `tiktok` |

新增六类站点的名称、共享 `default` profile 与网页入口集中在 [site-catalog.json](site-catalog.json)。自媒体平台的专用 profile 沿用上表；涉及发布、Cookie 读取/导出或独立 API 登录时按对应技能执行，不能以 `default` 替代其登录会话。不要导入 Cookie、复制指纹文件或把已有 profile 的 Cookie 合并到 `default`。

TikTok/X/微博技能可用时，登录必须由 `tiktok-hunter` / `x-hunter` / `weibo-hunter` 发起，不用通用浏览器另开窗口。已有有头登录窗口时保持 `--headed`，不要用无头命令重启它。API 登录成功、profile 中存在 Cookie、文件夹存在均不证明当前浏览器页面已登录。

例如知乎搜索导航：

```bash
camoufox-cli --persistent --json open '<按 sites/zhihu.md 生成的完整搜索URL>'
```

后续 snapshot、点击、滚动和原文读取保持同一 session 与模式。共享 `default` 中的搜索与阅读串行执行，先完成当前页面取数再打开下一站；其他任务正在使用时等待。提示 session 正忙时等待当前命令完成，不能 close 占用中的会话或换名并发。

## 选择站点并读取规则

| 搜索目标 | 站点规则 |
|---|---|
| 通用网页、新闻/图片搜索 | [Bing / 百度 / 夸克](sites/general.md) |
| 中文问答 | [知乎](sites/zhihu.md) |
| 视频、UP 主 | [B站](sites/bilibili.md) |
| 视频、Shorts、频道、播放列表（先检查 youtube-hunter） | [YouTube](sites/youtube.md) |
| 社区讨论 | [Reddit](sites/reddit.md) |
| 仓库、代码、issues、用户 | [GitHub](sites/github.md) |
| 职位、人员、公司 | [LinkedIn](sites/linkedin.md) |
| 股票与金融讨论 | [雪球](sites/financial.md) |
| 论文、学术、百科 | [arXiv / 百度学术 / 万方 / Wikipedia](sites/academic.md) |
| 技术讨论与贴吧 | [HN / V2EX / 贴吧](sites/tech.md) |
| 国际新闻 | [Reuters / BBC](sites/news.md) |
| 政策文件 | [国务院](sites/gov.md) |
| 商品 | [Amazon](sites/shopping.md) |
| 行业动态、招标、法规、供应链 | [36氪 / 招标剑鱼 / 国家法律法规库 / 1688](sites/business.md) |
| 技术证据、模型、开源与依赖生态 | [Stack Overflow / MDN / Gitee / Hugging Face / OpenReview / npm / PyPI](sites/tech-ai.md) |
| 论文、作者、引用与书目信息 | [Google Scholar / Semantic Scholar / OpenAlex / PubMed / DBLP / Crossref / CNKI](sites/academic-extra.md) |
| 岗位、人才与项目需求 | [BOSS直聘 / 51job / Indeed / 脉脉 / Upwork](sites/recruiting.md) |
| 商品评价、消费与社区需求 | [豆瓣 / 什么值得买 / 京东 / 淘宝 / 大众点评 / 虎扑 / 即刻](sites/consumer.md) |
| 图像、设计与作品来源 | [Pinterest / Pixiv / ArtStation / Flickr / Unsplash / Openverse](sites/design.md) |
| 抖音：先检查 douyin-hunter 是否可用 | [浏览器规则](sites/douyin.md) |
| 小红书：先检查 xhs-hunter 是否可用 | [浏览器规则](sites/xiaohongshu.md) |
| X：先检查 x-hunter 是否可用 | [浏览器规则](sites/twitter.md) |
| 微博：先检查 weibo-hunter 是否可用 | [浏览器规则](sites/weibo.md) |

用户指定平台时先按其要求选站。未指定时，中文/英文通用搜索先用 Bing；问答用知乎；技术项目用 GitHub；论文用 arXiv；新闻用 Reuters/BBC。生活体验、短视频或微博舆论先检查 `xhs-hunter`、`douyin-hunter`、`weibo-hunter` 是否在当前 crew 可用，否则按已有浏览器规则或公开索引搜索。选择仍需服从用户的地区、语言和来源要求。

按问题选专业来源：采购/供应商用招标剑鱼或 1688；技术定义用 MDN，模型/数据集用 Hugging Face；医学文献用 PubMed，作者/出版记录用 DBLP、Crossref 或 OpenAlex；职位/项目需求用招聘规则，消费评价用口碑规则，设计参考用作品规则。需要获取完整平台资料、进一步研究或联系时交对应采集技能、`expert-osbi` 或 `expert-bd`；仅在当前 crew 已配置时调用。

只执行上表维护的规则。通用网页搜索维持 Bing、百度、夸克，不新增 Google、DuckDuckGo、Brave、Startpage、Sogou、Qwant、Mojeek；Google Scholar 仅作为学术来源。上游其他站点不自动启用。

## 搜索执行

1. 读取所选站点规则。有查询模板时用关键词构造完整 URL，关键词按所在参数/路径片段编码一次，保留中文、空格、#、& 等字符。只提供页面入口的站点，打开后从真实搜索控件提交，不猜测查询 URL；额外筛选优先通过页面操作。
2. 用固定持久化 session 打开页面。需要登录或 Cookie 初始化的站点可先访问原站首页并核对实际页面；访问首页不保证已登录或能够解除验证。
3. 等待真实结果区出现后 snapshot；按语义 ref 定位搜索卡片与原文链接。客户端页面尚未加载时有界等待，不把空骨架判为无结果。
4. 保留标题、真实链接、作者/来源、页面实际显示的日期和摘要。字段缺失写明不可得；“3 天前”等相对时间保留原值，精确日期到原文核实。去掉广告、推荐位和重复链接，保留小红书 xsec_token 等访问参数。
5. 需要补充时按页面当前的分页/筛选控件继续；源码中的 API 游标、接口参数和签名不得当作网页导航参数，也不在 eval 中自行复刻 API 请求。
6. 原文阅读、登录墙、验证码、付费墙和懒加载遵循 browser-guide。遇到付费/不可见内容只记录实际可访问部分。
7. 用完关闭自己本轮创建的标签页；本轮已结束且没有其他任务使用该 session 时再 close，保留磁盘 profile。不执行 close --all，不关闭其他任务或正在等待用户登录的窗口。

snapshot ref 优先；必要时用 eval 读取真实 DOM，复杂逻辑包在 IIFE 中。表单输入使用真实页面事件，不盲试随机 CSS 类。延迟或超时先核对同一页面和会话状态，不自动重启全部浏览器。

## 范围与搜索记录

同一用户意图默认每站最多两次搜索导航/翻页，第二次说明缩小范围或补充角度的理由；失败的搜索导航也计入预算。首页初始化不计搜索次数。预算不足以覆盖研究范围时，先交付已有结果与缺口，不偷偷扩搜。站点规则中的分页方式说明如何操作，不自动授权全量翻页。

查询结束保留并反馈站点、关键词/筛选条件、实际搜索次数、未访问成功的来源和样本缺口。只报告本轮实际取得的信息；不能因上游有接口或规则文件存在就宣称已搜到结果。
