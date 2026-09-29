# Deck Talk — 幻灯讲解口播视频

type 类 workflow；`Brief.workflow=deck-talk`。本文指导 Stage 1–2 的逐页/段脚本、自检与 GATE A 质检，并约定后续制作、验收方式。通用 Stage 0→15、GATE A/B、返工上限与交付约定全程适用；每个阶段都要有对应动作与产物，不能以类型 workflow 为由跳过阶段。

## 类型与输入契约

以一条确定的口播音频为时间轴，大画面可为设计驱动的幻灯流、B-roll，或两者混排。默认 16:9、1920×1080、30fps。

| 模式 | presenter_source | 输入与分工 | 人物画面 |
|---|---|---|---|
| 1 · 实拍口播 | footage | 用户录好的口播视频；通常由 main 先用 talking-head-cut 完成语义剪辑，CP 接收剪好的成片，保留其原音轨 | 原视频小窗 |
| 2 · 数字人 | avatar | 已授权肖像 + 用户/main 音频；或明确批准的合成声音。用包内 liveportrait 工具检测并生成口型视频 | 数字人小窗 |
| 3 · 音频讲解 | audio（兼容 none） | 用户/main 提供音频，CP 按句边界制作 B-roll / 幻灯画面，保留原声 | 无小窗 |

声音是三种模式的共同主线。不得仅因不露脸就重做声音；不得把复刻/设计生成的声音登记为真人原录音。main/用户交付的稿件、已录好的音频均锁定，CP 不改写。

| Brief 字段 | 要求 |
|---|---|
| workflow | deck-talk |
| voiceover | 甲方锁定的 voiceover.md 或录音绝对路径；口播归 main/用户，CP 不重写。无小窗纯旁白按通用旁白分工，由 CP 写稿、GATE A 交审 |
| presenter_source | footage / avatar / audio（兼容 none）；明确选择，不静默去掉小窗 |
| presenter | footage 提供 main 已剪视频路径与授权；avatar 提供肖像路径与授权；audio 不提供人物素材 |
| audio | audio/avatar 提供锁定音频路径；footage 从已剪视频提取原音轨。需合成时明确音色档案 voice.json 与声音来源 |
| visual_source / audio_origin | slides / broll / mixed；声音来源 recorded / cloned / designed / stock-tts，不得混淆 |
| materials | 图表数据、单位、日期范围、来源；图片绝对路径与授权；标记第三方平台界面、品牌/logo 与版权状态，不根据动画效果编造数值 |
| form / gates / acceptance | 规格、字幕与封面要求、两道闸门批准人及代理范围、验收标准 |

**avatar 使用包内 `tools/liveportrait/SKILL.md`**：先准备唯一最终人声音轨，再生成人物口型；不另建公共 avatar-gen 技能。若要复刻声音或设计音色，先读公共 awk-tts，保存音色档案、试听确认后再合成长音频。优先沿用用户原声。

## 基线阶段的 Deck Talk 产物

Stage 3–10 仍逐阶段执行 `video-producer` 同名命令，生成对应脚手架并填写实质内容；`deck-render`、`liveportrait` 等负责实际渲染。通用命令的影视镜头字段不适用时，填写本类型的逐页/段构图、动作、音频对应与授权，不虚构机位或角色三视图。空模板不算阶段完成。

