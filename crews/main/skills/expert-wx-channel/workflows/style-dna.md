# 视频号 DNA 创建与更新 Workflow

本 Workflow 负责 DNA report、DNA 文档与 DNA template 的创建与更新。维度框架以 `wx-channel-style-profiler` 的 `references/video-dna-framework.md` 为准（DNA v2）。

## 边界

- DNA 是从一批作品样本中提取、聚合出的内容生产规则集；样本可以来自多个账号，也可以来自用户指定的一个账号的发布列表批量提取。
- 账号初始化与默认 `dna-0` 建立走 `account-setup.md`；对标样本先走 `account-benchmark.md`。
- DNA 如何用于内容生产走 `content-production.md`；改稿走 `editing.md`；数据复盘走 `review.md`。
- DNA 指导 main agent 出内容或视频 Brief；全片制作委托 `content-producer`。

## 入口判断

走本 Workflow：

- “建 DNA / 更新 DNA / 提炼这个账号的风格”
- “把这条视频落到某个 DNA 上”
- “用户提供单条或多条视频，帮我提炼可复用模式”

不走本 Workflow：

- 做内容 / 仿内容 → `content-production.md`
- 改脚本 / 换封面 / 压缩时长 → `editing.md`
- 看数据 / 评估 DNA → `review.md`
- 起号 / 定位 → `account-setup.md`
- 对标比较 → `account-benchmark.md`

## 目标 DNA 选择

1. 用户指定 `dna-id` 时使用该 DNA。
2. 未指定或说“默认 DNA”时使用 `dna-0`。
3. **作品类型**：视频号只有视频作品，`--kind` 固定 `video`，无需分型建 DNA。
4. 对标样本必须进入独立 DNA，不直接写入 `dna-0`；采纳后再通过局部融合更新。
5. 目标 DNA 不存在时，先走 `account-setup.md` 或按用户明确指定的新 `dna-id` 初始化。

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

原始脚本可临时放在 `wx_channel/ref/{dna-id}/transcripts/`。生成后的 report 必须进入目标 DNA 的 `reports/` 目录；覆盖同名 report 前先向用户说明。

## 样本获取

**先判作品类型**（视频 / 图文）：它决定用哪套维度框架、`--kind` 取值与目标 dna-id；同一个 DNA 不混型。

| 来源 | 处理 |
| --- | --- |
| 用户提供脚本 / 逐字稿 | 整理为 `.md` / `.txt`，保留描述、数据与账号线索 |
| 用户提供视频文件 | 先取得文字稿或确认转写；视频观测信息由用户/原视频补充 |
| 用户提供账号信息 | 记录昵称、简介、置顶、发布时间与内容形式 |
| 用户想法 / 偏好 | 不生成 report，按用户输入转译进入 DNA |

每条样本尽量收集：

- 样本类型：账号作品 / 用户提供单条
- 账号名、简介、主页承诺
- 发布时间、内容形式、素材来源
- 播放、完播、点赞、评论、转发等数据线索
- 横竖屏、时长、口播/实拍/AIGC 形态、真人出镜占比

缺失字段写「未观测」。视频号无公开对标抓取路径，数据必须来自用户或后台工具，不得编造。

## 建立或重建 DNA

### Step 1 - 准备样本

1. 判定作品类型（视频 / 图文），据此选框架与目标 `dna-id`。
2. 把脚本/逐字稿整理为 `.md`，首个一级标题写样本标签 / 视频描述摘要。
3. 确定目标 `dna-id`、`sample-id`、样本权重和 focus。
4. 整理账号观测与视频观测信息，供 Agent 补进 report。

### Step 2 - 生成单篇 report

```bash
wx-channel-style-profiler report \
  --input path/to/script.md \
  --dna-id {dna-id} \
  --sample-id {sample-id} \
  --cover-image path/to/cover.jpg \
  --source-url "https://channels.weixin.qq.com/..." \
  --output-dir wx_channel/dna/{dna-id}/reports
```

生成 scaffold 后必须：

