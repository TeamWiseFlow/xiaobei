> 2026-09-25 流程更新：旧 narration-video 已删除；deck-talk 继续完整执行通用 Stage 0→15，Stage 3–10 改用同名命令生成逐页/段产物，Stage 11 与 13b 也使用类型化脚手架，不再跳过。下文的“阶段裁剪表”和 narration-video 边界仅作原计划记录，现行执行契约见 `crews/content-producer/skills/expert-video/workflows/deck-talk.md`。

> 2026-09-23 实施更新：采用百炼 LivePortrait，作为 expert-video 内部工具，不创建公共 avatar-gen。deck-talk 提供 footage / avatar / audio 三模式，audio 支持直接 B-roll+原录音；最新执行契约见 `crews/content-producer/skills/expert-video/workflows/deck-talk.md`。awk-tts 的复刻/设计默认凭据顺序为火山→百炼业务空间→Agent Plan，音色档案锁定创建供应商及模型。下文保留最初方案供追溯，供应商与公共技能规划以本更新为准。

> 2026-09-25 进度核对：当前批准范围的工具与三模式 workflow 均已实现；原 Phase 0.2 即梦、0.3 HeyGen、1.3 公共 avatar-gen 被 LivePortrait 内部工具方案取代，不再是待实现项。Phase 4 的真实口播/数字人完整交付仍未验收，Windows 安装与字体渲染也缺少实机验证；火山自定义音色仍待有可用槽位后验收。§2–8 与 §9 旧勾选保留原计划记录，不能据此推断当前仍要开发即梦/HeyGen。

> 2026-09-25 字体策略更新：Noto Sans CJK SC 用于改善 Linux/macOS 的中文渲染；Windows 默认使用系统微软雅黑，不再下载 Noto。字体选择与 HTML 字重声明、片尾、字幕默认值保持一致；Windows 实机渲染尚待验证。下文 2026-09-20 的 Noto 字体实测记录只针对 Linux。

# deck-talk Workflow 调研与开发计划

> 定稿：2026-09-19 ｜ 更新：2026-09-23 ｜ 状态：**本地渲染/小窗工具、三模式 workflow、LivePortrait 与音色定制已实现；百炼设计/复刻/数字人样片已实测，火山自定义音色待已购槽位验收**
> 关联文档：`video-capability-replanning-2026-07-25.md`（§6.3/§6.4/§7/§8：HyperFrames / html-video / OpenMontage / ViMax 四上游定位与吸收判定）。本文是该文档所定"模板路径"（L3 html-video 创作链路方法论 + L2 HyperFrames 执行底座）的**首次生产落地计划**。
> 调研执行：2026-09-19 两个并行调研代理（渲染路径 / 数字人方案），全部基于当日 `git pull` 后的最新 HEAD。

---

## 1. 需求

为 Content Producer 的 `expert-video` 新增一个与 `collage-broll.md` 平级的 **type 类 workflow**，制作**带 B-roll 的讲解类口播视频**：

- **大画面**：PPT 风格幻灯片流，支持图表、图片素材插入、动效
- **角落小窗**（左下/右下）：真人口播视频，两种来源——
  - (a) 用户提供的实拍/录屏素材
  - (b) 数字人合成（需评估 HyperFrames 与 OpenMontage 的数字人模块、本地算力要求、在线 SaaS 可用性）

## 2. 决策记录（2026-09-19 用户拍板）

| # | 决策点 | 结论 |
|---|--------|------|
| 1 | workflow 命名 | **`deck-talk`**（规划期暂名 slide-explainer；不带 "broll" 字样——仓内 B-roll 已被 collage-broll 占用为"垫口播的素材动画"语义） |
| 2 | B-roll 渲染路径 | **HyperFrames 直接依赖**（npm，pin 版本）；html-video **只借鉴不依赖** |
| 3 | 数字人路线 | **SaaS API 双供应商路由**：火山即梦 OmniHuman 首选 + HeyGen 备选；本地模型路线排除（本机无 CUDA） |
| 4 | avatar-gen 归属 | **公共 `skills/`**（main 备素材与 CP 小窗都可能用，符合 ≥2 crew 共用规则） |
| 5 | PiP 小窗合成 | **`video-producer` 新子命令 `pip-compose`**（ffmpeg 后期叠加为主路径）；HF composition 内嵌合成作文档内可选路径 |
| 6 | 默认画幅 | **16:9 1080p**（PPT 原生比例；竖屏 9:16 下 16:9 幻灯大量留白）；Brief 可覆盖 |
| 7 | 配套工具命名 | 渲染 wrapper 定名 **`deck-render`**（与 workflow 命名对齐，对标 collage-broll 工具形态） |

## 3. 调研结论

### 3.1 调研基线（sandbox 六仓 2026-09-19 已 pull 最新）

| 仓 | HEAD | 上游日期 | 备注 |
|----|------|---------|------|
| `~/wiseflow-pro/hyperframes` | `ac0d8ced2` | 2026-09-19（当天） | 较旧基线 e2e61b0 **+4515 commits**，极活跃；CLI v0.8.50 |
| `~/wiseflow-pro/html-video` | `c414ecc` | 2026-06-22 | fork（bigbrother666sh），已与 nexu-io 上游同步（落后 0）；**已 3 个月无提交** |
| `~/wiseflow-pro/OpenMontage` | `08e2151` | 2026-09-05 | +446 commits（多为 provider 扩容）；与记忆 67 跟进基线一致；AGPLv3 |
| `~/wiseflow-pro/openclaw-plugin-heygen` | `d15f6e5` | 2026-04-27 | 已最新；MIT；HeyGen 官方维护 |
| `~/wiseflow-pro/liveavatar-agent-skills` | `88960dc` | 2026-09-10 | 已更新；MIT |
| `~/wiseflow-pro/liveavatar-sales-agent` | `b5ce65c` | 2026-08-30 | 已最新；MIT |

