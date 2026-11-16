---
name: xhs-style-profiler
description: 提取小红书作品 DNA：单篇笔记（图文 / 视频）生成 report，按 dna-id 聚合选题、标题与封面、内容创意、匹配的用户问题（搜索意图）、业务植入套路、互动引导与 CTA 套路、视频形态与制作指向、正文表达与图组视觉、口播文案子模块与账号运营子模块，推导 main agent 的图文 / Brief 生产 template。
---

# xhs-style-profiler

小红书作品 DNA 提取与聚合工具。输入是**笔记文本**（标题 + 正文 + 话题标签）或**视频转录文本**（口播全文 + 标题 / 描述 / 时长 / 互动线索），由 Agent 先整理成 `.md` / `.txt`；可选封面 / 首帧 / 配图作为视觉证据。不接受视频文件或链接作为直接输入（取数走 `viral-chaser` 或平台工具）。

DNA 的用途是指导 main agent 选题、包装、出内容或出视频制作 Brief；**不指导成片制作**——创作细节、脚本结构、镜头与编码参数归 Content Producer。

## 作品类型（`--kind`）

小红书有两套维度框架，用 `--kind` 选择；**一个 `dna-id` 只承载一种作品类型**：

| kind | 作品 | 维度框架 | 默认 dna-id |
|------|------|----------|-------------|
| `note` | 图文（默认） | `references/note-dna-framework.md` | `dna-0` |
| `video` | 视频 | `references/video-dna-framework.md` | `dna-0-video` |

- 不传 `--kind` 时默认 `note`（小红书的主作品类型），因此**默认 `dna-0` 是图文 DNA**；视频样本另建 dna-id（如 `dna-0-video`）。
- `build` / `update` 会校验同一 DNA 目录下 report 的 kind 一致，混型直接报错——另一种类型请另建 dna-id。
- 默认 dna-id 只是约定：用户可以指定任意 dna-id，脚本不强制命名。

## 产物模型

```text
单篇作品 -> DNA report
同一 dna-id 下全部 report + 权重 / focus + 用户输入转译 -> DNA 文档
DNA 文档 -> DNA template
```

- **DNA report**：单篇作品的样本观测 + 维度提取结果；跨篇共性与生产规则由聚合阶段给出，report 本身不是模板。
- **DNA 文档**：聚合后的生产规则、样本覆盖度、子模块结论与用户输入转译区。
- **DNA template**：main agent 的生产输入模板（视频 = Brief 正文 + 口播文案；图文 = 写作模板）。

## 存储结构

```text
xhs/dna/{dna-id}/
  reports/
    {sample-id}.report.md
  covers/
    {sample-id}.{ext}
  {dna-id}.dna.md
  {dna-id}.template.md
```

原始转录 / 正文文本可临时放在 `xhs/ref/{dna-id}/transcripts/`；生成后的 report 必须进入目标 DNA 的 `reports/` 目录。

## 职责边界

- **搜索优先**：`search-intent`（匹配的用户问题）是小红书必备维度——最大流量池来自搜索。关键词必须尽量落到用户可能的提问原句，不只写平台标签。
- 单篇 report 只提供候选信号，不判断跨篇稳定性；共性、偏好、孤例由聚合阶段判断。
- 视觉维度必须有图片 / 关键帧证据，由视觉模型读取；缺失写「未提供」，不得凭文本想象补齐。
- 口播文案子模块只在口播类作品启用；样本不足写「未启用」。
- 账号运营子模块（简介写法、内容形式比例、发布习惯）只在样本来自对标账号批量提取时填写，且**不进 template**。
- 不输出风格评分或账号权重；合规只记「必须避免项」（虚假承诺、利益诱导互动、隐藏站外联系方式、谐音绕检测），不出具合规审查结论。

## Report — 单篇提取

```bash
# 图文笔记（不传 --kind，默认 note）
xhs-style-profiler report \
  --input path/to/note.md \
  --dna-id {dna-id} \
  --sample-id {sample-id} \
  --cover-image path/to/cover.jpg \
  --source-url "https://www.xiaohongshu.com/explore/..." \
  --output-dir xhs/dna/{dna-id}/reports

# 视频笔记
xhs-style-profiler report \
  --input path/to/transcript.md \
  --kind video \
  --dna-id {dna-id}-video \
  --sample-id {sample-id} \
  --duration 45 \
  --cover-image path/to/cover.jpg \
  --output-dir xhs/dna/{dna-id}-video/reports
```

