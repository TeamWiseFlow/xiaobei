# Workflow：Collage B-roll（纸拼贴组装动画）

Brief 里写 `workflow: collage-broll`，或甲方要"把这句口播做成拼贴 B-roll""纸拼贴动画""半调拼贴"时使用。本文指导 Stage 1–2 的隐喻清单、自检与 GATE A 质检，并附半调纸拼贴 + assemble-from-empty 的制作与验收约定。与已验证的 `reversal-ad` 一样，通用 Stage 0→15 全程适用；GATE A 在 Stage 5 后，GATE B 在 Stage 9 后。类型指导只改变各阶段的具体产物，不能裁掉阶段或闸门。

## 类型定义

把一句约 5 秒的口播文稿压成一个 sharp visual idea，做成高级编辑风**半调纸拼贴（halftone paper-collage）组装动画** B-roll：

- 强烈、平坦、均匀的纯色纸面色场 + 黑白 halftone 照片剪贴为骨架 + 彩色卡纸点缀服务信息层级
- 动作是 assemble-from-empty：元素从空场逐件滑入、卡位、组装（stop-motion 质感），不是轻微漂移、晃动或慢 zoom
- 默认交付 9:16、5 秒、720×1280、无声 MP4，可直接垫在口播下面

逐条文稿 → 逐条隐喻 → 逐条独立成片。批量隐喻优先形成前后叙事（例如先表现手工消耗与经验流失，再表现规范沉淀与人机分工）。

## 输入契约（Brief 侧）

| Brief 字段 | 要求 |
|-----------|------|
| 文稿 | 甲方交付：口播形态给 `voiceover.md`（绝对路径），其余给 Brief 内文稿字段，逐条可独立成句。**落稿锁定不重写**——隐喻是文稿的视觉转译，不是改写；发现文稿无法转译（一句话塞多个隐喻、超时长带）报 Brief owner |
| form | 画幅 / 时长 / 分辨率 / 声音；未指定按默认（9:16、5s、720P、无声） |
| gates | GATE A / GATE B 批准人；代理批准时写明批准范围 |
| acceptance | 验收标准（未指定按「交付」节默认） |

## 基线阶段的纸拼贴产物

Stage 3–10 调 `video-producer` 同名阶段命令，生成并填写纸拼贴专用脚手架；空模板不算阶段完成。固定机位、无真人时也要把该事实登记为阶段产物，不虚构机位或角色三视图。

| Stage | 本类型动作与产物 |
|---|---|
| 0 | 核对文稿逐条可拆、规格和授权；缺字段向 Brief owner 澄清 |
| 1–2 | `script-write` 生成 `script/script.md` 隐喻清单；`script-self-eval` 按隐喻、纸片数、色彩与可转译性自检，低分返工 |
| 3 | `storyboard-build` 按每条隐喻写镜头表，记录固定构图、视觉命题、原句、逐件进入顺序与时长；落 `storyboard/storyboard.json` |
| 4 | `shot-decompose` 写空色场首帧、组装完成末帧及每层入场动作；落 `storyboard/shot_decompose.json` |
| 5 | `character-register` 登记跨镜一致的人物/物件纸片、参考图、授权；无人物时明确登记空角色清单；落 `characters/registry.json` |
| GATE A | 呈交隐喻清单、分镜、首尾画面、人物/纸片一致性方案；停下等批准 |
| 6 | `slot-plan` 为每镜 3–6 个独立纸片规划素材槽、色场和层级；落 `slots/slot-plan.json` |
| 7 | `asset-resolve` 逐层落实图像、形状、纸纹，记录来源、授权或生成 prompt/模型/时间；落 `slots/asset-resolve.json` |
| 8 | `slideshow-risk` 审核隐喻可读性、层独立性、真实入场、来源及水印/假字；做 HTML 静帧预览与人工检查，落 `slots/slideshow-risk.json`；fail 返工 |
| 9 | `delivery-promise-lock` 逐条锁定时长、规格、声轨、纸片动作、封面和证据，落 `slots/delivery-promise.json` |
| GATE B | 呈交每条素材来源、预览 contact sheet、最终定格帧与 Stage 8/9 审核；停下等批准 |
| 10 | `render-shot` 建 `render/collage-render-plan.json`，按批准预览用 `visual-render` 实际渲染；特殊变形才用 `batch-i2v`。计划不等于已出片 |
| 11 | `mix-audio` 建 `audio/collage-audio-plan.json`；默认逐条确认无声，有声音时登记来源、授权和对齐，不重做甲方口播 |
| 12 | `assemble --manifest` 逐条核验并交接单段成片，输出项目成片路径；无声片保持无音轨，不附加静音轨 |
| 13a | 公共 `video-review` 必跑；无声版的 `audio_absent` warning 是预期，有声版缺音轨则失败 |
| 13b | `motion-audit` 逐层核验 Stage 9 的组装承诺，单条默认落 `review/collage-motion-audit.json`，批量条目各自指定审核路径；整体淡入不能通过 |
| 13c | `normalize` 必调用：有声片归一至 -14 LUFS；明确无声时传 `--silent-ok`，核验无音轨并记录不适用 |
| 14–15 | 按 Brief 制作含主文案的封面；交成片、封面、`final-deliver.md` 的绝对路径 |