### 3.2 B-roll 渲染路径：HyperFrames vs html-video

| 维度 | **HyperFrames**（HeyGen 官方，Apache-2.0） | html-video（nexu-io，Apache-2.0） |
|---|---|---|
| 渲染方式 | headless Chrome（Puppeteer ^25）**逐帧 seek 截图 + ffmpeg 编码**——确定性、同输入同输出、永不掉帧（`docs/concepts/determinism.mdx`） | ⚠️ adapter 运行时**并不调用 HF 引擎**：Playwright chromium `recordVideo` 实时录屏 → webm → libx264（`packages/adapter-hyperframes/src/render.ts` 头注释自认；README "frame-by-frame" 与代码不符）。非确定性，慢机可能掉帧 |
| 帧/场景模型 | composition = 一个 HTML：`data-composition-id/width/height` 定画布，元素 `class="clip"` + `data-start/duration/track-index` 定时间轴；GSAP paused timeline 注册 `window.__timelines` 变 seekable（另有 CSS/Lottie/Three.js/Anime.js/WAAPI/TypeGPU 适配器） | content-graph IR（节点+边+拓扑排序→帧序），agent loop 填模板 |
| 图表/素材块 | **50+ registry 块**：data-chart、bar-chart-race、mk-line-graph、flowchart、world-map/us-map、code-diff/code-highlight、chatgpt/claude-exchange 等，`npx hyperframes add data-chart` 即装 | 24 个模板（frame-pentagram-stat / frame-swiss-grid / frame-decision-tree / frame-data-chart-nyt 等 PPT 风），**无数据驱动图表 API**，靠 agent 填 HTML |
| PiP 口播小窗 | ✅ `skills/talking-head-recut` 现成 PiP 版式（内容卡全屏 + 真人视频圆角角落小窗）；`docs/guides/avatar-presenter.mdx` 官方合成指南；`npx hyperframes remove-background`（本地 u2net）抠像 | ❌ 无 |
| 性能（1min 1080p30） | **≈ 1–2.5 min 单机**（官方实测 300 帧 9.8–25s 外推，本机未实测）；`--workers 1-24` 并行（每 worker 一个 Chrome ≈256MB）；4K ≈ 4 倍慢 | ≈ 实时录制时长（≥1x）+ 转码 |
| GPU | **不需要**：Chrome 捕获默认 SwiftShader 软件渲染，ffmpeg 默认 CPU x264；≤8GB RAM 自动 low-memory 模式；可选云渲染（HeyGen 托管 / AWS Lambda / GCP Cloud Run） | 不需要 |
| 运行时 | **Node ≥22 + ffmpeg**，`npx hyperframes` 即用，npm 已发布 | Node ≥20 + pnpm ≥9 + playwright chromium；**未发布 npm**，需 clone + build；根依赖含 remotion/react（安装重） |
| 成熟度 | 4516 commits、HEAD 为调研当天、HeyGen 生产背书、ADOPTERS 含 tldraw/TanStack、~21K star | 139 commits、2026-05-26 启动、单人主导（~116/139）、3 个月未提交 |

**结论**：渲染核心直接采用 **HyperFrames**；html-video 的价值转为**借鉴**——PPT 风模板（RFC-07 license 闸只收 MIT/Apache/BSD/CC-BY，license-clean 可直接搬）、"PPT 设计 skill→视频模板"转换方法论、content-graph IR 思想、`CLAUDE.md` 工程教训（混流 concat 必须用 concat filter 重建时间轴、字体冻结防跳闪、per-frame 显式时长 durationMode='explicit'）。

**用户原认知修正**："html-video 底层基于 HyperFrames"只在创作范式与模板来源上成立，其渲染 adapter 运行时不调 HF 引擎——两者不是上层/底层关系，直接选 HF 无中间层损失。

**两个关键规避点**：

1. ⚠️ **HF `/slideshow` skill 不能出 MP4**：输出是可导航 deck（`hyperframes present`），render 会静默截断只出第一页（`skills/slideshow/SKILL.md:22-26`）。正确范式 = **"每页 slide = timeline 上一个 scene"**，走 faceless-explainer/general-video 的组织方式，正常渲染。
2. **不吸收 HF 的 creation workflow skills 进 CP 路由**（重规划文档 §8.7 既定铁律 + OpenMontage vendoring 决策验证：原子能力可吸收、工作流路由不可吸收，会与自家路由打架）。HF 只当渲染引擎 + domain skill 参考；deck-talk workflow 文档自己写。

**调研时未验证项**：本机实际渲染耗时、代理环境依赖拉取、中文渲染、图表动画确定性——**已全部由 Phase 0.1 spike 验证通过（2026-09-20），实测记录见 §3.6**。HF 新增 sdk 包接口稳定性未评估（不使用即不受影响）。

### 3.3 数字人方案评估

#### 本地模型路线——本机全部出局

本机为云 VM（8 vCPU / 15G / **virtio-gpu，无 NVIDIA CUDA**）。OpenMontage 本地数字人工具（`tools/avatar/talking_head.py`：SadTalker/MuseTalk；`lip_sync.py`：Wav2Lip/MuseTalk）均声明 `LOCAL_GPU` + torch/CUDA 依赖、≥4GB VRAM、模型需外部 clone、工具级 EXPERIMENTAL；硅基 HeyGem.ai 开源本地方案需 8–12G 显存（口径冲突未验证）且以 Windows 为主。**纯 CPU 理论可跑但极慢且非设计路径，判不可行。**