- `--kind`：作品类型（见上）；不传走默认。
- `--cover-image`：封面 / 首帧 / 首图本地文件，作为视觉证据（自动拷进 `covers/`）。
- `--source-url`：原作品链接；本地素材无链接时省略。
- `--duration`：视频时长（秒），用于口播密度统计；图文忽略。
- `--weight`：样本权重，默认 1。
- `--focus`：限制该样本只影响指定维度 ID，可重复传入。

视频统计输入约定：

- 纯文字稿可只含一级标题和逐字口播。混合文件须把口播放在 `## 口播全文` 下（可带括号说明；也接受 `转录全文` / `逐字稿`），到下一个标题结束；来源、作者、备注、结构标注和视觉分析放在该节之外。
- 时间戳列表可用 `- 0.04–5.32s：原话`；统计时移除列表前缀与时间码，不计标题、标点和空白，只计口播中的字母、数字与汉字。句长、人称等视频统计也只看该口播正文。
- `[剧情概括]` / `[转述]` 不作逐字口播统计；正文边界不明、缺时长或含概括/转述时，口播密度标为「未提供」，聚合时排除该项，不能用 0 代替缺项。
- 口播密度使用视频总时长，表示全片平均字符密度，不能代替实际发声段语速或人工听音判断。

Agent 生成 scaffold 后必须：

1. 补齐「样本观测」：作品类型、样本来源、账号与简介、发布时间、数据线索、素材来源。
2. 回读原文，补齐各维度的单篇结论、原文证据与可复用信号。
3. 视频形态必须给出**制作指向**（Content Producer `expert-video` 的某个 workflow，或 main 的某个素材加工技能），只写真实存在的资源名。
4. 账号运营子模块无法从单篇观测时写「未观测」。
5. 高数据样本必须回读创意与形态再归因，不得只凭播放 / 阅读量下结论。

## Build — 聚合 DNA 文档与模板

```bash
xhs-style-profiler build --dna-id {dna-id}                      # 图文 DNA（默认 kind=note）
xhs-style-profiler build --dna-id {dna-id}-video --kind video    # 视频 DNA
```

默认读取 `xhs/dna/{dna-id}/reports/`，输出 `{dna-id}.dna.md` 与 `{dna-id}.template.md`。也可显式传 report 文件 / 目录：

```bash
xhs-style-profiler build --input path/to/reports --dna-id {dna-id}
```

Agent 聚合时必须：

1. 读取全部 DNA report，不能只看统计表。
2. 按 `weight` 与 `focus` 判断影响范围。
3. 区分高覆盖共性、高权重偏好、局部借鉴、孤例与例外。
4. 标注样本覆盖度；少量样本不得称为稳定结论。
5. 为每个维度写聚合结论、报告依据与可执行创作规则。
6. 确保 DNA 文档能完整推导 template（template 不得引入 DNA 文档未确认的规则）。

## Update — 增量聚合

```bash
xhs-style-profiler update \
  --input xhs/dna/{dna-id}/reports/{new-sample}.report.md \
  --dna xhs/dna/{dna-id}/{dna-id}.dna.md \
  --template xhs/dna/{dna-id}/{dna-id}.template.md
```

脚本合并历史 report 与新 report、重算统计并保留 Agent 已写内容；kind 从 DNA 文档 frontmatter 继承（也可用 `--kind` 显式指定，冲突时报错）。Agent 仍需重新审视聚合结论并同步修订 template。

