---
name: wx-channel-style-profiler
description: 提取微信视频号作品 DNA：单条视频生成 report，按 dna-id 聚合选题、短标题与视频描述、内容创意、业务植入套路、互动引导与 CTA 套路、视频形态与制作指向、制作规格、口播文案子模块与账号运营子模块，推导 main agent 的视频 Brief template。
---

# wx-channel-style-profiler

微信视频号作品 DNA 提取与聚合工具。输入是**视频转录文本**（口播全文 + 视频描述 / 时长 / 互动线索），由 Agent 先整理成 `.md` / `.txt`；可选封面 / 首帧 / 配图作为视觉证据。不接受视频文件或链接作为直接输入（取数走 `viral-chaser` 或平台工具）。

DNA 的用途是指导 main agent 选题、包装、出内容或出视频制作 Brief；**不指导成片制作**——创作细节、脚本结构、镜头与编码参数归 Content Producer。

## 作品类型

微信视频号作品只有视频一种，维度框架见 `references/video-dna-framework.md`；`--kind` 只接受 `video`（默认即 `video`，通常不用传）。

## 产物模型

```text
单篇作品 -> DNA report
同一 dna-id 下全部 report + 权重 / focus + 用户输入转译 -> DNA 文档
DNA 文档 -> DNA template
```

- **DNA report**：单篇作品的样本观测 + 维度提取结果；跨篇共性与生产规则由聚合阶段给出，report 本身不是模板。
- **DNA 文档**：聚合后的生产规则、样本覆盖度、子模块结论与用户输入转译区。
- **DNA template**：main agent 的生产输入模板（Brief 正文 + 可选口播文案）。

## 存储结构

```text
wx_channel/dna/{dna-id}/
  reports/
    {sample-id}.report.md
  covers/
    {sample-id}.{ext}
  {dna-id}.dna.md
  {dna-id}.template.md
```

原始转录 / 正文文本可临时放在 `wx_channel/ref/{dna-id}/transcripts/`；生成后的 report 必须进入目标 DNA 的 `reports/` 目录。

## 职责边界

- **短标题与视频描述是两项独立内容**：发布页两项都可填，官方称填短标题能获得更多流量；但作品管理页不展示短标题，取数时只能拿到视频描述。report 里短标题拿不到就写「未观测（管理页不展示）」，不得把视频描述当短标题；两者都由 main agent 拟定，发布时都必须填。
- 单篇 report 只提供候选信号，不判断跨篇稳定性；共性、偏好、孤例由聚合阶段判断。
- 视觉维度必须有图片 / 关键帧证据，由视觉模型读取；缺失写「未提供」，不得凭文本想象补齐。
- 口播文案子模块只在口播类作品启用；样本不足写「未启用」。
- 账号运营子模块（简介写法、内容形式比例、发布习惯）只在样本来自对标账号批量提取时填写，且**不进 template**。
- 不输出风格评分或账号权重；合规只记「必须避免项」（虚假承诺、利益诱导互动、隐藏站外联系方式、谐音绕检测），不出具合规审查结论。

## Report — 单篇提取

```bash
wx-channel-style-profiler report \
  --input path/to/transcript.md \
  --dna-id {dna-id} \
  --sample-id {sample-id} \
  --cover-image path/to/cover.jpg \
  --source-url "https://..." \
  --duration 36 \
  --output-dir wx_channel/dna/{dna-id}/reports
```

- `--kind`：只接受 `video`（即默认值），通常不用传。
- `--cover-image`：封面 / 首帧 / 首图本地文件，作为视觉证据（自动拷进 `covers/`）。
- `--source-url`：原作品链接；本地素材无链接时省略。
- `--duration`：视频时长（秒），用于口播密度统计。
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
wx-channel-style-profiler build --dna-id {dna-id}
```

默认读取 `wx_channel/dna/{dna-id}/reports/`，输出 `{dna-id}.dna.md` 与 `{dna-id}.template.md`。也可显式传 report 文件 / 目录：

```bash
wx-channel-style-profiler build --input path/to/reports --dna-id {dna-id}
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
wx-channel-style-profiler update \
  --input wx_channel/dna/{dna-id}/reports/{new-sample}.report.md \
  --dna wx_channel/dna/{dna-id}/{dna-id}.dna.md \
  --template wx_channel/dna/{dna-id}/{dna-id}.template.md
```

脚本合并历史 report 与新 report、重算统计并保留 Agent 已写内容；kind 从 DNA 文档 frontmatter 继承（也可用 `--kind` 显式指定，冲突时报错）。Agent 仍需重新审视聚合结论并同步修订 template。

`--input` 可省略，用于只融合用户输入或另一个 DNA 的局部规则；此时必须传 `--user-input`。

## DNA Template

**视频作品 template（= Brief 正文模板 + 口播文案模板）**

1. 选题
2. 短标题与视频描述
3. 内容创意
4. 业务植入与 CTA
5. 视频形态与制作指向
6. 制作规格
7. 口播文案

- 开头两段（**选题**、**短标题与视频描述**）跨平台通用。
- 视频 template 的各段直接对应 Brief 正文字段；**Brief 不含 DNA 信息**（Content Producer 看不到 main 的 DNA），素材清单、验收标准、闸门批准人按平台 Content Production Workflow 填。
- 账号运营子模块不进 template，只留在 DNA 文档。

## 用户输入转译

用户输入是参考信息，不是可直接入库的 DNA 规则：

```bash
--user-input "以后多做实拍拼接，少用纯动画"
```

Agent 必须映射到具体维度并转译为可执行规则，例如：

```text
video-form：主形态为影视解说 + 反转植入，制作指向 expert-video 的 Reversal Ad workflow
production-spec：竖屏 9:16、时长带 30-45s、画面偏冷暗解说段 + 明亮植入段
narration-script：口播保持第三人称解说体，句长 10-15 字
```

处理要求：

1. 在 DNA 文档「用户输入转译区」记录 raw_input、affected dimensions、DNA 修改、template 修改与状态。
2. 原话必须转译为可执行规则，不得直接抄进 template。
3. 与样本证据冲突时保留冲突说明，由用户选择优先级。

## Focus ID

| ID | 维度 |
|---|---|
| `topic-angle` | 选题与观看理由 |
| `title-cover` | 短标题、视频描述与封面 |
| `content-idea` | 内容创意 |
| `video-form` | 视频内容形态与制作指向 |
| `production-spec` | 制作规格与视听倾向 |
| `biz-implant` | 业务植入套路 |
| `interaction-cta` | 互动引导与 CTA 套路 |
| `narration-script` | 口播文案子DNA |
| `account-bio` | 账号简介写法 |
| `content-mix-cadence` | 内容形式比例与发布习惯 |

`--focus` 只接受上表维度 ID；填入其他值直接报错。

## 参考资料

- `references/video-dna-framework.md`（微信视频号视频作品 DNA 框架 v2：维度定义、制作指向映射、聚合边界与 Focus ID）