#### OpenMontage 数字人模块现状（AGPLv3，只借思路不搬代码）

- **SaaS 轨**：`kling_avatar.py`/`kling_lip_sync.py`（快手可灵官方 API，默认新加坡端点，**大陆直连未验证**）；`heygen_video.py`（HeyGen 作为多模型网关：Veo/Kling/Sora v2/Runway/Seedance/LTX，非 avatar 专用）。
- 本次 pull 新增国内直连 provider：`jimeng_video.py`（**火山引擎即梦**，visual.volcengineapi.com，HMAC-SHA256 V4 AK/SK 签名，异步提交+轮询）、`seedance_ark.py`（火山 Ark 直连）——**尚未接即梦 OmniHuman 数字人 API，但同域签名基建已就绪，扩展成本低**（对我们 = 签名思路可参考，代码自写，AGPL 隔离）。
- `pipeline_defs/talking-head.yaml`（v2.0 beta）**不是数字人生成**，是真人实拍素材精编管线（转录→跳剪→字幕→合成），纯 CPU 可跑——对来源 (a) 用户实拍素材是现成方法论参考。
- `avatar-spokesperson.yaml`（production）才是数字人管线：TTS → talking_head/lip_sync → face_enhance → compose；两条纪律值得吸收：**"先生成 5 秒样片确认质量再全量"**（asset-director.md:33）；数字人不可用时显式走 No-Avatar 路径（图形+旁白），不静默降级。
- PiP 合成范式：`video_compose` 有 `"presenter" → Remotion TalkingHead` 合成组件 + 独立 overlay 操作；`skills/creative/talking-head-gen-usage.md` 工作流 #4 明确"talking_head 输出作 presenter 层 + 叠加图表/录屏"——**"角落口播小窗 + 大画面图形"模式在上游已有现成路径**（非 GPU 密集）。
- grep 全仓无腾讯智影/百度曦灵/硅基/闪剪集成。

#### openclaw-plugin-heygen（MIT，HeyGen 官方 OpenClaw 插件）

- 把 HeyGen 注册为 OpenClaw 内置 `video_generate` 工具的 provider（模型串 `heygen/video_agent_v3`），封装 **v3 Video Agent API**（`POST https://api.heygen.com/v3/video-agents` 异步生成，非 Streaming/Interactive Avatar）。
- 认证 `X-Api-Key`（`HEYGEN_API_KEY=hg_...`）；avatar_id/voice_id/style_id 指定形象声音；landscape/portrait；插件侧上限 300s；≤20 张参考图；webhook 回调。
- 计费 credit 制（第三方评测未验证：个人版约 $48/月起，Avatar 3 ~3 credits/min，Avatar 4/5 ~20 credits/min）；配套 ClawHub `heygen-skills` 可上传照片创建专属 avatar。
- **大陆可达性：需走代理（本机 GitHub 都需 7897），未验证。**
- 另：HF 生态原生集成 HeyGen CLI（`heygen video create --type avatar/image`、`heygen lipsync`、TTS starfish），OAuth 登录有免费额度——HeyGen 备选路线有两个接入形态可选（openclaw 插件 / heygen CLI），开发时再定。

#### LiveAvatar（排除）

HeyGen 实时交互数字人平台（api.liveavatar.com，LiveKit/WebRTC 流式），面向对话场景（客服/销售/教学），**不产出离线 MP4**，与本场景错配。其 `gpt-live-demos.md` 中"avatar 缩角落 + 大屏动态 overlay"版式与目标 PiP 同构，可作版式参考；LITE 模式（自带音频流、云端渲染、~1 credit/min）录制充当小窗属 hack，列次选不采用。未来做直播/实时交互数字人时再评估。

#### 2026 大陆可达数字人 SaaS 横向

| 方案 | 本地/SaaS | 算力或费用 | 大陆可达性 | License/商用 | 成熟度 |
|---|---|---|---|---|---|
| OpenMontage talking_head（SadTalker/MuseTalk） | 本地 | CUDA ≥4GB VRAM，**本机不可行** | ✅ 离线 | 仓 AGPLv3；模型 license 未验证（Wav2Lip 商用存疑） | EXPERIMENTAL |
| OpenMontage kling_avatar | SaaS | 可灵 API 计费（单价未查到） | ⚠️ 默认新加坡端点，直连未验证 | AGPLv3 仓 + API 付费 | EXPERIMENTAL |
| openclaw-plugin-heygen（v3 Video Agent） | SaaS | credit 制，~$48/月起（未验证） | ❌ 预计需代理 | 插件 MIT；HeyGen 商业条款 | 官方插件，生产可用 |
| LiveAvatar | SaaS 实时 | LITE ~1 credit/min | ❌ 需代理（未验证） | 两仓 MIT；平台计费 | 生产，但实时交互非离线成片 |
| **火山即梦 OmniHuman** | SaaS | **快速模式 1 元/秒**，免费态并发 1 | ✅ **直连**（火山 AK/SK） | 商业 API | 官方 API 已开放（2025-09 起），文档新，**本机未实测** |
| 百度曦灵 | SaaS | 照片数字人 20 元/次；合成按套餐 | ✅ 直连 | 商业 API（有 MCP） | 成熟 |
| 腾讯数智人/智影 | SaaS | 套餐制（未细查） | ✅ 直连 | 商业 API | 成熟 |
| HeyGem.ai（硅基开源） | 本地 | 8–12GB VRAM（口径冲突） | ✅ 离线 | 开源（条款未验证） | 社区活跃，非本机可用 |