| Stage | 本类型动作与产物 |
|---|---|
| 0 | 核对输入契约、素材存在性、同源口播、小窗来源；未定分支先澄清 |
| 1 | script-write 生成 `script/deck-script.md` 模板，填每页单命题、版式、图表数据、素材槽、对应口播原文段与小窗方案 |
| 2 | script-self-eval 按 slides/mixed 或 broll 分别生成逐页/段自检模板，评估密度、来源、遮挡、句边界与真实动作；不改锁定口播 |
| 3 | `storyboard-build` 把逐页/段脚本拆为镜头表，记录命题、构图、口播句段、人物位置与预计时长；落 `storyboard/storyboard.json` |
| 4 | `shot-decompose` 记录每镜进入/离开时的视觉状态、真实动作、渲染方式与口播对应；落 `storyboard/shot_decompose.json` |
| 5 | `character-register` 登记 footage/avatar 的身份、授权、同源音轨和小窗位置；audio 模式明确“无人物”；若画面另含跨镜生成角色，再登记特征与参考图。落 `characters/registry.json` |
| GATE A | 呈交脚本、逐页/段分镜、画面状态、人物/声音方案；按通用闸门等待批准 |
| 6 | `slot-plan` 按镜规划图表、图片、B-roll 与口播对应，落 `slots/slot-plan.json`；给出每页/段的可核验素材槽 |
| 7 | `asset-resolve` 入库并 probe 图表/图片/真人素材，记录来源授权、弃选项；逐张检查第三方界面截图、竞品/无关品牌、logo 与版权状态，未获准发布的画面换成自有示意图。合成声音先落实音色与试听，检查真峰值与可闻削波；保护后音频作为数字人、字幕和成片的唯一同源输入。可先对齐字级时间戳，落 `script/deck-spec.json`，Stage 11 再核定最终声画对齐 |
| 8 | `slideshow-risk` 仍做合成前审核，落 `slots/slideshow-risk.json`；按可读性、标点边界节奏、素材覆盖、真实动作、来源授权与第三方品牌画面评估。幻灯元素动画与 B-roll 画面动作分别验收，不套通用动镜头占比阈值；fail 必返工 |
| 9 | `delivery-promise-lock` 逐页/段锁定时长、人物模式、音频来源、素材和真实动效，落 `slots/delivery-promise.json`；Stage 13b 按该承诺核验 |
| GATE B | slides/mixed 的幻灯段执行 scaffold + check + preview；交逐页/逐段联系表、真人小窗取帧/位置方案、素材来源、成本估算。avatar 必须先交 5–10 秒样片再批准全量；audio 模式交声音与 B-roll 取帧，不索要露脸视频 |
| 10 | `render-shot` 建立 `render/deck-render-plan.json`，再依计划实际渲染：slides 用 deck-render；broll/mixed 用 clip-trim + assemble 合成底画面；footage 沿用 main 已剪视频，avatar 用 liveportrait generate / resume。计划文件不代表渲染完成 |
| 11 | `mix-audio` 建立 `audio/deck-audio-plan.json`，核对最终唯一干声、字幕时间戳和底画面时长；需要时在本阶段完成配音/对齐，不改变锁定原声；干声不含 BGM，空计划不算完成 |
| 12 | deck-compose 按 footage/avatar/audio 合成 → burn-srt；需要 BGM 时在小窗合成后 ducking 混入，再做后续审片；有片头尾再 assemble，使用 hard 拼接，字幕与音频随主片一起平移 |
| 13a | 公共 video-review，verdict=pass 才可交付 |
| 13b | 调 `motion-audit` 按 Stage 9 承诺，对幻灯段做 HTML 动效验收、对 B-roll 段核验真实画面动作与口播对应，落 `review/deck-motion-audit.json`；不用通用 motion_led 的素材占比口径 |
| 13c | normalize 必跑，-14 LUFS；最终交付文件取归一化后的版本 |
| 14–15 | 按 Brief 制作含主文案的封面；交成片、封面、final-deliver.md 的绝对路径 |

## 设计与声画对齐

1. 每页一个命题，标题最多 32 字、要点最多 4 条且各不超 48 字。段落口播不逐字塞进幻灯。图表一页表达一个关系，标出单位、范围、来源。
2. 排名/类别对比用柱状图，时间变化用折线图，步骤关系用流程图，单指标可用 KPI 卡。脚手架内置正数柱状图，其余在 scene HTML/SVG 中设计；引用 registry 块须检查许可证、将字体与依赖本地化，不能引入上游 workflow。
3. 有小窗时整侧预留版面，字幕留底部安全带。脚手架默认匹配 1080p、小窗宽 22%、1:1、margin=32、subtitle-safe=160；调整 corner/size/aspect 后须重新目检。真人居中裁切可能切脸，必要时提前裁剪或改 aspect。
4. 声画只用一条源音频：用于 narration-align、页时长、字幕、最终合成；presenter 自带音轨不混入。实拍必须同源，不能只因时长相同就认为口型对齐。
5. 翻页落句号、逗号等标点对应的字级时间戳，不以 SRT cue 边界代替；先用 `video-producer deck-boundaries --subtitle /absolute/narration.subtitle.json --spec /absolute/deck-spec.json --output /absolute/review/page-boundaries.json` 核对。录音 ASR 则传 `narration-segments.json`，须含逐字/词且保留标点；verdict=fail 时调整页时长再渲染。每页 3–30 秒。过短合页、过长拆页，在 deck-script 记对应原文范围；不改口播。末页时长覆盖尾音，音频与视频总长偏差超过 0.12 秒时返工。
6. `source` 保存素材来源与授权，`caption` 只写观众该看到的图注；制作备注不得写入 `caption` 或 HTML 可见文字。GATE B 与交付前逐页看截图，查品牌/logo、图注和制作痕迹。

## GATE A / B

GATE A 看脚本及 Stage 3–5 产物：逐页命题与对应原文、分镜、画面状态、图表来源、小窗与人物授权、预估节奏。GATE B 看 Stage 6–9 的素材与承诺：逐页 PNG 联系表、小窗裁切/位置与口型预检、声音方案、API 成本及已批准范围。两个闸门分别呈交后停下等 Brief owner；已有代理批准则记录到 gates 后在范围内继续。

人工 review 不可由 check 的退出码替代。GATE B 后改图表数据、稿件、素材来源或小窗方案需重新确认受影响范围；只调圆角/位置等实现细节按原批准范围修正。

## 工具链

调用前读 `tools/deck-render/SKILL.md` 和 `tools/video-producer/SKILL.md`。各命令是独立阶段入口；中间结果由脚本落盘。不要手写 ffmpeg 或另建 HTML 录屏脚本。