## 隐喻清单（Stage 1–2）

先把每条文稿压成一个视觉命题，提取：

- **核心意思**：观众最终要看懂什么
- **情绪**：冷静、惊讶、紧迫、豁然开朗、荒诞、反讽
- **动作动词**：打开、连接、漏掉、装订、归档、点亮、压缩、分叉、组装
- **可视化隐喻**：机器、时钟、胶片、档案柜、控制台、规则册、漏斗、轨道、棋子

**不要把文稿逐字放进画面。** 默认一条文稿只做一个隐喻，控制在 3–6 个关键物件；元素过多语意变弱，i2v 组装也不稳定。

`script/script.md` 每条格式：

```text
1. 核心意思：经验每次都在重复消耗
   视觉隐喻：熟练剪辑师围着巨大的胶片时钟逐帧裁切，时钟走完一圈却只得到一小段成片
   关键物件：胶片时钟、剪辑师、剪刀、短胶片
   色彩：焦橙底，奶油白与浅青点色
   组装顺序：时钟 → 人物与剪刀 → 胶片 → 最终短输出
```

### 隐喻自检（Stage 2 重定义，任一条不过必返工）

1. 一句话只表达一个清晰隐喻？
2. 关键物件 3–6 个，不是满屏碎片？
3. 文稿没有逐字进画面（无字幕、无口播全文）？
4. 底色与点色按下方色彩规则选，有理由？
5. 批量时前后叙事成立，或每条独立成立？

## GATE A：呈交脚本与分镜

文本闸门——**停，结束本轮回复**，发 Brief owner 审：

- 呈交：条数、每条一句话视觉命题、色彩方案、组装顺序、Stage 3–5 分镜与主体登记
- 甲方只确认部分编号时，只让通过的条目进 Stage 6；未通过条目改隐喻重审
- 甲方已在 Brief 代理批准时，把批准范围落 `gates/gate-a.md` 后继续

## 纸片素材与可控组装（Stage 6–9，GATE A 批准后）

每条隐喻准备 3–6 个**独立的本地素材层**，用一张纯色 CSS 背景承载。素材可以是黑白半调人物/物件图片、彩色卡纸块、纸纹或连接件；不要求透明 PNG，规则矩形剪贴和 CSS `clip-path` 就能形成纸片。需要图像时调公共 `awk-img-gen` 分别生成，不生成一张无法拆开的完整尾帧。记录每个素材的 prompt、模型、时间和授权来源。文字、logo、水印、UI 不得混进素材。

底色按隐喻语义选择，同一批保持相近纸张质感和点色层级：焦橙/红用于时间与劳动，芥末黄用于警示与流失，墨绿用于认知与重置，深紫用于规范与沉淀，青绿用于协作与执行。主体以黑白半调为主，彩色卡纸只标出信息重点。

`script/visual-spec.json` 逐条记下 `script_meaning`、`visual_metaphor`、`style_signature`、`color_field.background_hex`、`elements`（各含 `what`、`role`、`asset`、`placement`、`enter_at`）、`composition.final_frame` 和 `motion_plan`。素材提示词写进 `script/imagegen-prompts.md`；对每个物件分别请求一致的半调纸拼贴质感和干净剪贴边缘，并禁文字、数字、logo、水印和 UI。

先用 `video-producer visual-render scaffold` 建每条独立 composition：

```bash
video-producer visual-render scaffold <project>/render/<item>/composition \
  --width 720 --height 1280 --fps 25 --duration 5 --background '#D95B36'
```

把素材复制到 composition 的 `assets/`，在 `index.html` 的 `#stage` 内放置纸片 DOM 层。每层有固定尺寸、坐标、层级和纸张边缘/阴影；用本地 GSAP 的 paused timeline 按“基础结构 → 主体/卡片 → 连接件 → 结果”依次入场。动画应有数帧卡位感，最后至少留 0.7 秒定格。所有动作只由时间轴决定，不用 `Date.now()`、随机数、外部 CDN 或自动播放。例：