**结论**：来源 (b) 数字人收敛为 SaaS API——**首推火山即梦 OmniHuman**（大陆直连、单图+音频→口播视频、1 元/秒、与仓内火山生态同源）；**备选 HeyGen**（质量标杆，代理+credit，定位出海内容线）。可灵 avatar 列观察（待验证大陆端点）。百度曦灵/腾讯数智人不接（多供应商维护成本 > 收益，即梦+HeyGen 已覆盖国内外两线）。

**凭据注意**：即梦 OmniHuman 走 visual.volcengineapi.com 的 **AK/SK V4 签名**，与仓内视频生成使用的 `VOLC_SEEDANCE_API_KEY`（火山方舟 Ark，Bearer key）**是两套凭据**，也与 `VOLC_ASR_*` 不同——需新开通智能视觉服务并新增 env（命名开发时定，如 `JIMENG_AK`/`JIMENG_SK`），缺失时子命令 exit 2 交 IT engineer，不静默降级。

### 3.4 本机运行时核查（2026-09-19 实测）

| 项 | 状态 |
|----|------|
| node | v26.8.2 ✅（HF 要求 ≥22） |
| pnpm | 11.2.2 ✅ |
| bun | ❌ 无（HF 用户侧不需要，仅贡献者开发用） |
| Chrome | `/usr/bin/google-chrome` ✅（Puppeteer 自带下载策略待 Phase 0 验证代理行为） |
| ffmpeg/ffprobe | ✅（expert-video 既有依赖） |
| CPU/RAM | 8 vCPU / 15G（HF workers 有余量；>8G 不触发 low-memory 模式） |
| GPU | virtio-gpu，无 CUDA（不影响 HF 渲染；排除本地数字人） |
| 中文字体 | Noto Sans CJK 在位（motion-graphics 已在用） |

### 3.5 调研时仓库现状盘点（2026-09-19，后续落地见 §9）

**workflow 文档范式**（照 collage-broll.md 骨架）：类型定义 → 输入契约（Brief 侧）→ 阶段裁剪表 → Phase 细则 → GATE A/B → 工作区 → 交付 → 不适用。

**与 narration-video 的边界**（必须显式消歧）：narration-video 已覆盖"口播类（真人出镜/数字人/真人录音）"，其形态是人声主干 + 素材按时间戳配画面（口播人全屏或素材全屏）；**deck-talk 的差异 = 大画面是设计驱动的幻灯片流（图表/图示/要点排版）+ 口播人缩至角落小窗**。路由信号："PPT/幻灯大画面 + 口播小窗""讲解类口播视频"。

**工具缺口**：

1. 仓内**没有任何 HTML 渲染路径**——Stage 10 现有两条路：render-shot（AIGC i2v）与 motion-graphics（Pillow 逐帧）。deck-render 是第三条路（HTML 确定性渲染），也是重规划文档"模板路径"的首次落地。
2. motion-graphics **无 video 元素类型**（元素仅 text/card/photo_circle/glow/band/highlight_zone/progress_bar/custom；video 只能当 background）——视频叠视频的 PiP 合成无现成子命令，且"禁止直接写 ffmpeg"铁律要求必须走 wrapper → 新增 `pip-compose`。
3. 仓内**没有数字人工具**——"数字人"仅在文档中作为一种口播形态被提及（expert-video SKILL.md L35/43/71、CP AGENTS.md L20、main 三包"视频全案分工硬边界"段）→ 新增公共 `avatar-gen`。

**闸门冲突**：Stage 8 `slideshow-risk`（六维幻灯风险 ≥4.0 fail）与 delivery-promise 的 "text_card/chart/kpi_grid 是动画幻灯不计入 motion、motion_ratio ≥0.70" 判据（重规划 #48/#49）会**误杀本类型**——deck-talk 天然幻灯流。处置：阶段裁剪表将 Stage 8 重定义为"幻灯动效等级自检"（必须用 HF 真动画：元素入场/图表动画/转场；禁止静图 Ken Burns 充数），motion_ratio 判据对 HTML 动画路径重定义；必要时给 slideshow-risk.py 加 workflow 感知参数（开发时定）。collage-broll 先例：Stage 6–9 "由静帧生成替代"。

**路由与文档同步触点**（Phase 3 清单）：

| 文件 | 触点 |
|------|------|
| `crews/content-producer/skills/expert-video/SKILL.md` | 类型 workflow 表（L68-72）+1 行含消歧；工具表 + `deck-render`/`avatar-gen`；env 依赖段 |
| `crews/content-producer/AGENTS.md` | 能力路由表（L16-24）+1 行，**插在 narration-video 行（L20）之前**（"首个匹配行即执行"） |
| `crews/main/skills/expert-{douyin,xhs,wx-channel}/workflows/content-production.md` | Brief 模板 workflow 枚举行（各 ~L203）+`deck-talk` |
| `crews/main/skills/viral-chaser/SKILL.md` | 类型→CP workflow 路由表（L243-246）+1 行 |
| 仓根 `requirements.txt` | avatar-gen 如有新 Python 依赖 |
| `CHANGELOG.md` | 记录 |

main 三包 SKILL.md 的"视频全案分工硬边界"段为通用表述（已含"数字人"字样），**无需改动**。

### 3.6 Phase 0.1 spike 实测记录（2026-09-20，全部验收项通过）

Spike 工作区 `/tmp/deck-talk-spike/probe`（hyperframes 0.8.50 pin + gsap 3.14.2 本地化；根清单 + 三场景子合成结构；30s 1080p30 中文幻灯样片：标题页 / SVG 柱状图动画页 / 左图右文要点页）。

