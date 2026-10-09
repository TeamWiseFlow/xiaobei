# 小红书原生界面卡片 Workflow

用户要做「群聊误发式」或「问答式连续讨论流」卡片，或指定用这些卡片发小红书时走本流程。它是图文笔记制作与发布的完整路线，使用 `native-ui-card` 共享技能出图；其他图文形式走 `content-production.md`。

## 1. 按图文 DNA 确定选题

读取 `xhs/dna/<dna-id>/<dna-id>.dna.md` 与 `.template.md`；未指定时用 `dna-0`，目标 DNA 不存在先走 Style DNA workflow 建立。读取 `business_knowledge.md` 和用户素材作为事实与输入。先依据图文 DNA 的选题规则确定本次主题、受众、核心问题和表达方向；用户给定的题目也按 DNA 细化，若与 DNA 不一致，先协调再制作。workflow 不另设内容范围。选题确定后，按 DNA 要求用 `xhs-hunter` 的有界搜索或单篇读取、`xhs/ref/` 及已有研究核查搜索意图；业务事实以 `business_knowledge.md` 和用户材料为准。

按 DNA template 定稿卡片的核心信息；问答卡另写主问题和相关搜索词。DNA 适合反差或反常识表达时，再核查常见看法、新判断及其依据；否则沿用 DNA 的内容结构。案例、数字和引用要有来源；无来源就改为明确的假设或不使用。

## 2. 选形态、编讨论流

- **群聊误发式 A，单图**：把已定稿的核心信息写成一条短消息，再选与这条消息有自然反差的正常群主题；2–3 条群内日常铺垫 → 跨天时间戳 → 设定的发言者误发消息，红字突出核心句 → 紧接自然的手滑道歉 → 3–5 条质疑、共鸣或追问，把核心消息推到画面中部。群友语言要像不同的人，不能都是替发言者捧哏。
- **问答式 B，三图**：图 1 是显眼的问题帖 + 仅出现一次的回答者头部 + 完整主回答，回答有具体情境、转折和条件；图 2 是这条回答下的反驳、回应与缩进楼中楼；图 3 沿同一讨论继续共鸣，再用高亮金句收束。图 2/3 不重新开题，不做三个互不相干的观点切片。

界面不加说明性角标。群人数、时间戳和可选 `stats` 按画面语境设置，检查前后一致；发布文案承接卡片内容。

为群友选用打包头像池，也可按许可额外下载或 AIGC 生成，记录到 `avatar_sources`。使用真人照片须先取得适用授权。头像用 `native-ui-card` 的 320×320 规范化输出，不手工拼本机模板路径。

## 3. 定稿并渲染

在 `xhs/outputs/<work-name>/` 建作品目录。参照 `native-ui-card` 随附的群聊或问答 JSON 示例写 `card.json`，填 `platform: xhs`、图文 `dna_id`、标题（≤20 字）、正文（含话题后 ≤1000 字）、话题（≤10 个）及全部页文案；群聊还需填与账号身份一致的 `self_name` 和 `self_avatar`。示例文本仅说明字段，不可直接发布。标题、正文、话题和互动引导按图文 DNA 定稿，并满足小红书平台规则；不放联系方式或站外导流。

运行 `native-ui-card --input /绝对路径/card.json --output /绝对路径/xhs/outputs/<work-name>`；修订加 `--force`。工具固定渲染 2160×2880 PNG，并检查头像和版面溢出。逐张打开图片复核：群聊核心消息的位置、红字、第一行、头像、是否遮挡；问答图 1 的问题和主回答是否完整、身份是否重复，图 2/3 是否连续、楼中楼是否看得清。过长就精简文案并重渲染，不靠裁掉底部解决。向用户展示标题、正文、全部图序，确认后发布。

## 4. 小红书发布与记录

按 `xhs-publish` 工具文档先 `xhs-publish check`；需重登时运行 `xhs-publish login`，把返回的二维码图片通过当前渠道发给用户；等用户确认后运行 `xhs-publish login-confirm`。把 `note.md` 的实际文字传给 `--body`，把图片按顺序传给 `--images`：

```bash
xhs-publish --mode image --title "已确认标题" --body "已确认正文 #话题" --images /绝对路径/page-01.png /绝对路径/page-02.png /绝对路径/page-03.png
```

图组含 AI 合成内容时，在发布命令末尾加 `--ai-declaration`；纯实拍或仅使用真实素材的排版卡片不加。

群聊单图只传 `page-01.png`。仅 `ok: true` 且返回笔记 URL 才记为成功；登录、风控、限频按 `xhs-publish` 和 expert-xhs 规则处理，不盲目重发。成功后执行：

```bash
published-track record --platform xhs --title "已发布标题" --content-type post --source-folder xhs/outputs/<work-name>/ --publish-url "返回的URL" --account <账号alias>
```

`dna-meta.json` 已由工具生成。双平台分发时抖音走 `expert-douyin/workflows/native-ui-cards.md`，按抖音自己的标题、文案、发布锁与记录执行。