```bash
deck-render scaffold /absolute/project/composition --spec /absolute/project/script/deck-spec.json
deck-render preview /absolute/project/composition --output /absolute/project/review/slides-v1
deck-render render /absolute/project/composition --output /absolute/project/render/slides.mp4
# 模式 1：音轨从 main 已剪口播视频中自动提取
video-producer deck-compose --mode footage --base /absolute/project/render/base.mp4 --presenter /absolute/main/cut.mp4 --output /absolute/project/composed.mp4

# 模式 2：先生成数字人，再使用任务记录锁定的视频和音频
liveportrait generate --image /absolute/portrait.png --audio /absolute/project/audio/narration.wav --output /absolute/project/render/presenter.mp4
video-producer deck-compose --mode avatar --base /absolute/project/render/base.mp4 --avatar-job /absolute/project/render/presenter.liveportrait.json --output /absolute/project/composed.mp4

# 模式 3：底画面可以直接是已按音频排好的 B-roll
video-producer deck-compose --mode audio --base /absolute/project/render/broll.mp4 --audio /absolute/project/audio/narration.wav --output /absolute/project/composed.mp4
```

`deck-compose` 校验模式输入并调用 pip-compose，记录唯一音频的路径与哈希。所有底画面必须已与锁定音频等长（容差 0.12 秒），不循环/变速声音迁就画面；avatar 模式还须保持 job 的音频路径、哈希和时长，不手改 job 音频字段。人物小窗变化只重跑合成及字幕/审片。技术调试可用 `pip-compose --dry-run` 检查区域；对外交付遵循明确的三模式契约。

## 中断后续跑

重新接单先读 `brief.md`、两道闸门记录、`script/deck-spec.json`、`slots/delivery-promise.json` 和已有媒体；对照 Stage 10–13 的实际文件与哈希，只接着完成缺失步骤。已有 LivePortrait job 用 `liveportrait resume --job <job>` 查询和下载，不重复提交；已有 slides 且与当前 spec 一致时直接复用。审片或 normalize 尚未完成，不能把中间 MP4 当交付。LLM 网络错误由运行框架处理，本 workflow 的续跑依靠落盘产物与重新派单。

B-roll 使用 `clip-trim` 切段、`assemble --manifest` 按序拼接，时间轴从锁定音频的句边界确定。mixed 先将幻灯段和 B-roll 段归一化后拼接；无幻灯的 audio+broll 模式不调用 deck-render，不强制 HTML 动效证明。主音轨在最终合成时替换底画面全部原声。BGM 如有需求，三模式合成后再按通用 ducking 混音，保留原音频来源记录。

## 画面验收（Stage 8/9/13b）

以下 HTML 条目只适用于 slides/mixed 中的幻灯段；B-roll 段逐段核验素材授权、语义对应、入出点、真实动作及与音频的对齐，不要求 HTML 元素动画。

- 每页必须有元素级入场/图表演进/关系展开；仅整页淡入或静图 Ken Burns 不通过。脚手架提供标题与正文分层入场，图表再加柱体动画；停留阅读段允许静止。
- `deck-motion-plan.json` 每页记录 scene_id、动画目标、局部起止、口播段落与全局翻页时刻。承诺以具体动作描述，不虚填 motion_ratio。
- 用 `deck-render preview --at` 抽动画前/中/后、每个翻页两侧；必要时播放成片观察实际动作。证据必须逐页覆盖，只有中点联系表不能证明动画。
- `deck-motion-audit.json` 逐页记录承诺、证据路径、是否兑付，核查数据不跳变、中文无缺字、小窗不遮挡、翻页与字幕/口型同源；任一项失败就返工。最终 verdict=pass 方可交付。

## 工作区与交付

```text
output_videos/<topic>/
  brief.md / voiceover.md
  script/deck-script.md / deck-spec.json / decisions.json
  storyboard/storyboard.json / shot_decompose.json
  characters/registry.json
  gates/gate-a.md / gate-b.md
  raw_materials/                    # 来源与授权
  audio/narration.mp3 / subtitles.srt / 时间戳
  composition/index.html / compositions/ / assets/
  slots/slot-plan.json / asset-resolve.json / slideshow-risk.json / delivery-promise.json
  render/slides.mp4 / presenter.mp4
  review/slides-v1/ / deck-motion-plan.json / deck-motion-audit.json / verdict.json
  video.mp4 / cover.jpg / final-deliver.md
```

交付默认有声 MP4，声画同源、技术自检通过、响度归一化；说明中列规格、耗时、素材授权、工作流与人工审片结论。保留 composition 源码便于改片。

## 不适用

- 人物全屏、不采用本工作流三模式排布：走 expert-video 通用制作流程，Brief 不指定类型 workflow。
- 纸拼贴视觉隐喻 B-roll：collage-broll。
- 可导航 PPT/deck、实时交互数字人：不属于本 workflow。
- 不承诺用数字人/声音复刻规避平台检测；真实录音与合成声音按实际来源登记。