| 验收项 | 实测结果 |
|--------|---------|
| 代理环境依赖拉取 | npm install 成功（npmjs.org 源 + 7897 代理）；**系统 Chrome 153 自动探测、零下载**；`doctor` 全绿（ffmpeg 6.1.1 / Node 26.8.2 / 8 核 / 15.6G / shm 8G / Docker 在位） |
| 中文渲染 | Noto Sans CJK SC 正确，字重分层正确（Bold 标题 / Light 副标题 / Regular 标签，抽帧目检通过） |
| 动画确定性 | **两次独立渲染字节级相同 sha256**（`e523a1ed…`，未用 --docker）；SVG+GSAP 柱状图 stagger 动画逐帧正确 |
| 耗时 | 30s 1080p30（900 帧）= **机内 36.7s**（capture 21.9s + encode 12.7s；workers auto=3；SwiftShader 软件渲染；beginframe capture 模式）；wall 78s（含 ~40s CLI/浏览器启动开销，长片摊薄）→ **1min 1080p ≈ 2min wall 外推**，处调研外推区间（1–2.5min/min）较优一侧 |
| 质量闸门 | `check` 全绿：lint 0 错 / runtime 0 错 / **对比度 37/37 WCAG AA** / layout 1 info（图表动画中间态 svg 溢出，非阻塞）；spike 期间被该闸门抓到真实设计问题（橙序号白底 2.0:1、浅灰页码 2.2:1，均 <3:1），修色后通过——闸门有效 |

**新发现（已吸收进 deck-render / workflow 设计）**：

1. **字体硬要求**：lint 要求所有 font-family 有 `@font-face` 声明（含系统字体），系统 CJK 字体用 `src: local('Noto Sans CJK SC Bold')` 等四档字重声明；**每个子合成文件须各自重复声明**（lint 按文件独立校验，根文件声明不覆盖子文件）。registry blocks 默认引 Google Fonts / jsdelivr CDN → 正式使用须本地化（仓自带 `hyperframes-localize-fonts` 子命令）。
2. **架构范式**：HF 推荐根清单（index.html 只做 scene 编排）+ 子合成文件（`<template>` 包裹、局部时间轴从 0 起、`data-composition-src` 挂载、根 `data-start` 定全局位置）——即 deck-talk"每页 = 一个 scene 文件、根按口播时间戳编排翻页"的生产模型，spike 已按此验证。
3. **telemetry 默认开启**（匿名用量上报）→ deck-render 的 check-setup 应执行 `hyperframes telemetry disable`。
4. npm v11 安全机制屏蔽 onnxruntime-node / protobufjs 的 postinstall——不影响渲染（转写能力不用），无需处理。
5. doctor 可选缺失项 whisper-cpp / Kokoro / MusicGen——转写与配音走 awk-tts 路线，无影响。
6. workers auto=3（按内存权衡，非 8 核全开）；长片可 `--workers` 手动提升。

**遗留可选验证项（不阻塞，后续 Phase 按需）**：registry `add data-chart` 块的拉取路径（GitHub raw 走代理）；chrome-headless-shell 优化 capture 路径（`HYPERFRAMES_BROWSER_PATH`）；`--docker` 确定性模式。

## 4. 技术方案

### 4.1 数据流总览（音频先行，声画同源）

```
Brief（voiceover.md 落稿锁定 / 或甲方录音）
  ↓ Stage 1-2（重定义）
script/deck-script.md —— 每页幻灯：命题/版式/图表数据/素材槽/对应口播段落 + 小窗方案
  ↓ GATE A（照走）
  ↓ Stage 6-7（重定义）
素材齐备：图表数据/图片/avatar 形象照 + narration.mp3（awk-tts 或甲方录音）
  ↓
narration-align → 字级时间戳 → 翻页点（句边界）→ 每页 scene 时长
  ↓ GATE B（照走：slides 设计静帧 contact sheet + 数字人 5s 样片 + 成本预估）
  ↓ Stage 10（重定义，两路并行）
大画面：composition HTML（scene 时序=时间戳）→ deck-render check → render → slides.mp4
小窗口：[数字人路线] avatar-gen create（形象照 + narration.mp3）→ presenter.mp4
        [实拍路线] 甲方素材入库校验 → clip-trim 裁剪对齐 → presenter.mp4
  ↓ Stage 11-12
pip-compose（slides.mp4 + presenter.mp4，音轨=narration.mp3 单一来源）→ burn-srt → assemble（片头尾）
  ↓ Stage 13a/b/c（照走）→ 14a（按需）→ 15 交付
```

### 4.2 音频单一来源设计（关键）

同一条 `narration.mp3`（awk-tts 产出，带字级时间戳；或甲方录音经 ASR）：

1. 驱动 `narration-align` → 时间戳 → 决定翻页点与每页 scene 时长（**声画对齐的结构基础**）
2. 驱动数字人（audio-driven avatar：即梦 OmniHuman / HeyGen 均支持音频输入）→ 小窗口型天然对齐
3. 驱动字幕（burn-srt）
4. 成成片音轨（pip-compose 透传；presenter.mp4 自带音轨弃用，避免二次压缩）

**页翻在句边界**：单页驻留时长 = 对应口播段落时长；设最短/最长驻留守卫（过短合页、过长拆页，写进 deck-script 自检）。

### 4.3 三个新组件