```js
// scaffold 已创建 const tl = gsap.timeline({paused:true});
tl.fromTo('#paper-1', {x:-720, rotation:-8},
  {x:0, rotation:0, duration:0.55, ease:'steps(4)'}, 0.25);
tl.fromTo('#paper-2', {y:1280, rotation:6},
  {y:0, rotation:0, duration:0.55, ease:'steps(4)'}, 1.1);
tl.fromTo('#paper-3', {x:720},
  {x:0, duration:0.55, ease:'steps(4)'}, 2.0);
```

以 `composition/index.html` 为真实可渲染画面。不要用一张完整海报做全屏淡入或 zoom 冒充逐件组装。

检查和静帧 QA：

```bash
video-producer visual-render check <project>/render/<item>/composition
video-producer visual-render preview <project>/render/<item>/composition \
  --output <project>/render/<item>/preview-v1 --at 0,0.8,1.6,2.8,4.8
```

`preview-v1/contact-sheet.jpg` 与 4.8 秒最终帧一起检查：隐喻是否一眼看懂、3–6 个大组是否清晰、黑白半调和点色是否形成层级、每层是否确实独立进入、无假字/水印/裁切越界。改版输出 `preview-v2` 等新目录，保留旧版比对。

## GATE B：呈交素材与预览

呈交每条隐喻的素材来源、联系表、最终定格帧和静帧 QA 结论。只让批准的条目进入最终渲染；修改素材或构图后重出预览并重新确认。代理批准的范围写入 `gates/gate-b.md`。

## 确定性渲染（Stage 10）

```bash
video-producer visual-render render <project>/render/<item>/composition \
  --output <project>/render/<item>/final.mp4 --workers 1 --quality delivery
```

默认交付 9:16、5 秒、720×1280、**无声** MP4。甲方要声音时先按 Brief 明确声音来源，再用 `video-producer audio-mix` / `deck-compose` 走公共音轨链；旁白必须保留用户或 main agent 提供的真人声音，不让拼贴视觉流程另造口播。抽看 0、1、2、3、4.8 秒与实际播放：从空色场逐件组装、固定机位、末帧稳定、无漂移。

若 Brief 明确要生成式物体变形、光影或无法用独立纸片实现的动作，可选用 `video-producer batch-i2v --batch <gen-jobs.json>` 调公共 `aigc-video-gen`。每个 job 写 `prompt`、`first_frame`、`last_frame`、`output`、`duration`，默认无声交付时另写 `"mute": true`，脚本在生成后无损去掉音轨；记录视频模型、费用与首尾帧。这是特殊镜头的备选路径，不为普通纸片组装默认调用视频生成 API。批量脚本属于 `video-producer`，不再使用独立 `collage-broll` 工具。

## 声音、成片与交付（Stage 11–15）

Stage 11 填实 `audio/collage-audio-plan.json` 的 `sound_policy`，默认写 `silent`；需要声音时写 `user-voice` 或 `approved-tts` 并落实最终音轨。Stage 12 每条使用只含一个片段的 manifest，调用 `video-producer assemble` 将 Stage 10 片段原样交接到项目成片路径，例如：

```json
[{"name":"item-01","path":"render/item-01/final.mp4"}]
```

```bash
video-producer assemble <project> --manifest render/item-01/segments.json \
  --output video-item-01.mp4 --verify-fps 25
video-review <project>/video-item-01.mp4
video-producer motion-audit <project> --video video-item-01.mp4 \
  --audit-output review/item-01-motion-audit.json
video-producer normalize <project>/video-item-01.mp4 \
  --output <project>/video-item-01_normalized.mp4 --silent-ok
```

有声片即使传 `--silent-ok` 也照常归一；无声片经 ffprobe 确认没有音轨后，归一化命令原样输出并写 `.normalization.json` 记录不适用。Stage 13b 的审核须逐层填证据并给出 verdict；Stage 14 按 Brief 制封面。批量条目分别执行 Stage 12–15，审核文件与交付说明要按条目对应，不能用一条结果代替全批。

## 交付

交付每条归一化成片、封面、`final-deliver.md` 的绝对路径；说明列出每条隐喻对应原句、素材来源、预览联系表、GATE A/B 记录与视频 QA 结果。`composition/` 保留，便于只改入场顺序或纸片位置后确定性重渲。
