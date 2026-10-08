# 抖音原生界面卡片 Workflow

用户要做「群聊误发式」或「问答式连续讨论流」卡片并发抖音图文，或将小红书此类卡片同步到抖音时走本流程。卡片是图文 `note`，不用视频制作路线。使用 `native-ui-card` 共享技能出图；其他图文形式走 `content-production.md`。

## 1. 按图文 DNA 确定选题

读取 `douyin/dna/<dna-id>/<dna-id>.dna.md` 和 `.template.md`；未指定时用独立的图文 DNA（如 `dna-0-note`），不能套视频 DNA；目标 DNA 不存在先走 Style DNA workflow 建立。读取 `business_knowledge.md` 和用户素材作为事实与输入。先依据图文 DNA 的选题规则确定本次主题、受众、核心问题和表达方向；用户给定的题目也按 DNA 细化，若与 DNA 不一致，先协调再制作。workflow 不另设内容范围。选题确定后，按 DNA 要求用 `smart-search` 核查抖音侧的事实与讨论。跨平台已有成品先核对内容与授权，按抖音图文 DNA 重新定标题、正文与 CTA。

按 DNA template 定稿卡片的核心信息；问答卡另写主问题和相关搜索词。DNA 适合反差或反常识表达时，再核查常见看法、新判断及其依据；否则沿用 DNA 的内容结构。真实数字和案例必须可核验；聊天与评论要符合自然交流习惯。

## 2. 写卡片脚本

- **群聊误发式 A**：把已定稿的核心信息写成一条短消息；正常群主题的 2–3 条闲聊、跨天时间戳、设定的发言者误发消息并用红字突出核心句、紧跟的手滑道歉、3–5 条自然的围观回复。核心消息要落在画面中部，群主题与消息有自然反差。
- **问答式 B**：图 1 问题帖大标题、另一句相关搜索词、回答者头部和完整主回答；图 2 是主回答下面的反驳和缩进楼中楼；图 3 继续这条讨论，以共鸣和金句结束。不得拆成三张独立观点图。回答者身份只在图 1 头部出现一次。

界面不加说明性角标；群人数、时间戳和可选 `stats` 按画面语境设置，检查前后一致。群友头像可从打包池选，也可以按许可另下载或 AIGC 生成，在 `avatar_sources` 写来源；不能拿未经授权的真人肖像充当虚构群友。

## 3. 生成与审核

在 `douyin/outputs/<work-name>/` 写 `card.json`，参照 `native-ui-card` 随附的群聊或问答 JSON 示例填内容，设置 `platform: douyin` 和图文 `dna_id`；群聊还需填与账号身份一致的 `self_name` 和 `self_avatar`。示例不作为成稿。标题、描述、话题和互动引导按图文 DNA 定稿，并满足抖音平台限制：标题 1–20 字，描述含话题 ≤1000 字，图组 1–35 张，单张 ≤50MB；本路线固定 1 或 3 张 3:4 PNG。文案只放一个平台内 CTA。

执行 `native-ui-card --input /绝对路径/card.json --output /绝对路径/douyin/outputs/<work-name>`；修订加 `--force`。它一次生成有序图片、HTML、`note.md`、`dna-meta.json` 和头像来源清单。逐张目视核对第一行、红字、消息顺序、头像加载、重叠与裁切。问答图 2/3 要让人看出是图 1 主回答下的持续争论。出图溢出就减字重渲染。向用户展示标题、正文和全部图序，确认后发布。

## 4. 抖音发布与记录

先读 `douyin-publish` 工具说明，用 `douyin-engagement check` 验证 Camoufox 持久化创作者会话；未登录执行 `douyin-publish login`。按顺序上传 `page-01.png`（问答式加 `page-02.png`、`page-03.png`），用户确认内容并要求发布后执行：

```bash
douyin-publish note --images /绝对路径/page-01.png /绝对路径/page-02.png /绝对路径/page-03.png --title "已确认标题" --caption "已确认描述 #话题" --original-sound --confirm
```

只有返回确认的作品 ID 和 `/note/` URL 才算完成。提交结果未知时先核实管理页，并用 `douyin-note-publish get-note-link --title "完整标题"` 取链，禁止自动重发。成功后执行：

```bash
published-track record --platform douyin --title "已发布标题" --content-type post --source-folder douyin/outputs/<work-name>/ --publish-url "确认的note URL" --account <账号alias>
```

`dna-meta.json` 已由工具生成。若同步发小红书，再按 `expert-xhs/workflows/native-ui-cards.md` 的标题、正文、探活、发布与记录流程单独处理。