1. 补齐「样本观测」：作品类型、样本来源、账号与简介、发布时间、数据线索、横竖屏与时长、素材来源（缺失写「未观测」）。
2. 回读转录 / 脚本原文，补齐各维度的单篇结论、原文证据与可复用信号。
3. 短标题与视频描述分开记：抓取只能拿到视频描述，短标题拿不到就写「未观测（管理页不展示）」，不得把描述当短标题。
4. 视频内容形态必须给出**制作指向**（Content Producer `expert-video` 的某个 workflow，或 main 的 `video-edit` / `talking-head-cut` / `ui-demo`），只写真实存在的资源名。
5. 视觉维度必须有封面 / 首帧 / 关键帧图片证据；口播文案子模块样本不足时写「未启用」。
6. 账号运营子模块只在样本来自对标账号批量提取时填写，单篇样本写「未观测」。

### Step 3 - 聚合 DNA

```bash
wx-channel-style-profiler build --dna-id {dna-id}
```

Agent 必须读取全部 report，按权重/focus 聚合：

- 高频共性、高权重偏好、局部借鉴、孤例、例外分开写。
- 标注样本覆盖度；单篇或少量样本不得称为稳定结论。
- 视频形态必须聚合成明确的**制作指向**（Content Producer `expert-video` 的某个 workflow，或 main 的素材加工技能），供 Brief 的 `workflow` 字段直接引用。
- 高数据内容要回读创意、形态与包装，不能只归因播放量。
- 为每个维度写聚合结论、报告依据和可执行规则。
- 确保 DNA 文档能推导 template；账号运营子模块的结论只留在 DNA 文档。

## 更新已有 DNA

### 新增样本

生成新 report 后运行：

```bash
wx-channel-style-profiler update \
  --input wx_channel/dna/{dna-id}/reports/{new-sample}.report.md \
  --dna wx_channel/dna/{dna-id}/{dna-id}.dna.md \
  --template wx_channel/dna/{dna-id}/{dna-id}.template.md
```

再由 Agent 重新审视聚合结论并同步修订 template。

### 用户偏好

用户偏好不直接入库。通过 `--user-input` 传入后，Agent 映射到具体维度，并把原话转译为具体维度的创作规则与 Brief / 图文生产规则。

### 局部借鉴

对标 DNA 的局部规则必须先说明来源、适用条件和影响维度，再融合进目标 DNA；不得整包照搬。

### 表现反馈

复盘产生的建议先列证据与影响维度，经用户确认后写入 DNA；不得把一次数据波动直接升格为 DNA 规则。

## DNA 使用接口

- **视频全案**：读取 DNA 文档与 template，main agent 产出 **Brief**（+ 口播类的口播文案）。Brief 写明选题与观看理由、内容创意、`workflow`（视频形态的制作指向）、制作规格、素材清单（绝对路径）、验收标准、闸门批准人。
- **短标题与视频描述由 main agent 拟定**：视频号发布页两项都可填，官方称填短标题能获得更多流量，因此两项都必须有、发布时都必须填；但入库（`published-track`）与 `wx-channel-engagement` 匹配只用**视频描述**，短标题不写库。这两项属发布文案，不进 Brief 的制作要求。
- **Brief 不含 DNA 信息**：Content Producer 看不到 main 的 DNA，只按 Brief 制作；也不要把 DNA 文档路径写进 Brief。
- **口播类视频**：口播终稿一律由 main agent 写好并随 Brief 交付（`narration-script` 子模块启用时按其结构写，未启用时按用户要求与 Brief 核心传达写）；真人口播时由 main agent 指导用户录音并向用户取得录音文件。CP 不重写。
- **工作区**：main 不替 CP 建工作区，也不指定项目目录；CP 自建工作区，双方 T3 权限可互访取文件。

## 对标接口

对标样本进入独立 `dna-id`；比较时输出选题、短标题与视频描述、内容创意、业务植入与 CTA、视频形态与制作指向、制作规格的差异，以及（账号批量样本才有的）账号运营子模块差异：简介写法、发布习惯。用户明确采纳后才通过局部融合写进目标 DNA。

## 编排原则

- 一个生产任务只使用一个 DNA，且作品类型与任务一致；需要融合时先更新 DNA。
- 样本、用户输入、数据反馈必须可追溯。
- 账号运营子模块（简介写法、内容形式比例、发布习惯）只在对标账号批量样本下填写，且只进 DNA 文档不进 template；覆盖度不足就写未观测。
- Template 只写 main agent 可执行的规则：视频类 = Brief 正文模板 + 口播文案模板。都不写成片制作细节。
