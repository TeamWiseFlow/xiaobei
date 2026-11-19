# 视频号账号对标 Workflow

用于分析对标账号或一组对标视频，形成独立 DNA，并与默认或指定 DNA 逐项比较。对标样本不得直接写入 `dna-0`；用户采纳后，只有转译后的规则可融合进基线 DNA。

## 入口判断

走本 Workflow：

- “分析对标账号”
- “看看这个视频号和我们风格差异”
- “这几条高分享视频有什么共同模式”
- “建一个对标 DNA”

不走本 Workflow：

- 用户明确说“把这条视频落到某个 DNA 上” -> 走 `style-dna.md`
- 账号定位和默认 DNA 初始化 -> 走 `account-setup.md`
- 抖音 / B站 / 小红书视频的追爆拆解（只为拿拆解报告，不建对标 DNA）-> 顶层 `viral-chaser`

## 对标 DNA 选择

1. 每个对标对象或样本组使用一个独立 DNA，建议命名为 `dna-benchmark-{slug}`。
2. 同一组对标账号或视频复用同一个 DNA 并增量更新；不因每次交互重复新建。来源差异保留在 report 证据中。
3. 对标 DNA 不进入默认内容生产，除非用户明确采纳其中某些规则。
4. 用户指定比较基线时使用该 DNA；未指定时使用 `dna-0`。

## 分析流程

### Step 1 - 获取样本

视频号没有公开抓取路径，样本获取按来源处理：

| 来源 | 处理 |
| --- | --- |
| 自己账号的作品 | `wx-channel-engagement list` 拿视频描述与行内指标；完整口播仍需转写或用户提供 |
| 用户提供文字稿 / 视频文件 | 文字稿直接输入；视频文件先经顶层 `talking-head-cut` 转写 |
| 用户提供的截图 / 口述数据 / 账号信息 | 作为数据、账号简介、发布时间与内容形式线索保留在 report 证据中，标注来源 |
| 跨平台参考（抖音 / B站 / 小红书链接） | 顶层 `viral-chaser` 下载 + 转写 + 拆解；跨平台样本只借鉴结构，不照搬平台调性 |

选择建议：

1. 优先选择分享、评论信号强的视频；播放量只作次要参考（视频号分享权重高于点赞）。
2. 对标账号的播放、互动数据只能来自用户提供或截图；不得编造，不得把运营效果等同于内容质量。
3. 对标账号至少批量收集 10 条代表性视频样本（从账号发布列表提取）；不足 10 条时提供全部并说明数量限制。
4. 每条样本尽量记录账号简介、发布时间、内容形式、素材来源；缺失写「未观测」，不虚构。
5. 单条视频可以形成单篇观察，但不得当成稳定结论；多个样本才分析覆盖率和共性。
6. 批量账号样本必须填**账号运营子模块**：账号简介写法（`account-bio`）、发布习惯（`content-mix-cadence`，含发布时间段与节奏）；只写进 DNA 文档，不进 template。

### Step 2 - 建立对标 DNA

对每条视频执行：

```bash
wx-channel-style-profiler report \
  --input path/to/transcript.md \
  --dna-id {benchmark-dna-id} \
  --sample-id {sample-id} \
  --output-dir wx_channel/dna/{benchmark-dna-id}/reports
```

再执行：

```bash
wx-channel-style-profiler build --dna-id {benchmark-dna-id}
```

Agent 必须回读文字稿，补齐 report，并基于全部 report 修订：

```text
wx_channel/dna/{benchmark-dna-id}/{benchmark-dna-id}.dna.md
wx_channel/dna/{benchmark-dna-id}/{benchmark-dna-id}.template.md
```

对标 DNA template 用语义段与目标 DNA 一致：选题、短标题与视频描述、内容创意、业务植入与 CTA、视频形态与制作指向、制作规格、口播文案（可选）。每一部分都要能从对标 DNA 文档推导；账号运营子模块不进 template。

### Step 3 - 选择比较基线

读取：

```text
wx_channel/dna/{base-dna-id}/{base-dna-id}.dna.md
wx_channel/dna/{base-dna-id}/{base-dna-id}.template.md
```

默认 `{base-dna-id}` 为 `dna-0`。若 `dna-0` 不存在，先停止比较并提示用户走 `account-setup.md` 初始化，或由用户明确指定另一个基线。

### Step 4 - 逐项比较

比较必须覆盖两层：

1. **DNA 文档**：逐个比较选题与观看理由、短标题与视频描述、内容创意、业务植入套路、互动引导与 CTA 套路、视频形态与制作指向、制作规格、口播文案子模块，以及账号运营子模块（简介写法、发布习惯）。
2. **template 语义段**：逐项比较选题、短标题与视频描述、内容创意、业务植入与 CTA、视频形态与制作指向、制作规格、口播文案。

每个维度和模板语义段都输出四类结论：

| 类别 | 判断标准 |
| --- | --- |
| 保持 | 基线已有优势，与目标观众和商业定位一致 |
| 引入 | 对标更有效，且不冲突业务事实、合规边界和用户偏好 |
| 局部借鉴 | 只适合选题、短标题与视频描述、内容创意、制作指向或发布习惯等局部场景 |
| 不采纳 | 仅依赖孤例、冲突商业定位、风险高或难稳定执行 |

每项至少说明：

1. 基线 DNA 的规则和证据。
2. 对标 DNA 的规则和证据。
3. 差异原因或适用条件。
4. 是否建议更新基线。

### Step 5 - 采纳与更新

对比结果不自动更新基线 DNA。用户明确采纳后，选择一种方式：

1. **局部 DNA 融合**：读取对标 DNA 文档 / template 中对应内容，把它当作用户提供的融合要求，更新基线 DNA。
2. **局部样本借鉴**：仅在用户明确希望引入原视频证据、权重或 focus 时，才将对标视频重新生成属于基线 DNA 的 report，并用 `--focus` 限定采纳维度。
3. **偏好转译**：用户表达“分享动机更明确”“口播更真实”等要求时，按 `style-dna.md` 的用户输入转译更新。
4. **明确不改 DNA**：仅作为本次选题或制作参考，不落盘到 DNA。

局部 DNA 融合流程：

1. 明确采纳范围：维度、template 语义段，或两者组合。
2. 读取对标 DNA 文档 / template 的对应规则、适用条件和例外。
3. 整理为一条可转译输入，包含来源 `dna-id`、采纳范围和具体规则。
4. 在基线 DNA 上执行无新增样本的 update：

```bash
wx-channel-style-profiler update \
  --dna wx_channel/dna/{base-dna-id}/{base-dna-id}.dna.md \
  --template wx_channel/dna/{base-dna-id}/{base-dna-id}.template.md \
  --user-input "采纳 {benchmark-dna-id} 的社交分享闭环：xxx"
```

5. Agent 把该输入转译为基线 DNA 的 affected dimensions、聚合结论、创作规则和 template 执行字段。
6. 融合时检查与基线证据、业务事实、合规边界和用户偏好的冲突；冲突保留说明，不静默覆盖。

更新后同步修订基线 DNA 文档与 template，并保留来源说明。