- `update` 只替换机器统计、元数据和报告引用，并在用户输入区追加 pending 偏好；维度正文、改名标题、附加手工段落原样保留，template 不自动改写，也不会重新生成待填 scaffold。新增偏好仍须 Agent 回读证据、转译并修订 template。
- 保留 DNA/template frontmatter 的 `dna-id`、`type`、`kind`；保留 DNA 的 `report_count`、`total_weight`、`weighting`、`generated_at`、唯一 `<!-- dna-reports ... -->` 引用区块，以及 `## 报告与权重`、原生统计表和其末尾“统计只用于辅助聚合……”边界、`## 用户输入转译区`。人工规则写在统计区外。维度标题可带稳定 ID 改名，template 正文可用自由 Markdown。
- 缺少机器区块、统计区混入无法识别的人工段落、历史引用数量不足或 kind 冲突时拒绝写入。先在副本恢复上述结构并核对原 report；不要用 build 绕过，build 会拒绝覆盖已有 DNA/template。
- 写入前自动保存两份原文件到 DNA 旁 `.profile-backups/<时间-随机后缀>/`，输出 `update.diff` 和含删除行的 `audit.json` 路径。核对 diff 中统计/引用替换与新偏好，再完成定性修订。写入准备或原子替换失败时原文件不变。

`--input` 可省略，用于只融合用户输入或另一个 DNA 的局部规则；此时必须传 `--user-input`。

## DNA Template

**视频作品 template（= Brief 正文模板 + 口播文案模板）**

1. 选题
2. 标题与封面
3. 内容创意
4. 关键词与用户问题
5. 业务植入与 CTA
6. 视频形态与制作指向
7. 制作规格
8. 口播文案

**图文作品 template（= 图文写作模板）**

1. 选题
2. 标题与封面
3. 关键词与用户问题
4. 内容创意与结构
5. 正文表达
6. 图组
7. 业务植入与 CTA

- 开头两段（**选题**、**标题与封面**）跨平台通用。
- 视频 template 的各段直接对应 Brief 正文字段；**Brief 不含 DNA 信息**（Content Producer 看不到 main 的 DNA），素材清单、验收标准、闸门批准人按平台 Content Production Workflow 填。
- 账号运营子模块不进 template，只留在 DNA 文档。

## 用户输入转译

用户输入是参考信息，不是可直接入库的 DNA 规则：

```bash
--user-input "以后多做实拍拼接，少用纯动画"
```

Agent 必须映射到具体维度并转译为可执行规则，例如：

```text
search-intent：主关键词补上「AI 客服」「评论区监控」，并落到用户提问原句
title-cover：标题偏数字型 + 痛点型，封面用大字报版式
content-idea：多用「实测对比」创意原型
```

处理要求：

1. 在 DNA 文档「用户输入转译区」记录 raw_input、affected dimensions、DNA 修改、template 修改与状态。
2. 原话必须转译为可执行规则，不得直接抄进 template。
3. 与样本证据冲突时保留冲突说明，由用户选择优先级。

## Focus ID

### video（视频）

| ID | 维度 |
|---|---|
| `topic-angle` | 选题与观看理由 |
| `title-cover` | 标题与封面 |
| `content-idea` | 内容创意 |
| `search-intent` | 匹配的用户问题 |
| `video-form` | 视频内容形态与制作指向 |
| `production-spec` | 制作规格与视听倾向 |
| `biz-implant` | 业务植入套路 |
| `interaction-cta` | 互动引导与 CTA 套路 |
| `narration-script` | 口播文案子DNA |
| `account-bio` | 账号简介写法 |
| `content-mix-cadence` | 内容形式比例与发布习惯 |

### note（图文）

| ID | 维度 |
|---|---|
| `topic-angle` | 选题与观看理由 |
| `title-cover` | 标题与封面图组 |
| `content-idea` | 内容创意 |
| `search-intent` | 匹配的用户问题 |
| `body-voice` | 正文表达与语气 |
| `imageset-visual` | 图组视觉风格 |
| `biz-implant` | 业务植入套路 |
| `interaction-cta` | 互动引导与 CTA 套路 |
| `account-bio` | 账号简介写法 |
| `content-mix-cadence` | 内容形式比例与发布习惯 |

`--focus` 按作品类型校验：视频 report 不接受图文维度 ID，反之亦然。

## 参考资料

- `references/video-dna-framework.md`（小红书视频作品 DNA 框架 v2：维度定义、制作指向映射、聚合边界与 Focus ID）
- `references/note-dna-framework.md`（小红书图文作品 DNA 框架 v2：维度定义、制作指向映射、聚合边界与 Focus ID）