| 组件 | 位置 | 职责与形态 |
|------|------|-----------|
| **`deck-render`** | `crews/content-producer/skills/expert-video/tools/deck-render/`（wrapper + SKILL.md + scripts/*.py + **package.json**） | 子命令：`check-setup`（node/ffmpeg/Chrome/中文字体/env 自检）、`scaffold`（composition HTML 骨架：scene 分页结构 + PiP 预留区 + 字体声明 + themes）、`check`（HF lint/validate 合并闸门——lint→check→preview→render 纪律，重规划 #50）、`render`（--workers/--quality 封装）。Node 依赖按 CLAUDE.md 规范落工具目录自己的 package.json，**hyperframes pin 版本**（防 4515-commits 级活跃度漂移；升级走 IT engineer，不静默）。需核实 apply-addons.sh 对嵌套 tools 目录（SKILL.md + package.json）的扫描 |
| **`pip-compose`** | `video-producer` 新子命令（scripts/pip-compose.py） | 底视频 + 小窗视频 → PiP 合成：corner 四选/尺寸比例/圆角/描边/字幕安全区避让；音轨默认透传底视频；断言（尺寸/时长/帧率）与干湿分离照既有范式。小窗素材重做时只重跑本步，不重渲 slides |
| **`avatar-gen`** | 公共 `skills/avatar-gen/`（wrapper + SKILL.md + scripts/*.py） | 子命令：`create`（提交→轮询→下载——多步骤+中间态**必须脚本化**铁律）、`status`、`providers`。provider 路由 jimeng（首选）→ heygen（备选），候选链 fallback + decisions.log 对齐 aigc-video-gen 范式；串行任务队列（即梦免费态并发 1）。即梦 V4 签名自写实现（思路参考 OpenMontage jimeng_video.py，AGPL 隔离不搬代码）。env：即梦 AK/SK + 可选 `HEYGEN_API_KEY`；缺失 exit 2 交 IT engineer |

## 5. 开发计划

### Phase 0 — Spike 验证（0.5–1 天 + 外部开通等待）【先证后建】

| # | 验证项 | 通过标准 |
|---|--------|---------|
| 0.1 | `npx hyperframes` 本机渲染 30s 含图表（data-chart）+ 中文样片 | 代理环境下依赖拉取成功；Noto CJK 渲染正常；图表动画逐帧确定性；1080p 实测耗时记录（校准 1–2.5min/min 外推） |
| 0.2 | 即梦 OmniHuman：单图 + 5s 音频 → 数字人样片 | AK/SK 开通、V4 签名调通、口型/画质可接受、输出规格（分辨率/帧率/格式）记录 |
| 0.3 | （可选）HeyGen：OAuth 免费额度 + avatar clip 生成 | 代理下可用则备选路线实测通过 |

**降级预案**：0.1 失败 → B-roll 退回 motion-graphics 扩展 slide 模板（Pillow 路线，无新依赖但图表/排版表现力弱）；0.2 失败 → 数字人只保留 HeyGen 或仅支持实拍路线（workflow 文档结构对降级免疫，provider 后补）。

**用户侧前置**：开通火山引擎**智能视觉服务**拿 AK/SK（0.2 硬前置）；HeyGen 账号（0.3 可选）。

### Phase 1 — 工具层建设（2.5–4 天）

1. `deck-render` wrapper（1–2 天）：四子命令 + composition 模板脚手架 + package.json pin + check-setup；验收 = spike 样片经 wrapper 复跑成功
2. `pip-compose` 子命令（0.5 天）：验收 = slides 样片 + 实拍/数字人小窗合成，位置/圆角/安全区参数化，断言齐
3. `avatar-gen` 公共技能（1–2 天）：验收 = 即梦 create 全流程（提交→轮询→下载）实跑出片 + fallback/decisions.log/串行队列 + env 缺失 exit 2

### Phase 2 — Workflow 文档 `workflows/deck-talk.md`（1 天）

按 collage-broll.md 骨架，核心内容：

- **类型定义**：幻灯片驱动的讲解口播视频；子形态（小窗来源 = 实拍 / 数字人 / 无小窗纯幻灯旁白）
- **输入契约（Brief 侧）**：口播稿 `voiceover.md` 落稿锁定（**口播归 main，CP 不重写**——两车道铁律）；小窗来源字段；图表数据与素材清单（绝对路径 + 授权）；规格默认 16:9 1080p
- **阶段裁剪表**（相对通用 Stage 0→15）：

| Stage | 处置 | deck-talk 对应 |
|-------|------|----------------|
| 0 Brief intake | 照走 | 核对口播稿、小窗来源、图表数据、规格 |
| 1 script-write | **重定义** | 幻灯脚本 `script/deck-script.md`：每页命题/版式/图表数据/素材槽/对应口播段落 + 小窗方案 |
| 2 script-self-eval | **重定义** | 幻灯脚本自检：每页单命题、信息密度上限、图表数据有源、小窗遮挡预检、翻页节奏（句边界+最短/最长驻留） |
| 3–5 storyboard / shot-decompose / character-register | **裁剪** | 无机位/无角色三视图；avatar 形象照登记 decisions.json |
| GATE A | 照走 | 呈交逐页幻灯脚本摘要 + 小窗方案 |
| 6–7 slot-plan / asset-resolve | **重定义** | 幻灯素材（图表数据校验/图片）+ 口播音频（awk-tts 或甲方录音 ASR）+ avatar 形象照 |
| 8 slideshow-risk | **裁剪重定义** | 六维打分不适用本类型；改"幻灯动效等级自检"——必须 HF 真动画（元素入场/图表动画/转场），禁静图 Ken Burns |
| 9 delivery-promise-lock | **重定义** | 声明幻灯动画等级；motion 判据按 HTML 动画路径口径 |
| GATE B | 照走 | 呈交 slides 设计静帧 contact sheet（HF preview 截图）+ **数字人 5 秒样片**（先样片后全量纪律）+ 成本预估 |
| 10 render-shot | **重定义** | 音频先行：narration-align 时间戳 → composition scene 时长 → `deck-render` 出 slides.mp4；`avatar-gen`（或实拍裁剪）并行出 presenter.mp4 |
| 11 mix-audio | 照走（前移部分） | narration.mp3 + 时间戳在 Stage 10 前产出；BGM ducking 照声音规范 |
| 12 assemble | **重定义** | `pip-compose` 小窗合成 → burn-srt → assemble（片头尾） |
| 13a/13b/13c | 照走 | motion-audit 抽查翻页与图表动画；normalize 必跑 |
| 14a make-cover | 按需 | |
| 15 交付 | 照走 | 回报绝对路径 |

- **幻灯设计规范**：版式网格、图表选型表（数据形态→registry 块类型）、小窗占位与安全区、每页信息密度上限
- **工作区树**（deck-script / composition 源文件 / slide-render 产物 / avatar 产物 / review）
- **交付**与**不适用**（口播人全屏为主/无幻灯设计需求 → narration-video；实时交互数字人 → 不支持；要可导航 deck 而非视频 → 不支持；纯素材配画面口播 → narration-video）

### Phase 3 — 路由与文档同步（0.5 天）

按 §3.5 触点清单逐项落地（expert-video SKILL.md 类型表+工具表+env 段、CP AGENTS.md 路由行前插、main 三包 content-production.md 枚举、viral-chaser 路由表、requirements.txt、CHANGELOG）。

### Phase 4 — 端到端验证（0.5–1 天）

真实短样片（~60s、4–5 页幻灯含 1 图表 + 数字人小窗）全流程：Brief → GATE A → GATE B → 渲染 → 合成 → `video-review` verdict=pass → normalize；**实测渲染耗时回填本文档**。

### Phase 5 — 后续增强（不进本期）

`remove-background` 无框 presenter 叠加（HF 本地 u2net）；html-video PPT 模板批量移植（license-clean）；HeyGen 云渲染路线；可灵 avatar 大陆端点验证；竖屏 9:16 版式预设。

## 6. 风险与缓解

| 级别 | 风险 | 缓解 |
|------|------|------|
| HIGH | Phase 0 spike 不全绿（代理下依赖拉取/中文渲染/图表确定性/OmniHuman 开通与质量） | spike 先行 + 两条降级预案；workflow 文档结构对降级免疫 |
| HIGH | 即梦 OmniHuman API 较新（2025-09 开放），输出规格/并发/质量本机未实测；成本随片长线性涨 | Phase 0.2 实测；成本预估强制进 GATE B 呈交；免费态并发 1 → avatar-gen 串行队列 |
| MED | HF 极活跃（日均提交），API 漂移 | package.json **pin 版本**；升级走 IT engineer 流程，不静默（HF 自身纪律同款） |
| MED | slideshow-risk / delivery-promise 闸门语义误杀本类型 | 裁剪表显式重定义 Stage 8/9/13b 判据；必要时 slideshow-risk.py 加 workflow 感知参数 |
| MED | 与 narration-video 路由竞争（同属口播类） | 类型表 + AGENTS.md 消歧信号明确，路由行前插 |
| LOW | pip-compose / wrapper 常规工程 | 既有范式（断言、干湿分离、退出码约定） |
| LOW | AGPL 污染（OpenMontage） | 只借思路纪律（5 秒样片、No-Avatar 显式降级、presenter+overlay 范式），代码自写；HF/html-video Apache-2.0 无虞 |

## 7. 成本预估

- **数字人路线**：即梦快速模式 1 元/秒 × 片长（3 分钟视频 ≈ 180 元）；HeyGen ≈ 3–20 credit/分钟 + 月费（~$48/月起，二手来源未验证）。GATE B 必须呈交成本预估。
- **实拍素材路线**：零合成成本。
- **渲染**：HF 本地渲染零 API 费用（电费/机时忽略级）；1min 1080p ≈ 1–2.5min 机时。

## 8. 复杂度与排期

**MEDIUM-HIGH**：Phase 0 spike 0.5–1 天 ｜ Phase 1 工具 2.5–4 天 ｜ Phase 2 文档 1 天 ｜ Phase 3 同步 0.5 天 ｜ Phase 4 验证 0.5–1 天 → **合计约 5–7 个工作日**（不含即梦 AK/SK 开通等待）。

## 9. 落地进度

**当前口径（2026-09-25）**：`deck-render`、`pip-compose`、`deck-compose`、包内 `liveportrait`、三模式 workflow、安装/update/Docker 接入及 awk-tts 声音复刻/音色设计均已落地。百炼数字人和音色样片已有单项实测；60 秒幻灯+测试图小窗的工程样片通过技术审片。仍需用真实口播素材按 Brief→两闸门→成片→人工口型/声音验收跑完整链路，并在 Windows 实机核验字体安装、浏览器与渲染。下列复选框反映原方案在 2026-09-21 的状态，不是新方案的待办清单。

- [x] Phase 0.1 HF 本机 spike（2026-09-20 通过：30s 1080p 机内 36.7s；中文与图表动画字节级确定；check 闸门全绿含 WCAG 37/37；实测记录见 §3.6）
- [ ] Phase 0.2 即梦 OmniHuman spike（**等用户开通智能视觉 AK/SK**）
- [ ] Phase 0.3 HeyGen 免费额度 spike（可选）
- [x] Phase 1.1 deck-render wrapper（check-setup/scaffold/check/preview/render；锁定 HF 0.8.50 + GSAP 3.14.2；60s 中文图表渲染已通过）
- [x] Phase 1.2 pip-compose 子命令（四角/圆角/描边/字幕安全区、唯一音轨、无小窗路径、dry-run 与输出校验；测试媒体合成通过，真人口型待真实素材验收）
- [ ] Phase 1.3 avatar-gen 公共技能
- [x] Phase 2 workflows/deck-talk.md（明确 footage/none 可用、avatar 生成未开放；同源音频与 HTML 动效验收）
- [x] Phase 3 路由与文档同步（本期非数字人范围；额外补 _brief.py 识别、script-write/self-eval 逐页模板、通用 Stage 3–10 裁剪守卫；未增加虚假的 avatar-gen 工具入口）
- [ ] Phase 4 真实口播/数字人端到端验证（本地测试媒体工程链路已通过，见下；未冒充真实口型验收）

### 9.1 2026-09-21 非数字人范围落地

用户确认即梦开通另行安排，先推进不依赖账号的部分。本次只做代码与本地工程验证，未配置数字人凭据、未调用数字人付费 API。

- **工具接入**：安装器现有递归扫描已支持嵌套 `tools/deck-render/SKILL.md + package.json`，wrapper 暴露函数也支持专家包 tools；不需要新增部署层。Pillow 使用仓根现有依赖，未新增 Python 包。HF 遥测通过子进程 env 关闭，不修改全局用户配置；doctor 的版本升级提示不触发自动升级。
- **相对原计划的细化**：增加 `preview` 子命令，用 HF snapshot 落 PNG/contact sheet，不启动常驻预览服务器；scaffold 只写空目录，渲染/合成先写临时文件、规格通过后落盘。pip-compose 提供显式 `--audio` 唯一音轨，省略 presenter 时可只配旁白。
- **旧闸门消歧**：Stage 8/9/13b 使用逐页 HTML 动效计划、承诺与证据审核，不将静态阅读停留硬算成 motion_led 素材占比；Stage 3–10 通用脚本在 deck-talk 下提示改走专属阶段，避免生成错误产物。GATE A/B 的甲方批准仍然保留。
- **原 spike 复跑**：原 30s spike 源文件复制到独立测试目录，经新 wrapper 的 check→render 成功，1920×1080/30fps；WCAG 37/37，保留原 SVG 中间态溢出的 1 条 info。渲染进程 wall 61.487s，输出 `/tmp/deck-talk-wrapper-check/spike.mp4`。本次使用缓存 HeadlessChrome 152 的 screenshot capture、workers=2，与 §3.6 的系统 Chrome / beginframe / workers=3 不同，耗时不能直接作同配置回归比较。

**60s 工程验证**（四页中文、柱状图、运动测试图小窗 + 440Hz 测试音，不是真人口播）：

| 项目 | 结果 |
|---|---|
| HF 检查 | lint 0 error/0 warning；runtime/layout/motion 无问题；WCAG 25/25 |
| 渲染 | 1920×1080 / 30fps / 60s；workers=2、delivery、软件截图；HF 内部 103.9s，渲染进程 wall 106.478s；含前置检查的 wrapper 118.615s |
| 后期 | pip-compose 42.915s；无小窗配旁白 4.910s；字幕 21.435s；normalize 30.220s |
| 归一化与审片 | normalize 测量 output_i=-14.05 LUFS；最终 MP4 容器时长 60.10s；video-review verdict=pass，全片 ffmpeg 解码无错误 |
| 动画 | 每页 0.15s/2.0s 局部时刻抽帧，正文区均有实际像素变化；图表最终态、小窗圆角/描边/留白已目检 |
| 回归 | 8 项测试通过（含真实浏览器中的深色图片页/左侧留白；四角、非法输入、24→30fps、唯一音轨频率验证、workflow 模板与八个阶段守卫等子场景） |

样片与日志：`/tmp/deck-talk-smoke-20260921/`（`video.mp4`、`smoke.json`、`logs/`、`review/`；临时目录可能被清理）。可复跑入口与覆盖边界见 `test/deck-talk/README.md`。

**未完成项**：真实口播的 TTS/ASR→句边界→口型人工验收、即梦 5s 样片、avatar-gen 提交/轮询/下载及 fallback、数字人全链路。当前工程样片不替代这些验收，也不把 Phase 4 整体标为完成。

## 10. 参考资料

- 调研基线版本见 §3.1；关键证据文件：HF `docs/guides/avatar-presenter.mdx`、`docs/guides/performance.mdx`、`docs/concepts/determinism.mdx`、`skills/talking-head-recut/SKILL.md`、`skills/slideshow/SKILL.md`（陷阱）、`registry/blocks/`；html-video `packages/adapter-hyperframes/src/render.ts`（录屏实现）、`research/2026-06-04-spec-07-ppt-to-template.md`（RFC-07）、`CLAUDE.md`（工程教训）；OpenMontage `tools/avatar/*`、`pipeline_defs/{talking-head,avatar-spokesperson}.yaml`、`tools/video/jimeng_video.py`（V4 签名参考）；openclaw-plugin-heygen `README.md`、`video-generation-provider.ts`
- 即梦 OmniHuman 文档：volcengine.com/docs/85621/1544715（1 元/秒、并发 1）、docs/85621/1829013（OmniHuman1.5）
- 仓内关联：`video-capability-replanning-2026-07-25.md` §6.3/§6.4/§7/§8（吸收判定 #31/#34/#48/#49/#50 直接约束本计划）；`crews/content-producer/skills/expert-video/SKILL.md`（通用流程与铁律）；`workflows/collage-broll.md`（文档骨架范本）
