# v5.7.3(2026-10-09)

- `aigc-video-gen music` 增加百炼业务空间 `fun-music-v1`：支持提示词/歌词、纯音乐、演唱性别及 MP3/WAV，同步生成后下载音频并保存 metadata；新增音乐专用选路，自动优先 MiniMax 再完整百炼业务空间，支持显式 `--platform dashscope`，火山/Agent Plan 视频凭据不触发音乐生成。
- deck-render、通用视觉片段、片尾和字幕按系统选择默认中文字体：Windows 使用自带微软雅黑且安装器不再下载 Noto；Linux/macOS 保留 Noto Sans CJK SC。旧 Python 动效兼容入口也可读取 Windows 字体文件。
- `expert-video` 的新视觉片段统一走 `video-producer visual-render`（HyperFrames/GSAP）；片尾改用该渲染器，拼贴 B-roll 改为独立纸片与可控时间轴，并把可选 i2v 批调收进 `video-producer`，删除独立 `collage-broll` 工具。旧 JSON 动效项目暂保留兼容入口。
- 安装/更新与 Docker 构建预装 deck-render 的 FFmpeg、锁定 HyperFrames/Playwright Chromium 和 Noto Sans CJK SC；运行时从包内浏览器路径启动渲染。
- awk-tts 新增声音复刻/音色设计、音色状态查询与绑定档案；默认沿火山 → 百炼业务空间 → Agent Plan 选路，火山支持新版单 key 和旧版双头鉴权。
- 百炼业务空间 TTS 候选链增加 `qwen-audio-3.1-tts-flash`，排序在 3.0 Flash 前，并适配模型专属默认音色和自定义音色档案；公共 ASR 与 TTS 自检按 `qwen-audio-3.1-asr-flash` → `qwen-audio-3.0-asr-flash` 尝试，显式模型关闭模型回退，Agent Plan 保留原模型候选。
- ASR 路由及火山/百炼后端统一放入公共 `skills/_shared`；视频转写、口播剪辑、CP 旁白对齐、TTS 自检及 Awada 语音消息共用一套实现，TTS 自检也按火山 → 百炼业务空间 → Agent Plan 回退，全部失败仅警告。
- 火山视频仅支持 Seedance 2.5 → 2.0 fast，按时长和参考素材数量筛选候选链，补齐参考音频、首尾帧互斥与 2.5 adaptive 比例适配；专用凭据改名为 `VOLC_SEEDANCE_API_KEY`（原 `AWK_GEN_KEY`）。
- `aigc-video-gen` 的百炼业务空间改用 `wan3.0-video` → `wan3.0-video-prime`，统一适配文生、首帧/首尾帧与多模态参考，支持2–30秒/智能时长、480P、参考音频和无声输出；Agent Plan 保留 HappyHorse/Wan2.7 候选链，显式模型也执行参数与素材校验。
- `awk-img-gen` 仅保留百炼业务空间与 Agent Plan，移除火山生图；新增 `--platform dashscope|plan` 固定端点、凭据和候选链，默认优先业务空间再 Agent Plan。Agent Plan 默认调用 `qwen-image-3.0-pro`，不可用时回退 `wan2.7-image-pro` → `wan2.7-image`。

### 平台职责与视频分析

- `expert-douyin` / `expert-xhs` / `expert-tiktok` / `expert-kuaishou` / `expert-twitter` 聚焦创作、发布、本人作品数据与创作者服务；私信及其他互动写操作、竞争对手直播调研与直播间互动统一收进 `expert-bd`，直播 workflow 按调研与互动拆分。内容搜索、账号/作品/评论读取、互动提醒与媒体下载由对应平台的一级 hunter 提供，以各平台已实现接口为准。
- `viral-chaser` 改为编排 hunter 取资料与下载，再用本地 analyzer 提取音频、公共 ASR 转写和全片关键帧；删除 analyzer 内的登录、探活、链接解析与下载链路。支持抖音、小红书、TikTok、快手、X、微博视频，不再支持 B 站链接；图文由 hunter 下载、对应平台专家 workflow 分析。
- 公共 `smart-search` 将抖音、小红书、TikTok、快手、X、微博和微信公众号路由到对应 hunter；微信视频号暂未提供搜索与取内容方案。`published-track` 只管理发布记录、查询与指标入库，各平台 engagement 工具负责取数后回填。

### TikTok、快手、X 与微博能力扩展

- 新增 `expert-tiktok` / `expert-kuaishou`，扩充 `expert-twitter`：提供起号、账号对标、定性风格 DNA、内容生产、改片与复盘 workflow，配套发布、本人作品取数及风格分析工具；取数匹配完整作品 ID 与账号后回填 `published-track`。
- 新增 `tiktok-hunter` / `kuaishou-hunter` / `x-hunter` / `weibo-hunter`，按平台接口提供搜索、账号与作品查询、评论读取、媒体下载，支持 `viral-chaser` 获取本地视频素材；微博沿用独立 `weibo-publish`，升级图文/视频发布及发布记录，不新增专家包。
- `expert-bd` 增加 TikTok 互动、私信与直播工具，接入快手直播读取/监听；X 互动从专家包移入 BD，并新增私信会话读取。快手普通互动写/私信、X Chat 消息发送与加密正文、微博互动写等缺少可复用接口的能力保持不支持。
- 登录与会话管理并入内部 `platform-runtime`，移除独立 `login-manager` 技能。X、TikTok、微博由各自 hunter 发起 Camoufox 登录，导出 cookie 与真实 UA，在隔离状态验证身份后保存 API 会话；快手使用 hunter 二维码/短信登录。TikTok 写入材料需同次浏览器会话取得，缺少 ticket-guard 材料时保持只读。
- X、TikTok、微博 hunter 明确专属登录窗口归属；login 核验窗口与持久 profile 并返回 session、窗口状态及当前 URL，新增 `login-status` 检查窗口。导出失败提示检查专属会话，窗口故障与 Cookie 缺失分别报告，不依据 profile 中历史 Cookie 判断登录有效。
- 发布先本地预览，确认提交后保存收据；结果未知时阻止重复发布，发布成功但入库失败时仅补记录。下载使用作品详情返回的媒体地址，平台 cookie 不发送给媒体 CDN。
- X 发布预览增加正文与帖串逐条权重、普通/长推模式和 Premium 权限提醒；未订阅或权限未确认时，每条保持280权重内，超限先精简。创作、发布及回复指引说明中文通常按2权重计数，登录校验不验证订阅权限，Blue 权限错误不触发重登。
- 发布失败保留脱敏后的上游消息、平台 result、HTTP 状态及请求阶段，写入收据并返回诊断，继续阻止 unknown 结果重发。快手视频当前仅覆盖空简介、私密、立即发布的分支；公开、带标题/正文/话题或定时的视频在上传前拒绝，交用户在原平台完成。
- 微博视频上传超时由默认30秒调整为独立300秒，可配置30–900秒，进程预算同步延长；最终视频提交补上与本次实际 Cookie 匹配的 CSRF 头，缺 Token 时停止。诊断区分上传、转码与最终提交，仅记录超时和头存在状态，保持未知结果禁止重发；修复位于适配层，保留依赖模块不变。
- 快手私密视频与微博短视频已获本机发布成功反馈；修复“缺公开链接/作品 ID 延迟返回”误报。快手区分创作者作品 ID 与上传 fileId，私密作品无 URL 也可入库和匹配本人指标；微博补完整 ID/短码解析，提交成功后以本次媒体 ID 精确查询本人视频。新增 accepted 收据保存平台确认，后续只查结果或补入库，保持 unknown 防重发；不拼造快手公开链接，不修改保留依赖模块。

### 抖音发布、采集与本人取数

- 抖音视频/图文恢复 Camoufox 持久化 session `douyin` 的浏览器发布链，统一入口提供本地预览与确认发布；本人作品取数通过 HTTP 临时读取同一 profile 的 cookie/UA，不另存登录态、不走 login-manager。创作者 `item/list` 优先提供播放量与深指标，公开详情仅补缺失互动计数。
- 视频发布支持显式传入 3:4 竖封面和 4:3 横封面，一键与分步流程都上传并保存双封面；比例不符时等比补浅灰底，保留完整内容，Brief 与交付规则同步要求双封面和文字安全区。
- 上传完成以视频可播放、真实上传/转码状态结束且连续就绪为准，排除常驻提示中的“上传中”文案；标题与简介改为真实键盘输入后读回，兼容 Slate 话题节点、Unicode 空白、短标题与空简介，简介校验完整正文。AIGC 声明确认单选框选中后才保存，缺视频、标题、封面或声明时停止提交。
- 封面预览在当前页面内按每次上传重新观察，避免大图列表超过命令行长度、上次运行残留与旧预览误判；设置封面后视频元素消失时，仅重开同一草稿一次，恢复后复核视频时长、标题、简介、双封面与 AIGC 声明。补传视频后重新填表与设置封面。
- 新增草稿续编、状态检查与短信验证续接，验证码通过私有文件读取、真实键盘输入；等待验证或结果未知时保留页面和提交记录，阻止重复提交及共用浏览器的关闭操作。取链按本次提交前作品 ID、提交时间和完整标题核查，不将最新旧作品误记为成功。
- `douyin-hunter` 媒体下载支持 `douyinpic.com`；用户、作品和评论 ID 按字符串完整传递，账号作品查询使用完整 `sec_uid` 并核对返回作者，禁止使用终端摘要中的缩略 ID。

### 录屏交付与安装可靠性

- `ui-demo` 有头演习的后续命令统一保持 `--headed`，避免 daemon 切换模式导致窗口与页面丢失；录屏按实际时长、关键帧与分辨率检查，经 IM 交付前转为 MP4。无声原始录屏按素材检查，整理成片画布并合成音轨后再走成片闸门。
- `video-edit extract` 新增 `--mode full`，自动读取时长并转换完整 MP4/WebM 等视频；支持保持原始分辨率、无音轨以及 H.264 / yuv420p / faststart 输出。
- 源码/Docker 与四个 tarball 安装器共用 `install-skill-deps.mjs`，扫描公共、crew 与嵌套工具的技能依赖；支持 per-skill 自定义依赖安装器，安装脚本与配置纳入哈希。哈希命中后仍检查依赖存在性及自定义完整性，缺失或损坏时补装，安装失败或结果不完整时不写成功哈希。`ui-demo` 缺依赖时返回明确的修复指引。
- 依赖安装跳过没有生产依赖且未声明自定义安装器的技能，修复 `proactive-send` 在干净 CI/安装环境中因不生成 `node_modules` 被误报失败；自定义安装器继续按自身产物校验，真实依赖缺失仍触发补装。
- OpenClaw 构建优先保留已生成且包含完整 daemon 导出的公开 CLI 入口，避免兼容脚本因内部 chunk 别名变化误报构建失败；入口缺失或不完整时继续执行原兼容生成与校验。
- CI 在 Linux/macOS 构建后校验 daemon/CLI 入口和技能依赖重复安装；发布包冒烟覆盖首装、重跑升级与用户配置/工作区/登录态文件保留，手动构建检出指定 release tag，并缓存 Python 下载。

### 小红书能力升级

- 新增一级技能 `xhs-hunter`：使用独立的 PC 扫码登录态，支持笔记和用户搜索、主页与推荐流查询、笔记正文及评论采集、图片和视频下载、批量采集与表格导出；供小红书运营和 BD 共用，并为 `viral-chaser` 提供视频资料与下载。
- `xhs-publish` 与 `xhs-engagement` 改用持久化的 Creator 本地 HTTP 会话，扫码二维码可保存为图片供用户确认；支持图文和视频发布、发布时声明 AI 合成内容，以及已发作品的互动数据抓取。每日取数只扫描最近三页并直接更新 `published-track`。
- 创作者数据分析写入 `pub_xhs.deep_metrics`；可用时将单篇作品观众画像完整保存到 `pub_xhs.fan_portrait`。取数缺字段或接口无数据时保留已有记录，不写入猜测值。
- 新增 `xhs-live`、`xhs-im`、`xhs-pugongying`、`xhs-qianfan`：直播间读取与监听、私信会话归 `expert-bd`；达人合作查询与邀约、分销商资料查询及蒲公英/千帆合作 workflow 归 `expert-xhs`。涉及发送的操作需确认具体内容。
- PC 与 Creator 共用的 HTTP、会话和 Relay 客户端收敛到 `_shared/xhs_utils`；小红书请求所需计算值由 OFB Relay 提供。`login-manager` 不再管理小红书，移除旧的 `xhs-content-ops`、`xhs-interact` 和小红书浏览器取数链路；`expert-xhs` 的内容调研改走有界的 `xhs-hunter` 请求。

### Content Producer 新增 Deck Talk workflow

- 新增 `deck-talk` 幻灯讲解 workflow：支持实拍口播、LivePortrait 数字人和仅音频+B-roll 三模式；按 Brief 写逐页/逐段脚本并自检，使用同源音频翻页，验收 HTML 动效与成片。CP 与 main 三平台 Brief/爆款拆解路由接入，通用阶段脚本识别并避免误走分镜/幻灯风险闸门。
- 新增 expert-video 内部 `liveportrait` 与 `deck-compose`，支持同源音轨、任务续查及哈希校验。
- 新增 `deck-render` 本地渲染 wrapper，锁定 HyperFrames 0.8.50 / GSAP 3.14.2，支持中文脚手架、检查、静帧联系表、MP4 与规格校验；复用安装器的嵌套工具依赖与 wrapper 扫描。
- 新增 `video-producer pip-compose`，支持四角小窗、圆角描边、字幕安全区、唯一音轨、无小窗旁白、干跑和时长守卫；数字人生成由 expert-video 内部 LivePortrait 工具提供。

### 小红书与抖音新增原生界面卡片

- 新增 `native-ui-card` 内容生产形态：群聊误发式单图、问答式连续讨论流三图。技能将已定稿内容渲染为 3:4 图片和作品文件，检查头像加载与版面溢出；示例和默认身份不限定选题或品牌。
- 小红书、抖音专家包分别接入选题、卡片编排、出图审核、图文发布与记录流程。选题和表达由对应图文 DNA 决定，反差或反常识角度仅在 DNA 适合时采用；业务知识用于核实涉及的事实与边界。

# v5.7.2 (2026-09-20)

### 视频制作流程与交接

- **统一 Stage 0→15 制作流程**：所有视频制作均从 Brief 进入通用阶段链，保留 GATE A 剧本验收、GATE B 素材验收及成片技术自检。移除 `intent-router`；`story-develop` 仅用于 Brief 缺失或不清晰时的需求整理。
- **类型 workflow 指导剧本生产与自检**：`reversal-ad`、`narration-video`、`collage-broll` 分别定义 Brief→script 的写作规则、检查项和制作约定；`script-write` / `script-self-eval` 按 workflow 生成对应模板。未指定类型时走通用分场剧本。
- **明确口播与旁白分工**：口播稿由小贝提供或向用户取得，content-producer 原样落稿、不代写；真人录音走时间戳与画面排布；制作解说的旁白由 content-producer 编写并提交 GATE A。DNA 指导选题与 Brief，不延伸接管分镜制作。
- **拼贴 B-roll 流程对齐**：按隐喻清单生成静帧并交给 `collage-broll render`；被裁剪的分镜、素材规划、逐镜渲染和拼接阶段加入 workflow 守卫，避免误走通用分镜链。
- **改片与交付约定补齐**：修改单明确问题位置、预期效果与保留项；按受影响片段定向重做，保留上一版并记录修改。AIGC 转场补充选帧、景别、风格与帧率衔接要求，素材清单增加规格说明。

### AIGC 供应商与百炼 Agent Plan

- **百炼 Agent Plan 统一接入**：图像生成、TTS、ASR、声画视频生成支持通过 `AWK_API_KEY` 访问 `token-plan.cn-beijing.maas.aliyuncs.com`。默认百炼配置下，一个账号和 Key 即可覆盖文本、图像、语音与视频能力；同时保留业务空间 `WORKSPACE_ID` + `MODELSTUDIO_API_KEY` / `DASHSCOPE_API_KEY` 路线。
- **图像生成收敛到百炼**：业务空间使用 `qwen-image-3.0-pro` → `qwen-image-3.0` → `qwen-image-2.0-pro-2026-06-22` 候选链；Agent Plan 使用 `wan2.7-image-pro` → `wan2.7-image`。支持文生图、参考图编辑与多图融合，封面及制作工具同步接入。
- **TTS 增加百炼后端**：支持 `qwen-audio-3.0-tts-plus`，业务空间可回退 `qwen-audio-3.0-tts-flash`；保留火山豆包语音合成。支持普通音频下载、SSE 流式音频与字级时间戳，统一语速、响度、格式和音色处理，并自动执行 ASR 自检。
- **ASR 统一路由**：按火山 → 百炼业务空间 → 百炼 Agent Plan 尝试已配置后端，失败时回退并汇总错误；百炼使用 `qwen-audio-3.0-asr-flash`，统一输出全文、句段与秒级词时间戳。视频转写、口播剪辑及旁白对齐共用该入口。
- **视频生成支持 Agent Plan**：百炼 t2v / i2v / r2v 使用 `happyhorse-1.1` → `happyhorse-1.0` → `wan2.7` 对应模式候选链，保留火山 Seedance 与 MiniMax H3。仅配置百炼 `AWK_API_KEY` 时可直接生成，无需额外视频 Key；已有显式视频供应商凭据时仍按配置优先级选择。
- **Agent Plan 真实调用验证与修复**：TTS 普通/流式、公共 ASR、文生图、三种视频模式及旁白对齐入口均完成实测；视频下载、音视频轨与完整解码通过。修复百炼流式 sentence-end 缺少句级文本时字幕为空的问题，以及旁白对齐的公共 ASR 导入路径错误、百炼结果被误标为火山来源的问题。i2v 实测按首帧比例输出，成片尺寸需检查实际媒体，不能仅依赖请求的 `ratio`。

### 抖音图文音乐发布与作品跟踪

- **新增抖音图文音乐发布**：`douyin-note-publish` 支持按序上传多图、填写标题与描述话题、读取上传后的实际推荐音乐并选曲；发布前复核配乐，发布后回收 `/note/<id>` 链接。仅在明确选择原声时跳过配乐流程。
- **图文与视频分开路由**：视频入口改为 `douyin-video-publish`，与图文共享登录态和发布任务锁。修复输入框不兼容的选择器调用；发布结果待核实时只补取链接，避免自动重复发布。
- **图文发布后取链修复**：兼容管理页将标题与正文合并展示的 DOM，在唯一候选的图文编辑页核验完整标题后返回链接。候选判定与点击合并为一次浏览器操作，修复两次检查间列表刷新导致直接退出的竞态；每轮搜索后等待 5 秒、轮询候选最多 30 秒，超时后间隔 3 秒重新搜索，最多 4 轮。保留多候选停止与禁止自动重发，已通过列表消失后恢复的浏览器回归，并用两条已发布作品复测取链。
- **创作者侧指标与深度数据**：抖音取数接入创作者 `item/list`，优先采用创作者侧播放量并保留有效零值；兼容图文链接。`deep_metrics` 保存最新 JSON 及采集时间、来源，不累积历史快照。心跳按平台启用状态巡检，抖音聚焦最近 30 条作品，取数失败显式报告。

### 平台兼容性修复

- 视频号短标题统一无标点、以空格分隔；发布前准备 3:4 / 4:3 封面变体，增强封面编辑操作及 DNA 入库核验，视频描述字数改为建议值并以平台输入框为准。
- 小红书软风控增加有界冷却与单次重试，安全限制不再直接判定为登录失效；发布正文中的字面量 `\\n` 归一化为真实换行。
- 视频素材抓取跟进小红书 EF 系列视频分档兼容。

---

# v5.7.1 (2026-09-15)

### 第三方插件 pin 升级（openclaw-weixin 2.4.8 / wecom-openclaw-cli 1.1.1）

> openclaw 基座保持 `2026.7.1-2`（`0790d9f593`）不变。本轮只动第三方插件 pin，**不触碰本机部署实例**。

- **`@tencent-weixin/openclaw-weixin` 2.4.6 → 2.4.8**：上游 2.4.7/2.4.8 的唯一实质改动是一行 import——`createTypingCallbacks` 从已被 OpenClaw 2026.8.1 删除的兼容子路径 `openclaw/plugin-sdk/channel-runtime` 改到 `openclaw/plugin-sdk/channel-message`（上游声明新路径仍兼容最低宿主 2026.5.12）。其余为版本号与 CHANGELOG。
  - **对 7.1-2 宿主已实测兼容**（不是照抄上游声明）：2.4.8 用到的 11 个 `openclaw/plugin-sdk/*` 子路径在 7.1-2 的 `package.json` exports 里全部存在；18 个具名导入逐个对 7.1-2 已 build 的 `dist/` 做运行时校验，12 个 value import 全部命中（含关键的 `channel-message :: createTypingCallbacks`），6 个 type-only import 在 7.1-2 的 `.d.ts` 中也都在。
  - pin 的 `integrity` 用本地 `npm pack` 下来的 tarball 算 sha512 与 npm `dist.integrity` 对账一致（`update.sh` / `install-wecom-channel.sh` 都是按 tarball sha512 校验）。
- **`@wecom/wecom-openclaw-cli` 1.1.0 → 1.1.1**：安装流程更稳健——`openclaw plugins install` 支持透传 `--force`（7.1-2 的 `plugins-cli` 已有该 flag：Overwrite an existing installed plugin）、多 npm 源 failover 时不再顺手删插件目录、`channels.wecom` 配置备份与描述对缺失 `botId` 更宽容、移除废弃的 `getNpmPluginPath` / `hasValidChannelConfig`。
- **`@tencent-weixin/openclaw-weixin-cli` 2.1.4 不变**：仍是 npm latest，integrity 已复核与 registry 一致。
- 同步把 `scripts/install.sh` / `scripts/install-atomgit.sh` / `docker/docker-bootstrap.sh` 中「pin 文件缺失时」的兜底版本 `2.4.6 → 2.4.8`（三处，避免兜底路径装到旧版）。

---

### 安装与升级链路修复（插件幂等 / pnpm 守卫 / 死代码清理）

> 起因：pin bump 后老用户升级不生效、新机 pnpm 版本不符致 `apply-addons` 直接炸。四个 installer + docker bootstrap 行为对齐，避免裸机 / atomgit / Windows / Docker 四条路线分叉。

- **openclaw-weixin 幂等判断改为按版本比对**：原 `plugins list | grep` 已装即 return，pin bump 后已装实例永远停在旧版，必须人工跑 `plugins install --force` 才升得上去。新增 `weixin_installed_version()`（主路径 `plugins list --json` 取 version，回落到 `$OPENCLAW_HOME/npm/projects/*/node_modules/<pkg>/package.json` glob——目录名带 hash 只能 glob）；判定：已装 == pin → 跳过、!= pin → `--force` 升级、插件在但版本读不到 → 也 `--force` 重装（正确性优先）。三处同源实现一起改（`scripts/install.sh` / `scripts/install-atomgit.sh` / `docker/docker-bootstrap.sh`）——docker 侧 `/root/.openclaw` 是持久卷，镜像升级后插件不会跟着 pin 走，同样需要比版本。升级只换 `npm/projects` 下的包，登录态在 `$OPENCLAW_HOME/openclaw-weixin/` 数据目录不受影响。
- **Windows 安装器补齐同一逻辑**：`install.ps1` / `install-atomgit.ps1` 的 `Install-WeixinPlugin` 仍是旧判断（匹配到插件名即 return），Windows 老用户重跑安装器永远停在旧版。新增 `Get-WeixinInstalledVersion`（主路径 `plugins list --json`，沿用 Capture-Streamed 的 EAP Continue 模式规避 PS 5.1 NativeCommandError；回落 npm/projects glob，与 bash 版逐分支对齐）；判定与 bash 版一致，失败提示同步带 `--force`。便携 pwsh 7.6.6 下 AST 抽真实函数 + 假 openclaw 跑 6 场景全过（裸装 / 同版跳过 / 2.4.6→2.4.8 升级 / JSON 损坏走 glob 回落 / 版本读不到重装 / stderr 噪音不污染主路径）。
- **`update.sh` bundled tarball 路径补 `--force`**：`vendor/openclaw-plugins/*.tgz` 每次都装、没有幂等跳过，但不带 `--force` 时在已装实例上会失败，进而触发紧随的 `exit 1` 把整次 update 打断。在线路径（`npx openclaw-weixin-cli install`）未动——该 CLI 遇到固定版本 spec 会自行跳过升级，要修得改调用方式，按决定暂不处理。
- **pnpm 版本守卫**：pnpm 10.x 的 install CLI 不认 `--fetch-retries`（`apply-addons.sh` 依赖同步直接 unknown argument 炸掉），而 `update.sh` 零预检、`install.sh` 的 `install_pnpm()` 只判断存在即跳过，报错完全不指向真因。`update.sh` 步骤 1.5 加大版本预检（读 `openclaw/package.json` 的 packageManager pin；版本探测在 `/` 下做，避开 pnpm ≥11 在带 pin 目录返回假版本）；`install.sh` 定义 `PNPM_VERSION`（此前从未定义，真走到安装分支会执行 `npm install -g pnpm@` 空版本）并加 major 守卫（低于要求版本则升级而非跳过）；仓根 `package.json` 的 packageManager 从 4 月遗留的 `10.30.2` 对齐 `11.2.2`。
- **install.sh / install-atomgit.sh 删旧源码路线死代码**：tarball 路线 `main()` 从不调用系统依赖 bootstrap（install_node / install_git / install_pnpm）与 git clone（clone_wiseflow / checkout_openclaw_at_pin），是 tarball 定案前旧 curl-源码路线的遗留。`install.sh` 删 19 个零调用者函数（含 require_sudo / install_homebrew / node 版本解析链等传递死代码）+ `USE_LOCAL`/`--use-local`；`install-atomgit.sh` 删同款死 helper 与 `--use-local` no-op 分支；两脚本头注释对齐（`update.sh` 原写「拉新 tarball」，实为 git clone 源码升级路线）。README 删 `--use-local` 行（该 flag 由静默 no-op 变为明确 Unknown option）。ps1 未动（本就 pnpm 11 原生）。
- **`setup-crew` 只为对外 crew 生成 ALLOWED_COMMANDS**：internal crew → `security:full`，`apply_exec_tiers` 本就不读该文件（权限模型在 exec-tiers.sh），4b/4b.5 加 crew-type 闸门（以 workspace SOUL.md 为准，与 4c 一致），避免对内 crew 生成死文件并误导成受白名单约束。SOUL.md 缺失时 `resolve_crew_type` 兜底 external 照常生成，保持 fail-closed。已存在的旧文件不删（可能含用户手工添加的私有条目，运行时无副作用）。

### expert-video 工具链补齐（消除主打形态被迫手写脚本的结构性缺口）

> 按 content-producer 提交的 toolchain-proposal 实施（P0×2 / P1 / P2）。功能实测 50/50 通过（守卫失败路径、checkpoint 续渲、spec 错误拒绝、burn-srt/normalize 全链互操作、1080p 生产规格冒烟、渲染帧目检）；code-review 1 HIGH / 2 MEDIUM / 7 LOW 全部修复并附回归测试。

- **`narration-layout`（P0，新增）**：逐句旁白排布 + 防重叠守卫 + 逐句/末句越界断言 + SRT + 可选混音（内部 subprocess 复用 audio-mix）；`force_style` 落 `abs_starts.json` 供 burn-srt 引用；首句 min_gap 哨兵、lead_in 非负校验；产物按 hard 直拼排布（docstring 与 SKILL.md 均声明转场约束）。
- **`motion-graphics`（P0，新增）**：声明式 spec 驱动 PIL 逐帧动画，Stage 10 第二条渲染路径（与 render-shot 并列）；内置四件套模板（dimension_grid / scroll_cards / crew_panel / rec_highlight，收编 v4 已验证组件）+ 8 类基础元素（必填字段 load_spec 统一校验）+ `custom` 插件逃生舱（编码/checkpoint/校验留在子命令）；帧级 checkpoint + `--force`；时长/分辨率/帧率三重断言（`fit=none` 错画幅不再静默）；缺 ffmpeg/字体 exit 2。`_mg_lib` / `_mg_templates` 为非子命令库。
- **`clip-trim`（P1）**：新增 `--normalize WxH@FPS` / `--grade warm` / `--windows` 多窗 / `--zoompan` 定帧缓推 / `--duration` / `--low-load` / `--force`。**切片起点改 input seek**——修 output seek 在倍速链下被静默放大 speed 倍的内容错位（视频音频流统一）；多窗/定帧工作目录带参数指纹，改参自动重切、不静默复用陈旧内容；顺带修 `.mp3` 容器封 aac 的存量 bug（改为按输出扩展名选编码器）。
- **`assemble`（P1）**：新增 `--manifest` 显式有序段清单（绕开 shot-NN 命名约定）/ `--verify-fps` 拼接后帧率断言（checkpoint 命中重跑同样生效）/ `--expect-durations` 逐段时长校验（list/segments/beats 三形态兼容，全量违例收集）；段名含 `/` 时 unify 落盘名打平。
- **`audio-mix`（P2）**：逐轨 `--fadein`/`--fadeout`（afade 在 adelay 前，fadeout 锚定 `min(轨长, duration-delay)`，超限报错）；`--duration` 硬上限语义写明；修 adelay 缺 `:all=1` 立体声只延左声道的存量 bug。
- **文档同步**：wrapper help、video-producer 与 expert-video 两份 SKILL.md（阶段链 + Stage 12 组合套路新增逐句排布与动态图形配方）、reversal-ad / narration-video 护栏条款、`requirements.txt` 的 Pillow 注释补 motion-graphics；顺带清 audio-mix.py / delivery-promise-lock.py 的 U+FFFD 乱码。

### expert-video 定位纠正 + crew 级后期脚本合入

- **crew 级后期脚本合入 expert-video**：`crews/content-producer/scripts/` 的五个后期脚本（normalize / burn-srt / duck / denoise / interp）经排查只被 CP 自己的三份文档引用（main 侧、install / setup-crew / apply-addons、docker、allowlist 全无引用），本该合。移到 `skills/expert-video/tools/video-producer/scripts/`，自动获得 wrapper 子命令形态（`video-producer normalize|burn-srt|duck|denoise|interp`），与注入的 exec 规范（一律绝对路径、禁 `cd` 前缀）对齐——原调用方式是 workspace 根相对路径 `python3 scripts/x.py`，本来就冲突。顺带修掉 crew 级目录的两个结构性问题：`setup-crew` 对 `crews/<id>/` 是 `cp -R` 拷贝（技能是软链改了即生效，crew 级 scripts 改了要重跑部署才生效），以及同一批脚本被三处文档重复描述——现在唯一权威落点是 `video-producer/SKILL.md` 的「后期处理子命令」段，`scripts/README.md` 删除。
- **SKILL.md 重写（296 → 217 行）**：纠正「通用制作流程」的定位——它不是与类型 workflow 并列的第四条路，也不是 Brief 未指定类型时的 fallback，而是**做任何视频制作工作都必须遵循的基准准则**，reversal-ad / narration-video / collage-broll 只是在其上对特定类型的进一步细化。原「Workflow 清单（按视频类型选）」表里把「通用制作流程」当成一行选项，已删除该行，改为「这个包怎么读（三层）」：通用制作流程 = 基准 / 类型 workflow = 细化 / 工具说明 = 子命令参数，冲突时以 workflow 为准但闸门与护栏不让步。「本包」全部改「我」（与 AGENTS.md 第一人称口径一致）；瘦身去重（Stage 12 参数表删掉只留八个场景化组合套路、依赖表 11 行压成两段），硬规则一条没丢。全仓同步该错误提法：三份 DNA 框架的制作指向表、三份 `build_style_profile.py` 的 video-form 提取提示、三平台 content-production、viral-chaser、CP AGENTS.md、`docs/expert-pack-dna-architecture.md` 4.7/4.9。
- **reversal-ad 工作流增强**：`workflows/reversal-ad.md` 依实战补强（+44/−17），SKILL.md 输入表同步。
- **注（需部署动作，本仓未做）**：`~/.openclaw/workspace-content-producer/` 仍是 09-08 的四条悬挂软链（collage-broll / design-full / manim-explainer / video-producer），expert-video 与 expert-design 尚未链入，`~/.openclaw/bin` 下同名 wrapper 也是悬挂；需重跑 `./scripts/setup-crew.sh`（会 prune 悬挂链、重建软链与 wrapper），`workspace-content-producer/scripts/` 里的五个旧拷贝可一并手工清掉。

### DNA（内容风格 DNA）补「业务植入」与「互动引导与 CTA」两维

- 三个平台（抖音 / 小红书 / 视频号）共 5 份框架各补两维：`biz-implant` 业务植入套路（是否植入 / 位置与时机 / 载体 / 方式原型（反转植入 / 痛点→方案 / 场景带入 / 实测对比 / 清单第 N 项 / 身份认同 / 口碑故事 / 教程内嵌 / 硬广直给）/ 衔接句 / 密度与占比 / 品牌词出现方式）、`interaction-cta` 互动引导与 CTA（行动目标与主目标 / 位置与时机 / 句式与原文摘录 / 行动数量 / 诱因设计 / 与转化目标对应 / 平台组件与合规边界）。
- 与 `narration-script` 划界（口播子模块的「合」只记收束方式，CTA 目标与句式归 `interaction-cta`）、与 `video-form` 划界（形态层面的「影视解说 + 反转植入」记形态与制作指向，本维度记植入怎么设计）。聚合规则补硬要求：两维必须给出「位置 + 载体 + 原文摘录」三样证据，只写「自然植入」「引导关注」不算提取完成；无植入写「无植入（纯内容）」。
- 维度数变为 抖音视频 10 / 图文 9、小红书视频 11 / 图文 10、视频号 10，三份 `build_style_profile.py` 的 DIMENSION_GROUPS / 报告提示 / TEMPLATE_STAGES 等同步，template 新增「[业务植入与 CTA部分]」（图文侧取代原「互动与标签」段）。
- **删「统计与分词」死代码**：分词（相邻二字组合）在脚本里算完从未渲染进 report 或 DNA 文档，统计口径合并进「职责边界」一行；脚本移除 `extract_terms` / `STOP_TERMS` 及相关未使用导入，同样从未被读取的 `weighted_coverage` 聚合项一并删掉。
- **xhs 作品类型表纠正**：默认 `--kind` 是 note，但表里把 `dna-0` 挂在 video、`dna-0-note` 挂在 note，与脚本 `KIND_SUFFIX_HINT`、框架文档、style-dna.md、专家包 SKILL.md 全部相反——改为 note（默认）→ `dna-0`、video → `dna-0-video`，默认 kind 排表格首行。
- **视频号 content-production.md 按抖音版重写**：补 Step 0「识别制作路线」（素材组装 / 从零制作 / 脚本制作）与素材模式、脚本模式入口；Step 编号连续（原 Step 6 之后直接跳到 8/9/10）；制作合并为 Step 5（路线 A main 直接做轻加工 / 路线 B、C 出 Brief 委托 CP）；确认节点回到三个（选题 / 短标题与视频描述 / 成片与封面——原「第四个必停节点」编号错且缺成片确认）。视频号特有约束全部保留：短标题 + 视频描述双字段、取数与入库只用视频描述、短标题不写库、无公开下载路径、30-55 人群与真人出镜占比、转发动机、session 正忙与扫码登录、sph 链接。
- 顺带清掉写给开发者的元叙述（「DNA 不是『平台级 DNA』」等），改为正向表述；Brief 新字段同步到三平台 content-production、CP 侧交接契约与 `account-benchmark` / `style-dna` / `review` 的归因表。

### 平台实操路径回写（视频号发布 / 小红书 / X）

- **wechat-channels-publish 实测路径回写**（来源：小贝 2026-09-14 实战提案，eval 片段取自当日发布实录并通过 `node --check`）：snapshot 一律 `-s "wujie-app"`（整页 snapshot 撞 wujie 双 body 报 strict violation）；Step 3 视频上传改直连 `input[type=file]` 选择器（click 触发按钮路线拿不到 ref）；新增「设置封面」步骤（编辑入口 / 上传封面 / `accept*=image` 精确选择器防双 file input 冲突 / 裁剪确认）；描述框改 eval 四步（聚焦 → insertText → insertParagraph → innerText 校验，contenteditable 空串致 aria 无独立 ref）；短标题 fill + eval 读 `.value` 校验（aria 占位文本填后不消失，snapshot 复核不可信）。新增 4 个 pitfall + 错误处理表 3 行；content-production.md 发布清单补「设置封面」项。
- **`publish_xhs.py` 路径解析修复**：`_shared` 上溯按 D8 拆分前布局写死 `parents[3]`，拆分后（`skills/expert-xhs/tools/xhs-publish/scripts/`）只到 `tools/`，`relay_sign` import 落空。改 `parents[4]` 精确解析到 `skills/_shared`。2026-09-14 小红书实际发布验证通过。
- **twitter-post CJK 输入安全闸门**：CJK 正文禁用 `type`（逐字符按键流与 X Draft.js 异步处理竞态，实测中文丢字 + 乱序），改 eval + `execCommand insertText` 整段插入；新增发布前 MATCH 校验闸门与发布后 profile 终验；「Something went wrong」先过闸门判因（MISMATCH 重插 / MATCH 瞬时错误重试），替换原「优先精简正文」的误判。含草稿回填重复、占位符假警报、emoji 渲染为 img 三个坑。expert-bd comment-engagement 复用同套规则。
- **微信视频号 / 公众号登录统一无头截 QR**：同模式无头截二维码发用户扫码，渲染失败才 `--headed` 兜底；`docs/platform-login-and-browser-spec.md` 两处旧说法连带修正。
- **`published-track record` 补 `--help`/`-h`**：对齐 `update-metrics.sh` 既有模式（DB 检查前响应，无库也能查参数），覆盖全部必填/可选参数、upsert 去重键、`wx_channel --title` 语义（完整视频描述非短标题）、publish-date 禁传 `$()` 警示。
- **Brief 硬性规则新增「不写实现路径」**：Brief 只写需求与验收标准，禁写脚本引用 / ffmpeg 参数表 / 工具链内部细节；用户点名参数例外照传并注明。不依赖工具链补齐进度——边界规则本身恒成立，过渡期由既有「CP 回报无法执行 → 确认改 Brief」条款兜底。

### 清理

- 删除软著申报脚本（`generate_code_doc.py` / `generate_form_info.py` / `generate_manual.py` / `swcr-register.sh`）及 expert-ir 的依赖与委派表条目，软著 / 商标 / 专利申报明确移出职责范围（`docs/d21-symlink-skill.md` C 类清单同步清理）。
- awada 媒体发送说明更新（`scripts/lib/agent-skills.sh`）；`README.md` 精简。

---

# v5.7.0 (2026-08-31)

### 专家包（Expert Pack）架构

> 解决 `AGENTS.md` 膨胀到 257 行 / 19,094 字符逼近注入上限、平台流程互相干扰、运营风格无法结构化复用的问题。详见 `docs/expert-pack-dna-architecture.md`。

- **改造后形态**：一个 crew = 薄 `AGENTS.md`（通用准则 + 专家包路由表）+ 多套专家包（工作流 + 技能组合 + 知识库 + DNA）+ DNA 库 + 共享的 `SOUL` / `TOOLS` / `IDENTITY` / `USER` / `MEMORY`。同一个 crew 保持一个 workspace、一套记忆、一个人格；专家包只是「工作面」，不是子 crew。
- **基于 OpenClaw Skill 按需加载**：源码验证 bootstrap 文件每轮全量注入、`bootstrap-extra-files` hook 也是全量注入、祖先链加载不会发现任意子目录——均不适合承载专家包。Skill 机制只注入 `name + description + 路径`，agent 任务匹配时才 read 全文，是原生的按需加载通道。
- **技能收纳规则**：只被一个领域使用的技能整体迁入对应专家包 `tools/`，从路由面消失；跨领域复用的保持顶层。收纳后技能总数不增反降，路由更准。技术依据：workspace 扫描器发现 `SKILL.md` 后停止深入，包内 `tools/*/SKILL.md` 不会被注册为独立技能。
- **薄 `AGENTS.md` 职责边界**：只保留通用准则（品牌红线、素材治理）、专家包路由表（任务特征 → 专家包名）、兜底规则。各平台具体流程全部下沉到对应专家包。
- **专家包内六大 workflow**：`style-dna`（DNA 创建与更新）、`content-production`（内容生产）、`account-setup`（起号与定位）、`account-benchmark`（对标比较）、`editing`（改稿与调整）、`review`（数据复盘）。workflow 每一步必须能落到工具或明确标注为 agent 推理任务，严禁"专家进行 XX"空话。
- **首个改造对象**：`crews/main`（小贝），已完成 `expert-wx-mp` 专家包。

### DNA（内容风格 DNA）

- **三层产物**：单篇文章 → DNA report（单篇定性提取）→ DNA 文档（聚合同一 DNA 目录下全部 report 的生产规则）→ DNA template（写稿时直接执行的结构化要求）。
- **存储结构**：运行时保存在平台运营文件夹下，按平台和 DNA ID 分层——`<platform>/dna/<dna-id>/reports/`、`covers/`、`{dna-id}.dna.md`、`{dna-id}.template.md`。`dna/` 与 `calibration/` 由集中目录下沉进各平台运营文件夹。
- **数据直连 DNA（废除 rubric）**：`pub_*` 表新增 `dna_id` / `account` / `perf_evaluated` 列，作品与 DNA 直接挂钩。评估按量触发（每平台每 DNA 累积 ≥5 条成熟记录），归因走趋势优先（同账号相对值），复盘一律针对 DNA 无单篇复盘。旧 rubric 脚本与 seed 文件已删除。
- **跨平台 style-profiler 统一规范**：每个平台专家包必须有对应 profiler tool，命令模式（`report` / `build` / `update`）、存储模式、三层产物、权重/focus、用户输入转译、统计边界统一；仅维度定义、分组命名、template 第三项起的分段结构允许平台自定义。

### openclaw 上游同步 v2026.7.1 → v2026.7.1-2

> 7.1 release branch 上的两个补丁发行版（7.1-1 / 7.1-2，均 2026-08-04 发布）。37 个 patch（002 / 007 + 35 个 browser-camoufox-pivot per-file）全部 `git apply --3way --check` 干净通过，无需重新生成。变更集中在 codex / memory-core / state-migrations / plugins / infra，与浏览器转向 patch 无重叠。**未 build**，待次日整体 apply-addon。

- **v2026.7.1-1**（`81ac4f3bdd`）：Codex progress replies 不再中途停 turn（#106961/#108487）；Memory Core 启动期修复 derived sidecar 冲突避免 Gateway fatal restart loop（#107220/#108652）；WSL state permissions 容忍 EROFS（#108250/#108258）；legacy migration residue 改非致命（#106101）；managed plugin 更新修复 stale npm lock（#107294/#107866）。
- **v2026.7.1-2**（`0790d9f593`）：npm plugin updates 接受 singleton-array metadata（#108336），tracked 官方插件可正常安装/升级。
- `openclaw.version` → `2026.7.1-2` / `0790d9f593ad30c940ed93b5872a8cf6d6f3cf8c`。`openclaw-weixin.version.json` 无新发行版，不变。

### camoufox-cli fork 跟随上游 0.7.3 + 浏览器二进制升 FF152

> 本轮把 wiseflow fork 的 camoufox-cli 从 `0.6.2-wiseflow.1` 升到 `0.7.3-wiseflow.1`，同步上游 0.7.x 的安装链路修复，浏览器二进制从 FF135 那一代升到 `v152.0.4-beta.28`（Firefox 152 基线，2026-07-19）。FF152 修了 "synthetic mouse input stalling under heavy load"（地址栏换 IP 死机的根因之一）、"humanized mouse trajectory dropped in FF146 migration"、juggler hang 等多个稳定性问题。

- **`patches/camoufox-cli/src/install.ts` 同步上游 0.7.3 三块缺失修复**：
  - `stableTags()` 函数 + `assetsViaWeb()` 重构（上游 #17）——scrape path 过滤 prerelease tag，不再误拉 beta 版浏览器。
  - `browserPresent()` + install 后 `launchPath()` 兜底（上游 #17/#19）——"已安装"不只看 version.json，还要检查二进制在磁盘上；broken install 立即报错。
  - `launchPath` 加入 import，支持上面两处。
- **`patches/camoufox-cli/package.json` 升级**：
  - `version`: `0.6.2-wiseflow.1` → `0.7.3-wiseflow.1`
  - `camoufox-js`: `^0.11.1` → `0.11.2`（pin 死，跟上游 0.7.3 对齐，避免意外升 0.12）
  - `playwright-core`: 保持 `1.52.0`（camoufox juggler 兼容性需要）
  - `wiseflowForkBaseline`: `0.6.2` → `0.7.3`
- **浏览器二进制 `v152.0.4-beta.28`（FF152 基线）**：`camoufox-js@0.11.2` 的 `CamoufoxFetcher` 指向 `daijro/camoufox` 仓库，`fetchLatest()` 跳过 prerelease，拉第一个 stable release。比 fork 之前用的 FF135 那一代新 17 个 Firefox 大版本。
- **`scripts/update.sh` 加入 camoufox-cli fork rebuild（第 6.5 步）**：
  - 老用户跑 `update.sh` 时，在 `apply-addons.sh` 之后、`pnpm build` 之前，自动 `bash patches/camoufox-cli/build.sh`（rebuild dist + npm install -g 覆盖旧版）+ `camoufox-cli install`（用新 fork 拉新浏览器二进制）。
  - 修复之前老用户升级后全局 `camoufox-cli` 还是旧版、浏览器二进制不更新的缺口。
- **未引入多 tab 架构**：上游 0.7.3 的 `browser.ts` 引入 `TabState` + `tabs` Map + ref-counted close（多 agent 共享浏览器指纹），跟 fork 的单 page + fail-first 队列架构冲突。wiseflow 当前"一个 session 一个 agent"场景不需要多 tab，保留 fork 现状。
- **保留的 fork 独有功能**：`shortenSession()`（支持 cron 长 session 名）、`recoverOrphanBrowser()`/`killDaemon()`/`termThenKill()`（孤儿浏览器进程树回收）、`--viewport` 参数（weibo/xianyu 二维码登录用）、fail-first 队列、`upload`/`identity` 三件套。

---

# v5.6.5 (2026-08-15)

### 安装脚本与镜像运行时 bug 修复

- **install.ps1 Windows 软链**：软链创建失败时回退到拷贝，处理 Windows 用户权限问题，避免技能 wrapper 软链落空致命令找不到。
- **install.sh 更新路线**：`daemon.env` 也用 no-BOM 写法（与 `.env` 一致），修 README fence 渲染。
- **install.sh**：`pnpm install` 前置 portable node 到 `PATH`，避免裸机环境 node 版本不足致 pnpm 装包失败。
- **Docker 镜像**：补装 `ffmpeg` + `sqlite3`，修视频/语音技能与 openclaw 数据库依赖缺失。
- **siliconflow-img-gen 凭据分离**：图像生成专用 key 从 `AWK_API_KEY` 改为独立的 `AWK_GEN_KEY`（与 LLM 的 `AWK_API_KEY` 解耦），同步 `.env.template` / `docker/.env.example` / SKILL.md / `gen.py` / 测试；移除 `thinkingDefault: high`。

---

# v5.6.4 (2026-08-11)

### Docker 分发方案构建与启动 bug 修复

> 5.6.3 引入开箱即用 Docker 方案后，构建机跨境拉包与镜像 bootstrap 层连环踩坑，本轮全部修平。

- **构建机跨境拉包**：删 Dockerfile `# syntax=docker/dockerfile:1` pin 与 `USE_MIRROR` 分支逻辑，FROM 回滚原始 `node:24-bookworm`，npm registry 走 npmjs、corepack 改 `npm install -g pnpm`（绕开 ACR 构建机 corepack 跨境抖动），NPM registry 参数化支持不同构建机位置；文档改勾海外机器构建。
- **bootstrap 静默退出**：修 Dockerfile `ARG` 语法错 + `ENV NPM_CONFIG_REGISTRY` 写死致 bootstrap 静默 `exit 1`；补 `log()` 函数定义（首行 `command not found exit 127` 真根因）；诊断输出走 stderr + 独立 `RUN cat` 步骤显示 bootstrap 诊断文件，穿透 buildkit stdout 吞。
- **AWK_API_KEY 无法更新**：entrypoint 每次启动重新覆盖 `apiKey` 致渲染后无法更新，修。
- **构建流程收尾**：master 分支改为纯本地 build 流程；完成 Docker 分发方案收尾。

---

# v5.6.3 (2026-08-07)

### 数据闭环彻底打通，为自我进化奠基

- **`content-calibrator` 打分+预测机制完善**：内容产出 → 发布 → 数据回流 → 下一轮策略调优的闭环不再有断点。calibrator 拿 published-track 回流的实际数据（阅读/点赞/转发/转化）对照预测打分，自动校准后续选题与打法的权重，为小贝自主迭代提供燃料。
- **`published-track` 数据复盘机制完善**：新增微信视频号取数支持，现在主力四平台（微信视频号、微信公众号、小红书、抖音）全系支持内容自动生产、自动发布、自动取数、自动复盘；发布结果数据回流进 calibrator，闭环生效。

### wx-mp-hunter 接口重写

- 原微信公众号素材接口方案因官方接口调整已不可用，本轮按新版接口重写 `crews/main/skills/wx-mp-hunter`（cheerio 解析新响应结构）。

### 5.6.2 bug 修复（本轮实测踩坑）

- **install.ps1 / install-atomgit.ps1**：
  - Bug1 `.env`/`daemon.env` 不换行：新增 `Write-EnvFile` 辅助函数（UTF8 no BOM + 显式 CRLF），`@(...)` 强制数组。
  - Bug2 技能 wrapper 在 Windows 用 `.cmd` shim 替代软链（Windows 软链需管理员/开发者模式，不靠谱）：新增 `Expose-SkillWrappers` 函数。
  - Bug3 `$Force`/`$SkipBind`/`$SkipBrowser`/`$NoPrompt` 改为 `$script:` 前缀（PowerShell 函数内默认看不到顶层 bare 变量，读局部 `$null`，是 `XIAOBEI_FORCE=1` 不生效的根因）。
  - Bug4 `OPENCLAW_HOME` warning 3 行 `ui_warn` 降级为 1 行 `ui_info`（实际安装结构正确，warning 纯噪音吓人）。
- **install.sh / install-atomgit.sh**：
  - Bug4 `unset OPENCLAW_HOME` 误伤内部变量：删除 unset，保留 warning→降级为 info。
  - tarball 下载原子写优化（`.part` → rename）。
  - pip install 无条件加 `--break-system-packages`（PEP 668，不做探测简化小白体验）。
  - Bug5 `OPENCLAW_HOME` 在 `set -u` 下报 unbound：`cd "${OPENCLAW_HOME}"` 裸引用补 `${OPENCLAW_HOME:-}` 兜底。
  - Bug6 atomgit 国内线路默认跳过 gum spinner bootstrap：`GUM_VERSION` 默认置空，`bootstrap_gum_temp` 加空判定短路，避免连 GitHub 超时 75 秒拖慢安装（系统已装 gum 仍会用；想强制走 GitHub 可 `export OPENCLAW_GUM_VERSION=0.17.0`）。
- **install.ps1 / install-atomgit.ps1 Windows 软链**：
  - Bug7 `workspace-<crew>/skills` 落真文件夹而非软链：根因是 Git Bash 的 MSYS2 默认把 `ln -s` 当 `cp -r`。`Run-SetupCrew` 调 bash 前导出 `MSYS=winsymlinks:nativestrict` 让 `ln -s` 走真 NTFS 软链。
  - Bug8 `~/.openclaw/skills` 缺失/真文件夹：根因是 Windows 路线没调 `apply-addons.sh`。新增 `Sync-GlobalSkills` 函数把仓根 `skills/` 软链到 `~/.openclaw/skills`，幂等 + 失败回退 copy。README 安装段补「Windows 建议打开开发者模式」说明。
- 四脚本语法校验通过（`bash -n` + Python PS1 括号平衡校验）。

### 推荐大模型切到阿里云百炼

---

# v5.6.1 (2026-07-31)

### content-producer 视频能力四方向重构

- **公共底座换火山**：`skills/siliconflow-tts` → `skills/awk-tts`（火山方舟豆包语音合成 2.0 / seed-tts-2.0 字符版，NDJSON 流式响应 + X-Api-* 鉴权 + speaker 路由 + 火山 ASR 自检复用 viral-chaser 凭据池）
- **新建 `video-producer`**：端到端主技能，17 个子脚本骨架覆盖 Stage 0–14 全链 + 两道闸门 GATE A/B + 产物文件即 checkpoint 不引状态机；意图路由三档脚本模板中文化为故事讲述型 / 纔画面动效型 / 蒙太奇剪接型（非专业用户一眼能懂）
- **新建 `design-full`**：整合 design-system-picker + init-workspace + AGENTS.md 工作模式 2，含 14 套设计系统库 + 三条子工作流 A/B/C
- **`collage-broll` 清洗**：Gate 3 + Phase 3 生成部分改直接调公共 `aigc-video-gen` wrapper 不裸引用其下 scripts/gen.py；删"由 gbro-collage-broll 适配而来"出处日志段 + 原模对比表 + 配置指南段 + 底部"没吸收的 gbro 原膜能力"段；`run_gate3.py` 同步走 wrapper（`shutil.which` 拿 PATH 化路径）
- **`manim-explainer` 清洗**：Render Conventions + Reusable Starter 两处命令示例改调 `manim-explainer` wrapper，不再裸引用 `scripts/render-manim.sh`
- **`aigc-video-gen` Flag 肄清**：删 6 个 agent 用不到的 Flag（`--ref-audio` / `--negative-prompt` / `--no-prompt-extend` / `--seed` / `--poll-interval` / `--timeout`），对应 payload 注入逻辑 + poll 函数形参一并收口改内部固定常量；SKILL.md Parameters 段补 3 个有用 Flag（`--prev-segment` / `--no-audio` / `--platform`）；两平台 submit payload 默认均带 `watermark=false`
- **CP 定义文档同步**：AGENTS.md 重构为四能力方向路由表（185→27 行），SOUL/IDENTITY/MEMORY/BUILTIN_SKILLS 同步，scripts/README.md 与 normalize.py 清出处词，openclaw_setting_sample.json 旧技能字样清
- **README 借鉴出处段订正**：补 video-producer 借鉴的四个开源项目 HyperFrames / html-video / ViMax / OpenMontage（§5 禁词原则只约束技能内 SKILL.md / 脚本注释，README 是产品门面例外可列）；AutoClip 措辞补 motion-audit 借鉴点

### openclaw 上游同步至 v2026.7.1

- 从 v2026.6.11 升级到 v2026.7.1（merge-base 起 3368 commits；7.1 是 2026-07 最新稳定版，7.2 仍 beta）。openclaw release tag 是同级 release 分支（非线性累积），6.11 不是 7.1 的祖先；6.11 release-branch 独有的 28 commit 多为 CI/release/QA 收尾，关键代码修复 `fix(agents): preserve absent embedded session keys` 已经通过主线合入 7.1（`31a65e0647`），未丢失。
- **6 个 browser-camoufox-pivot per-file patch 按 7.1 上游漂移重新生成**（原 patch `git apply --3way` 冲突，patch 集合不变，仅刷新内容）：
  - `01` docs/tools/browser.md、`05` extensions/browser/src/browser-tool.ts、`09` extensions/browser/src/browser/profile-capabilities.ts、`11` src/agents/agent-tools.ts（mod patch，按 7.1 新结构 re-port）
  - `10` / `17`（del patch，目标测试文件在 7.1 内容漂移，按 7.1 当前内容重新生成删除补丁）
  - 7.1 新增 `local-extension` profile 模式（Chrome 扩展 relay 驱动），`09` re-port **保留该新模式**、仅移除 `local-managed`（camoufox 接管）
  - `05` re-port 顺带修一个 latent 类型错误：`resolvedTarget` 未排除 `"camoufox"`，传给只接受 `"host"` 的 `resolveBrowserBaseUrl` 报 TS2322（原 patch 因 build 走 tsdown/esbuild 不做类型检查而一直未暴露，tsgo 现捕获）。修法 `target === "node" || target === "camoufox" ? undefined : target`，运行时等价（camoufox 必先早返回）
- 保留 patch 002 / 007 + 其余 29 个 pivot per-file patch（均 `git apply --3way` 通过）
- **验证**：全量 37 patch 顺序 apply 0 失败；tsgo 类型检查 `browser-tool.ts` / `profile-capabilities.ts` / `agent-tools.ts` / `camoufox-cli.adapter.ts` 均通过（无关报错均来自 6.11 node_modules 与 7.1 源码错配，非本仓改动）
- **openclaw-weixin 无新发行版**：`@tencent-weixin/openclaw-weixin` 2.4.6 / `openclaw-weixin-cli` 2.1.4 / `@wecom/wecom-openclaw-cli` 1.1.0 均已是 npm 最新，`openclaw-weixin.version.json` 不变
- `overrides.sh` 已与版本无关（浏览器转向后去掉 patchright 注入，仅注入 `OPENCLAW_DISABLE_WEB_SEARCH`），7.1 `package.json` 无 `pnpm.overrides`，兼容

# v5.6.0 (2026-07-12)

### 浏览器栈整体替换（双线栈，spec `docs/browser-stack-replacement-spec-2026-07.md`）

> 2026-07-11 ~ 07-12 落地。调研结论见 `docs/browser-extension-replacement-research.md` §12（架构转向，优先级最高）。

**双线浏览器栈**（替代原"整体替换 extension"路线）：

- **线 1（日常主力）**：新增 `target=camoufox`（默认）→ forked camoufox-cli 走旁路，绕开 routes/、pw-session、chrome-mcp。反指纹 Firefox + JSON-over-unix-socket。
- **线 2（特殊情况 fallback）**：保留 `target=host`（existing-session 真机 Chrome + chrome-mcp relay）+ `target=node`（remote-cdp 远端 Chrome）。routes/ 层不动。
- **删 sandbox 整条路**（容器 + bridge + facade + `agents.defaults.sandbox.browser` 配置）+ **删 host `local-managed` 分支**（不再额外下 Chromium）+ **patchright 整体去掉**（`overrides.sh` 不再注入 patchright-core，playwright-core 保留给 remote-cdp 用）。

**§1 fork camoufox-cli**（commit `24c1bf1`）：

- vendored 进 `patches/camoufox-cli/`（flat layout，基线上游 `Bin-Huang/camoufox-cli@0.6.2`），不另起 repo、不 npm 发布。`build.sh` 全局安装（`npm install -g .` link，bin → `dist/cli.js`），全局版本 `0.6.2-wiseflow.1`。
- **三个新功能**（spec §1.1 必改）：
  - `upload @ref|selector <file> [more files...]` — Playwright `setInputFiles`，variadic，缺文件 fail-fast。发布类技能依赖。
  - daemon **fail-first 队列** — 同 session 并发命令直接 fail 返回 `session <name> 正忙，请等待当前操作完成后再试`，`close` bypass（recovery）。不排队不等待，agent 读到 fail 文本知道发生了什么。
  - `identity [export <f>]` — 导出有效 UA + 指纹摘要（fingerprintHash），与 `cookies export` 对称（对应原则 4 cookie+UA 双导出）。
- code-review 后两处修复：HIGH 测试隔离（`server-queue.test.ts` 的 `queueState.calls` + firstGate 在 `beforeEach` 重置）+ MEDIUM daemon 挂起（`activeConnections` Set + `forceExit` 构造选项，`wait 999999999` + `close` 不再 linger）。
- 测试：`cli.test.ts` 加 upload/identity 解析 + `server-queue.test.ts` 新文件（fail-first + close bypass）。`npm test` 非 e2e 全过（173 passed）。`tests/e2e.test.ts` 1 失败（沙箱无 camoufox 浏览器二进制，557MB，`camoufox-cli install` 下，deferred 到 §11 step 7 真机验证）。

**§2 extension 改造 + patches 重组**：

- **001 monolith 拆成 35 个单文件 patch**（commit `c3fb7f9`）移至 `patches/browser-camoufox-pivot/patches/`，命名 `NN-{mod|del}-<path>.patch`，按文件名 sort 顺序应用。各 patch 改不同文件、彼此独立，上游漂一个文件只挂那一个 patch。干净上游逐个 `git apply --3way` + 全量端到端 dry-run 验证通过。
- **adapter + 测试 ship 在 `patches/browser-camoufox-pivot/files/`**（`camoufox-cli.adapter.ts` 的 `executeCamoufoxCliAction` 翻译 17 action → forked cli daemon 命令，JSON-over-unix-socket 通信，daemon 生命周期 `ensureDaemon` 探活 + `spawn detached unref`，DI 注入便于测试，33 测试过）。
- **default 改成 camoufox + upload 校验前置**（commit `b0fe815`）：`browser-tool.ts` 无 target 无 node 无 existing-session profile 时走 camoufox（description 同步 `Default: camoufox`）；`resolveExistingUploadPaths` 前置到 camoufox 早返回前，闭合 explicit target=camoufox+upload 绕过路径校验的 pre-existing 安全缺口。
- **patch 处置**：002 留 / 003 删 / 005 删 / 006 删（`noDefaults` 是 patchright 1.60+ 专属，patchright 去掉后原版 playwright-core `connectOverCDP` 不支持）/ 007 留并改名 `007-prefer-camoufox-cli.patch`（system-prompt 引导与架构 patch 解耦，便于单独 revert/调序）。
- **`overrides.sh`**：删 patchright-core 注入（pnpm override + doc sed 都删），保留 web_search disable。
- **`docs/tools/browser.md`** 改成双线模型（`target` 枚举段：`camoufox|host|node`，sandbox/local-managed 标已删，camoufox 为默认日常主力）。

**§2.3 setup-crew.sh 改造**（commit `ce28c38`）：

- `scripts/lib/crew-workspaces.sh` 加 `sync_crew_skills` 函数（按 skill 粒度 `rm -rf + cp -R` 覆盖，不删部署实例独有 skill，带 package.json 的 skill 跑 `npm install --production`）。
- `setup-crew.sh` §1 部署循环 fresh + exists 两个分支都调它，exists 分支不再只做 guide 注入。沙箱验证：自定义 skill 保留、同名 skill 被覆盖、npm 依赖装好。crew 专属 skill 更新现可传播到已部署 workspace。

**§7 twitter-interact 恢复脚本模式**（commit `0c2e962`）：

- AiToEarn clone 正好在 catchup commit `74e884f0`（v2.4.0），无 HEAD 差异要追。上游走 Twitter API v2 + OAuth，按「只吸收知识不搬架构」+ spec 要求 camoufox-cli，吸收操作语义（子命令结构 + 频率纪律），执行仍走 camoufox-cli。
- `twitter_interact.py` 改造：单一持久化 session `twitter`（原则 1，去掉 per-task nonce）+ fail-first 队列检测（`SessionBusyError` → exit 3，busy 时不 close 避免 tear down 正在跑的操作）+ 登录错误消息改成有头（原则 3）。
- 测试：`TestSessionNaming` 改断言常量 `twitter`，加 `TestFailFirstQueue` 验证 busy → exit 3 + 不 close。28/28 通过。

**§8 profile 丢失处理**：

- 新增 `docs/profile-loss-handling.md` canonical 程序：profile 丢失 / 损坏 / 指纹错配 → 重建 + 重登录，**绝对不允许导入 cookie 造会话**（补充 D，强化原则 5）。
- 理由：xhs `a1`/`websectiga` 等设备指纹 cookie 导入到不同指纹会错配 → 被风控检测。2026-06-29 教训：凌晨心跳里 xhs-browse 无登录态，Agent 用 CDP `Network.setCookies` 注入 22 个 cookie 强造会话后批量抓取，当日触发小红书风控、账号被处罚。
- camoufox-cli `cookies import` 合法用途仅限同指纹 profile 的 cookie 备份/恢复 + 跨设备迁移同一指纹（profile 整体搬，不是只搬 cookie）。
- HEARTBEAT.md 约束 4 已落地「凌晨心跳跳过 + 等白天」策略，本文档补白天恢复流程。

**§9 README.md / CHANGELOG.md 更新**：本条目 + README `**v5.6.0 更新**` 浏览器架构重新设计段 + `## 🔧 比原版更强、更适合国内网络环境的浏览器方案` patch 表更新 + `## 🤝 xiaobei 基于如下优秀的开源项目` 去掉 Patchright 加 camoufox（🦊 https://github.com/daijro/camoufox）。

**§3-§6 并行中**（另一 agent）：browser-guide/smart-search/web-form-fill 三技能适配 + login-manager 纯指导化 + 9+ 平台 skill 改造 + wx-mp-hunter 收编。

**核心原则**（用户拍板的 8 点 + 补充，详见 spec §0）：每平台一个且只一个持久化 session（原则 1）/ 需验证码必须 camoufox-cli 有头（原则 2）/ douyin·twitter·xhs·weibo·zhihu·xianyu·reddit·youtube 有头登录 + wechat-channel·wx-mp 无头截图 QR（原则 3）/ cookie+UA 双导出（原则 4）/ 严禁浏览器方案导入 cookie（原则 5）/ profile 丢失重建+重登录绝不导入（补充 D）/ 涉及登录持久化 + 不登录临时性 session（补充 A）。

### 产品拆分（client 仓）

- **client 仓独立成仓**：从 Pro 仓 `product-split/client` 分支切出独立仓 `wiseflow`（远程 `git@github.com:bigbrother666sh/wiseflow.git`），发布仓 `TeamWiseFlow/xiaobei.git`。
- **relay 仓独立**：auth / sign / publish-relay / video-relay / tx-relay / awada-server 等服务搬到独立 PM2 仓 `wiseflow-relay`（`git-server:repos/wiseflow-relay.git`）。client 不持任何平台凭据，所有 relay 调用带 `X-OFB-Key` header。
- **openclaw 版本锁定**：本仓 `openclaw.version` 锁 `v2026.6.10 / aa69b12d`，CI/release 按此 clone + checkout。
- **patches 精简**：001（relax exec allowlist）+ 004（chrome port grace retry）已删，上游 6.10 已吸收或风险降级；保留 002/003/005/006。

### D8 扁平化 + D15 删减 + addons 销毁 + awada 拍平

- **D8**：原 `addons/officials/crew/{main,content-producer,it-engineer,sales-cs}` 拍平到 `crews/<crew-id>/`；公共技能统一在 `skills/`。
- **D15**：删除所有不用的 addons 模板与脚本。
- **awada 拍平**：原 `awada/awada-extension/` 改为 `awada/`（D8 一并）。
- **D19 权限放开**（2026-07-03）：内 crew（main / content-producer / it-engineer）SOUL.md `command-tier: T3` + 清空 `ALLOWED_COMMANDS`；sales-cs 维持 `T0`。Docker 内对内全放开（消除 allowlist miss 摩擦），对外保留 prompt injection 防线。
- **权限模型简化**（2026-07-07）：删 `command-tier`（T0~T3 四档抽象）字段，T1/T2 死代码清除。权限改由 `crew-type` + `ALLOWED_COMMANDS` 两源决定：`internal` → `full`；`external` → `deny`，有 `+` 条目则升级 `allowlist`。SOUL.md ×5 删 `command-tier` 行；`exec-tiers.sh` 重写；`inject_exec_guide` 改读 `crew-type`；内 crew 空 `ALLOWED_COMMANDS` 删除。

### Phase 4.5 — camoufox-cli 集成

- **login-manager 重写**：从 CDP WebSocket 抽 cookie 路径 → camoufox-cli cookies export。保留中央存储 `~/.openclaw/logins/{platform}.json`；新增 5 个子命令（`qr-headless` / `qr-confirm` / `cookie-export` / `cookie-import` / `session-cleanup`），加 `wx-mp` 平台（Phase 4.6）。25 单元测试全过。
- **browser-guide 改写**：加 §0 camoufox-cli 主推章节（5 小节），§1-6 标 fallback。
- **浏览器类 skill 收敛**：viral-chaser / content-calibrator / xhs-content-ops / xhs-interact 4 个 skill SKILL.md 改用 camoufox-cli 主推路径（修过期引用 + xhs-interact 全文重写 161+ 行）。
- **指纹模板 bake**：Dockerfile `wiseflow-layer` 阶段加 camoufox-cli 指纹模板 bake，产物 `/root/.openclaw/logins/_template/camoufox-cli.json`。
- **D18 约束**：不 fork camoufox-cli / 不 bake chromium / 每 agent 一 session。
- **设计骨架**：`docs/phase-4.5-design.md`（4 子任务地图 + 接口契约 + D18 约束清单）。
- **spike 报告**：`docs/camoufox-spike-2026-07.md`（指纹复用 + cookies export 验证通过）。

### Phase 4.6 — 微信公众号 engagement 接入（方案 A 骨架）

- **wx-mp-engagement skill 新建**：`crews/main/skills/wx-mp-engagement/`（SKILL.md + fetch_engagement.py + 15 单元测试）。camoufox 跑创作者中心抓阅读数/点赞数/评论数/分享数/收藏数 → 写 `pub_wx_mp`。
- **published-track 集成**：`fetch-and-update-metrics.sh` 加 `wx_mp` 平台路由（直接 exec `wx-mp-engagement.sh fetch --row-id $ROW_ID`），`MANUAL_PLATFORMS` 移除 `wx_mp`。
- **登录复用**：走 login-manager `wx-mp` 平台（中央 cookie）+ camoufox 扫码流程。
- **限制**：仅支持用户**自己有后台权限的号**（创作者中心用公众号账号登录），竞品号拿不到。
- **spike 验证待真机**：10 项 checklist 见 `docs/wechat-mp-engagement-design.md` §七，等统一部署后由用户跑。
- **失败回退**：方案 A → B（容器内 mitmproxy + camoufox）→ C（维持 manual update）。

### Phase 5 — img-gen 改火山方舟 Seedream 4.0（D13 决策）

- **siliconflow-img-gen 改调火山方舟**：`/api/v3/images/generations`（非 `/coding/v3`）。默认 model `doubao-seedream-4-0-250828`，可选 5.0 lite / 3.0 t2i。
- **API key 改 AWK_API_KEY**（D13 决策：img-gen Key 用户自带，纯客户端不入 server）。Skill 内全部 SiliconFlow / Qwen 引用清除。
- **size 校验**：按火山文档（方式 1: 2K/3K/4K；方式 2: WxH，总像素 [2560×1440, 4096×4096]，宽高比 [1/16, 16]）。
- **28 单元测试全过**：常量 / size 校验 / payload 构造 / API 请求 / env 校验 / CLI smoke。
- **SKILL.md 全文重写**：火山方舟专属文档，保留与 SiliconFlow 路径对比表。

### Phase 8.1 / 8.2 — IT engineer 记忆注入

- **产品拆分后运维知识集中注入**：`crews/it-engineer/MEMORY.md` 顶部加 116 行新章节（D19 / D20 / login-manager / awada / camoufox 排故 / 4.6 engagement / 部署路径 / 升级策略）。
- **D20③ 依赖安装规范**（pip `--target vendor` / npm 局部 / 冲突处理 / it-engineer 介入准则）。
- **未动**：SOUL / IDENTITY / AGENTS（属 Phase 7 续暂缓部分，待下一阶段）。

### 默认配置精简（开箱即用）

- **记忆默认 fts-only**：`config-templates/openclaw.json` 与 `openclaw-aihubmix.json` 均加 `agents.defaults.memorySearch.provider = "none"`，新用户**无需开向量/embedding 模型**即可用记忆（走 FTS 全文检索）。
- **dream 默认关闭**：`plugins.entries.memory-core.config.dreaming.enabled` 改 `false`，避免 3am 烧 token 和噪声日志；进阶用户可自行开启（README 有指引）。
- **主力模型统一走 AWK**：`install.sh` 不再收集 `SILICONFLOW_API_KEY`，`_USER_PROMPT_KEYS="AWK_API_KEY"`；视觉/替补也走火山方舟 Coding Plan，一个 key 即可。

### 脚本注入精简

- **Python 调用规范挪进 `inject_exec_guide` 的 external-allowlist 分支**：原独立 `inject_python_exec_guide()` 删除，`setup-crew.sh` 4 处调用移除。内 crew 无 allowlist，该规范对内不成立，不再注入。
- **`inject_env_file_guide()` 删除**：与 main / it-engineer AGENTS.md 已建立的"main 不直接写 env，spawn IT engineer；IT engineer 按 OFB_ENV.md 规范写入"约定重复，`setup-crew.sh` 中调用与 `_OFB_ENV_FILE` 计算块一并移除。

---

# v5.5.2

### Selfmedia Operator 视频制作与分发能力

- **一站式短视频制作**：`video-product` 技能支持文章链接、追爆报告、文字主题、本地文件等多种输入，自动生成脚本 → 逐段生成视频素材（声画同出）→ FFmpeg 合成成片。直连火山引擎 Seedance（doubao-seedance-2.0 系列）与阿里云百炼 Wan2.7-HappyHorse（happyhorse-1.1 系列）端点，按平台自动 fallback
- **视频分发**：新增微信视频号发布（`wechat-channels-publish`，处理 wujie shadow DOM），结合既有的小红书、抖音、Twitter/X、B站、快手等平台，实现短视频制作 → 多平台分发的闭环
- **两个剪辑辅助技能**：
  - `de-mouth`：口播视频去口误，自动识别并删除静音、语气词、卡顿词、重复句、残句，输出干净视频 + 字幕 + 剪映草稿
  - `highlight-clipper`：从本地视频中通过 ASR 转录 + 文本分析自动提取高光片段，剪辑输出多段短视频
- Selfmedia Operator引入科学的评估方案和自动复盘方案（发布前预测打分 -> 每日数据复盘 -> 根据复盘调整打分量表 -> 不断优化预测准确性)。以上已内置到所有平台的发布流程中，让运营工作不再“凭感觉”。

### 主力模型切换为 GLM-5.2，推荐火山方舟 Coding Plan

- `config-templates/openclaw.json` 主力模型由 DeepSeek V4 Pro 切换为 **GLM-5.2**（经火山引擎方舟 Coding Plan 接入，`awk/glm-latest`），fallback 为 siliconflow provider
- `install.sh` 交互式收集的 key 由 `DEEPSEEK_API_KEY` 改为 `AWK_API_KEY`
- 大模型推荐主推**火山方舟 Coding Plan**：支持 GLM-5.2、Kimi-K2.7、MiniMax-M3、DeepSeek-V4 系列、Doubao-Seed-2.0 系列等模型，工具不限；通过 xiaobei 邀请链接订阅叠加 9.5 折，首月尝鲜低至 9.4 元。邀请链接 https://volcengine.com/L/dx-wt80li-I/ ，邀请码 `5Y5A6L86`
- siliconflow、aihubmix 推荐不变（siliconflow 仍需申请，作为视觉/替补模型）

> 想使用 5.5.2 的视频生成能力，需额外开通火山方舟 doubao-seedance-2.0 系列或阿里云百炼 happyhorse-1.1 系列模型，并将对应 key（`AWK_GEN_KEY` 或 `MODELSTUDIO_API_KEY`）配置到 `daemon.env`。

### openclaw 上游同步至 v2026.6.10

- 从 v2026.6.6 升级到 v2026.6.10
- **删除 patch 001**（relax exec allowlist shell syntax）：上游 exec 审批重构为 risk-based（`command-explainer` + `exec-authorization-plan`），`&&`/`||`/`;` 复合命令已原生逐段匹配 allowlist；`$()`/反引号/重定向上游仍拒但 wiseflow 已改走 `.sh` 脚本。原目标代码 `splitShellPipeline` 已删，无法 re-port
- **删除 patch 004**（chrome port grace retry）：上游新增 `ensureManagedChromePortAvailable` + `recoverOwnedStaleManagedChromeCdpListener`，命中 EADDRINUSE 时主动杀掉占用端口的陈旧 Chrome 进程并清 singleton lock 再重探，比 3×500ms 轮询更强
- 保留 patch 002/003/005/006（验证 apply 通过，上游无等价改动）

### 上游关键变更摘要（与 xiaobei 相关）

- **GLM-5.2（6.10）**：暴露 reasoning levels、GLM overload failover、Zai 合成模型回退 manifest baseUrl
- **心跳（6.9）**：修复 5.20 及所有 5.x 上心跳 scheduler 不触发的回归（#88970）
- **sessions_yield over MCP（6.9，#90861）**：修复 MCP 下 sessions_yield 保留
- **安全（6.9）**：secrets redaction、阻断内部 HTTP session overrides、审计 open-DM tool exposure、plugin write owner check
- **存储（6.9）**：NFS 上禁用 SQLite WAL、reindex temp 清理、setup state 移出 workspace dot-dir
- **web search（6.9）**：Codex Hosted Search、key-free provider 保持 opt-in
- **6.10**：fast talks auto mode、channel switch reset 陈旧 origin 字段、hook registry 组合保留 trusted policies

# v5.5.1

### openclaw 上游同步至 v2026.6.6

- 从 v2026.5.28 升级到 v2026.6.6（4253 commits，跨越 6.1→6.2→6.5→6.6 四个稳定版）
- 重新生成 patch 004（chrome-port-grace-retry）和 patch 005（browser-timeout-env-var）以适配上游文件重构
- patch 001–003 验证通过，无需修改

### 上游关键变更摘要

- **安全加固**：exec 审批超时默认拒绝（fail-closed）、sandbox binds 收紧、MCP stdio 继承收紧、Codex HTTP 私有目标阻断、loopback tools 权限隔离
- **OpenRouter 一等公民**：模型设置流程原生支持 OpenRouter OAuth/API-key
- **Parallel Search (Free)**：零配置内置 web search（无需 API key），作为 DuckDuckGo 之前的默认 fallback
- **移动端**：iPad 侧边栏 + iPhone Control Hub，Workboard/Skill Workshop 连接 Gateway
- **Telegram/iMessage**：account-scoped topic 路由、always-on inbound restart、durable echo markers
- **Browser/MCP**：existing-session CDP 支持、WebSocket validation、Streamable HTTP loopback、OAuth/SSE auth 修正
- **Provider**：Claude Fable 5 adaptive thinking、Gemma 4 reasoning replay、本地模型跳过 guardian review、gpt-5.3-codex 恢复
- **Cron**：wake 保留 originating session/agent、impossible cron 表达式拒绝创建
- **启动提速**：cached model metadata、移除 startup catalog wait、lazy slash-command loading
- **QoL**：`openclaw update repair` 恢复路径、compaction timeout 默认降至 180s

# v5.5.0

### 完全重新设计的部署与渠道绑定流程

- 初次安装时默认安装官方微信插件，用户使用个人微信扫码后即可启动第一个crew——main agent，直接在微信上就能使用
- 后续的设定、更多crew的启用、渠道绑定等均可通过main agent完成（直接在微信上与它对话）
- 如果仅需要一个“个人助理”，或者不需要更大的AI crew团队（crew数量小于3），可以一直使用微信渠道，无需额外的操作
- 工作渠道除支持飞书外，额外增加企业微信
- 新增 WeCom channel 插件自动安装脚本（`install-wecom-channel.sh`），支持 pin 版本 + SHA-512 完整性校验，Main Agent 直接执行无需用户手动运行 `npx`
- main agent可以完整操作feishu、企业微信的配置（应用创建、凭据获取、权限配置、事件订阅、crew绑定全流程）

### Designer + IT Engineer 全链路升级

**Designer 与 IT Engineer 的技能组合现已覆盖网页（官网 / 产品 Landing Page）的完整开发与生命周期管理：**

> **设计** → **开发**（IT Engineer 通过 coding-agent）→ **部署**（云计算资源）→ **备案**（ICP）→ **SEO**

#### Designer 升级

- Designer 从"配图+海报生成"重新定位为**系统性视觉设计体系构建者**，负责从零构建完整网页、APP 界面、品牌视觉体系
- 新增 `design-system-picker` 技能：内置 15 套知名品牌设计系统（Stripe / Vercel / Linear / Notion / Apple / Supabase / Shopify / Figma / Spotify / Tesla / Framer / Airbnb / BMW / IBM / Starbucks），覆盖 fintech / devtools / productivity / consumer / luxury / enterprise / ecommerce / creative / media / automotive / lifestyle 全品类
- 设计系统包含完整的 8 段规范（色彩、字体、组件、布局、层级、响应式等），所有 HTML/CSS 产出严格遵循选定设计系统的 token
- 支持从 [awesome-design-md](https://github.com/VoltAgent/awesome-design-md) 上游仓库查找并导入更多设计系统
- Designer 改为纯 binding 模式运行，用户直接使用，其他 crew 不再 spawn Designer
- 简单出图需求（视频封面、海报等）统一使用 `siliconflow-img-gen`，无需启动 Designer
- 新增三大工作流：完整网页/落地页设计（A）、APP/产品界面设计（B）、品牌视觉体系构建（C）

#### IT Engineer 升级

- 新增 `seo` 技能：技术 SEO 审计与优化（爬取、索引、结构化数据、Core Web Vitals、关键词映射）
- 新增 `icp-filing` 技能：ICP 备案全流程指导（材料清单、流程步骤、域名查询、备案号生成）
- 新增 `icp-exemption` 技能：Apple 国区 ICP 豁免申请附件 PDF 生成
- 新增 `tccli` 技能：腾讯云 CLI 速查手册（CVM / Lighthouse / DNSPod / SSL / VPC 等 200+ 服务）
- 新增 `alicloud-find-skills` 技能：阿里云 Agent Skills 搜索、发现与安装

### Selfmedia Operator 增强

- 新增 `wx-mp-publish` 技能：**支持将微信公众号文章自动排版并直接推送至草稿箱**，实现从内容生产到公众号发布的一站式闭环
- 新增 `t2video`（简单视频制作）技能：一站式短视频生产，整合 TTS 语音合成 + 素材搜集 + FFmpeg 组装
- 新增 `highlight-clipper`（高光时刻视频制作）技能：支持从给定视频文件（录屏）中按语音自动剪辑高光时刻短视频
- 大幅完善多平台发布技能，新增/增强支持：小红书（API 方式）、抖音、B站、快手、YouTube、TikTok、Instagram、Facebook、Threads、Pinterest 等

### Officials Addon 新crew 

- **business-developer**（商务拓展）正式发布：4.x版本的功能现在可以完全通过business-developer实现
- **investor-relationship**（投资人关系）预发布

### crew 机制改进

- 启用 BOOTSTRAP.md 机制，每个crew根据自己职责设定，在启动初期会主动向用户搜集必要信息，如Selfmedia Operator搜集账号矩阵信息、IR和BD主动搜集公司、产品信息
- skill 路径解析修复与加载机制优化

#### OpenClaw 升级至 v2026.5.28

- 基于 OpenClaw v2026.5.28（从 v2026.5.7 升级，跨越 6424 commits）
- Patches 004/005 针对 v2026.5.28 新文件结构重新生成，全部 5 个 patch 验证通过
- awada extension 适配升级

### Bug 修复与改进

- `scripts` 脚本中诸多不当处修复与改进
- `crew-recruit` / `crew-dismiss` SKILL.md 澄清 TEAM_DIRECTORY.md 由脚本内部自动同步，无需 agent 手动更新
- HRBP `add-agent.sh` 新增 business-context symlink 和 crew MEMORY.md 背景说明自动注入

---

# v5.4.9

### 升级 openclaw 至 v2026.5.7

- v2026.5.7 被标记为 stable，是近期最稳版本；所有 4 个 patch 均干净应用，无冲突

### install.sh 大幅优化 & DeepSeek + SiliconFlow 最佳实践落地

- 大幅简化新用户 onboard 流程，交互式引导输入 API Key，同时完整支持 macOS 安装部署
- 经过对多个 provider、多个主流 LLM 的实战测试，总结最佳实践为 DeepSeek（主力）+ SiliconFlow（替补 & 视觉模型）组合，已内置到 config-template 和 install 脚本中
- agents.defaults.subagents.announceTimeoutMs 提高至 3600000（1 小时），避免长时间 subagent 任务意外超时

### Bug 修复

- 修复了 v5.4.8 中存在的诸多 bug（涉及 scripts、skills、crew 配置等模块）

### Officials Addon 预发布

- 预发布 **business-developer**（商务拓展）和 **investor-relations**（投资人关系）两个新 crew 模板

---

# v5.4.5～5.4.8

### 升级 openclaw 至 v2026.5.6

- 同步上游 hotfix（OpenAI Codex OAuth 路由修复回滚、plugin/runtime fetch header、debug proxy header replay、web_fetch timeout 后 tool lane 卡住等修复）
- 当前升级原因：v2026.4.24 已知运行问题较多，直接追到 2026.5.6 稳定修复版本
- 诸多 bug 修复（scripts）
- 技能优化

### 升级 openclaw 至 v2026.4.24

**Browser Extensions 重要变更（v2026.4.22 → v2026.4.24）：**

- **新增坐标点击动作**：`act kind="coordinateClick"` 支持通过 x/y 坐标点击，补充 aria ref 定位之外的场景
- **默认 act 超时预算**：修复了 act 操作的默认超时时间设定，避免长时间 act 任务意外被截断（与 patch 005 env var 支持互补）
- **per-profile headless 配置**：每个浏览器 profile 可独立配置 headless/有头模式，不再全局统一
- **稳定 tab 句柄 + 自动化技能**：新增 tab handle 机制，跨多步操作可稳定引用同一标签页；新增 `automation skill` 供 agent 调用
- **Doctor 诊断工具**：新增 `browser doctor` 命令，agent 可直接调用浏览器诊断，并向用户展示结构化诊断信息
- **已有 session 附加修复**：修复 existing-session 附加时的端口冲突、超时判定、WS 状态探测等多个问题（#57245）
- **Chrome profile 锁恢复**：自动检测并恢复 Chromium profile 锁文件异常，减少需手动清理的情况（#62935）
- **空闲 tab 自动关闭**：`/new`、`/reset` 或会话归档时自动关闭已跟踪的浏览器标签，防止跨 session 泄漏
- **Linux 可执行文件路径扩展**：新增 `/opt/google`、`/opt/brave.com`、`/usr/lib/chromium*` 等检测路径（#48563）
- **Browser Realtime Talk**：Talk/Voice Call/Google Meet 可通过 realtime voice loop 调用完整 agent 能力

**Google Meet 首次作为内置 plugin 发布**（bundled participant plugin，含个人 Google 认证、Chrome/Twilio 实时会话、会议记录/出席名单导出、已开启 Meet 标签的恢复工具）

**其他变更：**
- DeepSeek V4 Flash/Pro 加入内置 catalog，V4 Flash 成为新用户默认模型
- 多项安全修复（跨 bot token replay、sandbox browser SSRF、secrets BOM 清理等）
- Plugin 启动性能优化：静态 model catalog、按需加载 provider 依赖

**patch 状态：**
- patch 002、005 无需调整，直接通过
- patch 003（act-field-validation）因 `executeActAction` 函数签名新增 `onTabActivity` 参数导致上下文行号偏移，已重新生成



### 升级 openclaw 至 v2026.4.22

- 同步上游变更（2298 commits，含 telegram/discord 优化、thinking 模型默认级别修复、session 路由保持、wecom/azure openai 等改进）
- patch 001（suppress-stale-reply context）针对新版上下文行偏��重新生成，`--check` 直接通过

# v5.5

### 架构调整

- **patches 与 addon 分离**：将代码补丁（`patches/*.patch`）、插件（`patches/suppress-stale-reply`）和依赖覆盖（`patches/overrides.sh`）从 `addons/officials/` 迁移至项目根目录 `patches/`，作为 xiaobei 的共性基础能力，对所有 addon 生效。addon 不再支持 patches 层，仅提供额外全局技能和 Crew 模板。

- **默认全局技能重新划分**：`smart-search`、`browser-guide` 从 addon 专属技能迁移至 `skills/`（项目根目录），成为 xiaobei 所有 crew 默认可用的内置技能，无需依赖 official addon 即可生效。

- **`apply-addons.sh` 重构**：先应用 `patches/` 下的基础补丁和覆盖，再安装默认全局技能（`skills/`），最后逐 addon 安装额外技能和 Crew 模板。addon 加载流程简化为两层（skills → crew），移除原有的 overrides 和 patches 层。

### 升级 openclaw 至 v2026.4.15

- 同步上游变更（详见 openclaw release notes）
- patch 001（suppress-stale-reply context）针对 `deliver.ts` 重构（OutboundPayloadPlan 架构调整）重新生成
- patch 005（codex apiKey）已被上游原生集成，移除

# v5.4

### 新增

- **suppress-stale-reply 插件 + patch 001**：用户连续快速发送多条消息时，agent 对被超越消息的回复不再发送给用户，但仍写入对话历史供下一轮上下文使用，最终用户只看到对最新消息的回复。所有走标准 inbound/outbound 路径的 channel（feishu / awada / wecom / cli 等）自动获得该能力。`/`-前缀的指令型回复（如 `/kb`、`/cc`）放行，不参与抑制。可通过 `OPENCLAW_SUPPRESS_STALE_REPLY=0` 关闭

# v5.3

### 新增

- **新媒体运营 Crew 模板（selfmedia-operator）**：内置文生图（siliconflow-img-gen）技能，文生视频（siliconflow-video-gen）已迁移至 video-producer crew；提供完整的选题研究→图文输出、草稿扩写→完整文章两套工作流；配图优先策略（用户素材 > 免版权图片 > AI 生成 > 历史复用），素材统一归档至 `campaign_assets/`

- **smart-search 新增平台**：百度贴吧（全局搜索 + 指定吧搜索）、Amazon（含分类/排序过滤），YouTube 新增类型过滤（shorts/video/channel）及"最近1小时"时间过滤

### 改进

- **升级 OpenClaw 至 v2026.4.11**：同步上游安全加固（Browser/security SSRF 防御增强、exec 沙箱安全、媒体访问鉴权）、Dreaming/Active Memory 功能（内存子智能体、日记视图、REM 回���）、Ollama/vLLM/Feishu/Teams 若干 bug 修复；原 patch 004（web_fetch RFC2544 支持）已被上游原生集成，改为配置项并同步到 `config-templates/openclaw.json`

- **sales-cs 数据库访问重构**：将所有客户数据库操作改为命名脚本（`skills/customer-db/scripts/`），禁止直接执行 SQL，增强安全性和可维护性

- **sales-cs 消息防重**：修复工具调用轮次中输出面向客户文本导致重复消息的问题；统一 customerdb hook 与命令路径的 peer 规范化逻辑

- **smart-search 搜索引擎策略调整**：主推 Bing（国内网络稳定可用），百度降为 backup，Quark 降为 fallback，移除 Google（国内经常不可用）

- **系统配置**：修复 setup-crew 中所有 agent 的 reasoningDefault 未正确关闭的问题

### 文档

- `docs/quick_start.md` 新增"推荐上手三步走"：含招募对内/对外 crew、注入业务背景、IT Engineer 运维的完整对话示例

- README 完善：补充 openclaw clone 步骤；新增 opencli 致谢

# v5.2

- combine ofb and wiseflow
- publish sales-db and self-media operator

# v5.0

upgrage workflow to Agent!

# v4.32
- bug fix；

- import error\can not work when use rss souces only.

- update patchright to 1.57.2

- clean useless code

# v4.3.1

- 后端新增 info_stat 统计接口，并补齐 user_notify、user_prompt、ws_ping 等前端交互相关接口。

  Added info_stat statistics endpoint and completed frontend interaction endpoints such as user_notify, user_prompt, and ws_ping.

- read_info 参数与 task time_slots 枚举同步为当前实现。

  Synced read_info parameters and task time_slots enum with the current implementation.

- 后端接口文档更新，移除已弃用的 mc_backup_accounts CRUD 说明。

  Updated backend API docs and removed deprecated mc_backup_accounts CRUD descriptions.

# v4.30

- 升级为与 pro 版本一样的架构，同时具有一样的 api，可无缝共享 [wiseflow+](https://github.com/TeamWiseFlow/wiseflow-plus) 生态！

  Upgraded to the same architecture as the pro version, with the same api, seamlessly sharing the [wiseflow+](https://github.com/TeamWiseFlow/wiseflow-plus) ecosystem!

# v4.2

- 全新的网页爬取方案，使用 patchright 直连本地用户真实浏览器，从而实现更加强大的反爬虫伪装能力，以及提供用户数据持久化留存等特性；

  Brand new web crawling solution: uses patchright to directly connect to the user's real local browser, providing much stronger anti-crawling disguise capabilities and features like persistent user data storage.

- 配套提供预登录、清除、深度清除脚本

  Provided supporting scripts for pre-login, cleanup, and deep cleanup.

- 大幅简化 web crawler相关的 config

  Greatly simplified web crawler-related configuration.

- 新增了proxy方案（支持直连提供商服务器，动态获取，本地缓存）

  Added a new proxy solution (supports direct connection to provider servers, dynamic acquisition, and local caching).

- 整合 Crawler4ai script 方案，提供网页操作能力

  Integrated Crawler4ai script solution, enabling web page operation capabilities.

- 重构搜索引擎方案，适配新的爬取方案并修复一些累积问题

  Refactored search engine solution to adapt to the new crawling approach and fixed some accumulated issues.

- 升级 docker 部署方案，适配全新的打包 work flow。

  Upgraded Docker deployment solution to fit the brand new packaging workflow.


# v4.1

- 通用llm提取支持设定 role 和 purpose，从而实现更加精准的提取

  Universal LLM extraction supports setting role and purpose, enabling more precise extraction

- 社交平台信源增加查找创作者详情的功能

  Added functionality to search for creator details in social media platform sources

- 增加自定义精准搜索功能（自定义 info 提取字段）

  Added custom precision search functionality (custom info extraction fields)

- 可以为关注点指定搜索源，目前支持 bing、github、arxiv、ebay 四个源，并且全部使用平台原生接口，无需额外申请并配置第三方 key

  Can specify search sources for focus points, currently supporting four sources: bing, github, arxiv, ebay, all using platform native interfaces without requiring additional third-party key applications and configurations

- 优化的缓存以及缓存遗忘机制

  Optimized caching and cache forgetting mechanisms

- 修复快手平台搜索结果为空时的错误处理

  Fixed error handling when Kuaishou platform search results are empty

# v4.0

- 深度重构 Crawl4ai（0.6.3）和 MediaCrawler， 并整合引入 Nodriver，大幅提升获取能力，支持社交平台内容获取（4.0版本提供对微博和快手平台的支持）；

  Deeply refactored Crawl4ai (0.6.3) and MediaCrawler, integrated Nodriver, significantly enhanced content acquisition capabilities, supporting social media platform content retrieval (version 4.0 provides support for Weibo and Kuaishou platforms);

- 全新的架构，混合使用异步和线程池，大大提升处理效率（同时降低内存消耗）；

  New architecture utilizing a hybrid approach of async and thread pools, greatly improving processing efficiency (while reducing memory consumption);

- 继承了 Crawl4ai 0.6.3 版本的 dispacher 能力，提供更精细的内存管理能力；

  Inherited the dispatcher capabilities from Crawl4ai 0.6.3 version, providing more refined memory management capabilities;

- 深度整合了 3.9 版本中的 Pre-Process 和 Crawl4ai 的 Markdown Generation流程， 规避了重复处理；

  Deeply integrated the Pre-Process from version 3.9 and Crawl4ai's Markdown Generation process, avoiding duplicate processing;

- 放弃了通过 pocketbase 的api 进行数据库操作，改为直接读写 sqlite 数据库，因此无需用户在 .env 中提供pocketbase的账密，也规避了登录过期导致数据库无法读写，从而产生大量日志的隐患；

  Abandoned database operations through PocketBase API, switched to direct SQLite database read/write, eliminating the need for users to provide PocketBase credentials in .env, and avoiding the risk of database read/write failures due to login expiration that could generate excessive logs;

- 优化 llm 处理策略，更加符合思考模型的特性；

  Optimized LLM processing strategy to better align with the characteristics of thinking models;

- 优化了对 RSS 信源的支持；

  Enhanced support for RSS sources;

- 优化了代码仓文件结构，更加清晰且符合当代 python 项目规范；

  Optimized repository file structure, making it clearer and more compliant with contemporary Python project standards;

- 改为使用 uv 进行依赖管理，并优化了 requirement.txt 文件；

  Switched to using uv for dependency management and optimized the requirement.txt file;

- 优化了启动脚本（提供提供 windows 版本），真正做到"一键启动"；

  Optimized startup scripts (including Windows version), achieving true "one-click startup";

- 优化了日志输出，增加 recorder 总结，并提供更精细化的日志输出控制。

  Enhanced log output, added recorder summaries, and provided more granular log output control.


# v3.9-patch3

- 更改版本号命名规则

  Change version number naming rules

- 诸多累积修复

  Numerous cumulative fixes

# v0.3.9-patch2

- 定制更改 crawl4ai 0.4.30 版本，以取得更好的性能

  Modified crawl4ai version 0.4.30 for better performance

- 相应的更改 core/requirements.txt

  Corresponding changes to core/requirements.txt

- 更改 prompt，但未在 qwen2.5-14b 模型上发现改进

  Modified the prompt, but no improvements were found on the qwen2.5-14b model


# V0.3.9

- 适配 Crawl4ai 0.4.248 版本，优化了性能

  Adapt to Crawl4ai 0.4.248 version, optimized performance

- 累积 bug 修复

  Cumulative bug fixes

- 增加 docker 运行方案（感谢 @braumye 贡献）

  Added docker running solution (thanks to @braumye for contributing)


# V0.3.8

- 增加对 RSS 信源的支持

  add support for RSS source

- 支持为关注点指定信源，并且可以为每个关注点增加搜索引擎作为信源

  support to specify source for each focus point, and add search engine as source

- 进一步优化信息提取策略（每次只处理一个关注点）

  Further optimized information extraction strategy (processing one focus point at a time)

- 优化入口逻辑，简化并合并启动方案 （感谢 @c469591 贡献windows版本启动脚本）

  Optimized entry logic, simplified and merged startup solutions (thanks to @c469591 for contributing Windows startup script)


# V0.3.7

- 新增通过wxbot方案获取微信公众号订阅消息信源（不是很优雅，但已是目前能找到的最佳方案）
  
  Added WeChat Official Account subscription message source acquisition through wxbot solution (not very elegant, but currently the best solution available)

- 升级适配 Crawl4ai 0.4.247 版本，

  Upgraded to fit Crawl4ai 0.4.247 version,

- 通过新增预处理流程以及全新设计的推荐链接提取策略，大幅提升信息抓取效果，现在7b 这样的小模型也能比较好的完成复杂关注点（explanation中包含时间、指标限制这种）的提取了。

  Through the addition of a new pre-processing process and a completely redesigned recommended link extraction strategy, the information capture effect has been significantly improved, and now even small models like 7b can better complete the extraction of complex focus points (such as time and index limits in the explanation).

- 提供自定义提取器接口，方便用户根据实际需求进行定制。

  Provided a custom extractor interface to allow users to customize according to actual needs.

- bug 修复以及其他改进（crawl4ai浏览器生命周期管理，异步 llm wrapper 等）（感谢 @tusik 贡献）

  Bug fixes and other improvements (crawl4ai browser lifecycle management, asynchronous llm wrapper, etc.)

  Thanks to @tusik for contributing

# V0.3.6
- 改用 Crawl4ai 作为底层爬虫框架，其实Crawl4ai 和 Crawlee 的获取效果差别不大，二者也都是基于 Playwright ，但 Crawl4ai 的 html2markdown 功能很实用，而这对llm 信息提取作用很大，另外 Crawl4ai 的架构也更加符合我的思路；

  Switched to Crawl4ai as the underlying web crawling framework. Although Crawl4ai and Crawlee both rely on Playwright with similar fetching results, Crawl4ai's html2markdown feature is quite practical for LLM information extraction. Additionally, Crawl4ai's architecture better aligns with my design philosophy.

- 在 Crawl4ai 的 html2markdown 基础上，增加了 deep scraper，进一步把页面的独立链接与正文进行区分，便于后一步 llm 的精准提取。由于html2markdown和deep scraper已经将原始网页数据做了很好的清理，极大降低了llm所受的干扰和误导，保证了最终结果的质量，同时也减少了不必要的 token 消耗；

  Built upon Crawl4ai's html2markdown, we added a deep scraper to further differentiate standalone links from the main content, facilitating more precise LLM extraction. The preprocessing done by html2markdown and deep scraper significantly cleans up raw web data, minimizing interference and misleading information for LLMs, ensuring higher quality outcomes while reducing unnecessary token consumption.

   *列表页面和文章页面的区分是所有爬虫类项目都头痛的地方，尤其是现代网页往往习惯在文章页面的侧边栏和底部增加大量推荐阅读，使得二者几乎不存在文本统计上的特征差异。*
   *这一块我本来想用视觉大模型进行 layout 分析，但最终实现起来发现获取不受干扰的网页截图是一件会极大增加程序复杂度并降低处理效率的事情……*

  *Distinguishing between list pages and article pages is a common challenge in web scraping projects, especially when modern webpages often include extensive recommended readings in sidebars and footers of articles, making it difficult to differentiate them through text statistics.*

  *Initially, I considered using large visual models for layout analysis, but found that obtaining undistorted webpage screenshots greatly increases program complexity and reduces processing efficiency...*
  
- 重构了提取策略、llm 的 prompt 等；

  Restructured extraction strategies and LLM prompts;

  *有关 prompt 我想说的是，我理解好的 prompt 是清晰的工作流指导，每一步都足够明确，明确到很难犯错。但我不太相信过于复杂的 prompt 的价值，这个很难评估，如果你有更好的方案，欢迎提供 PR*

   *Regarding prompts, I believe that a good prompt serves as clear workflow guidance, with each step being explicit enough to minimize errors. However, I am skeptical about the value of overly complex prompts, which are hard to evaluate. If you have better solutions, feel free to submit a PR.*

- 引入视觉大模型，自动在提取前对高权重（目前由 Crawl4ai 评估权重）图片进行识别，并补充相关信息到页面文本中；

  Introduced large visual models to automatically recognize high-weight images (currently evaluated by Crawl4ai) before extraction and append relevant information to the page text;

- 继续减少 requirement.txt 的依赖项，目前不需要 json_repair了（实践中也发现让 llm 按 json 格式生成，还是会明显增加处理时间和失败率，因此我现在采用更简单的方式，同时增加对处理结果的后处理）

  Continued to reduce dependencies in requirement.txt; json_repair is no longer needed (in practice, having LLMs generate JSON format still noticeably increases processing time and failure rates, so I now adopt a simpler approach with additional post-processing of results)

- pb info 表单的结构做了小调整，增加了 web_title 和 reference 两项。

  Made minor adjustments to the pb info form structure, adding web_title and reference fields.

- @ourines 贡献了 install_pocketbase.sh 脚本

  @ourines contributed the install_pocketbase.sh script

- @ibaoger 贡献了 windows 下的pocketbase 安装脚本

  @ibaoger contributed the pocketbase installation script for Windows

- docker运行方案被暂时移除了，感觉大家用起来也不是很方便……

  Docker running solution has been temporarily removed as it wasn't very convenient for users...

# V0.3.5
- 引入 Crawlee(playwrigt模块)，大幅提升通用爬取能力，适配实际项目场景；
  
  Introduce Crawlee (playwright module), significantly enhancing general crawling capabilities and adapting to real-world task;

- 完全重写了信息提取模块，引入"爬-查一体"策略，你关注的才是你想要的；

  Completely rewrote the information extraction module, introducing an "integrated crawl-search" strategy, focusing on what you care about;

- 新策略下放弃了 gne、jieba 等模块，去除了安装包；

  Under the new strategy, modules such as gne and jieba have been abandoned, reducing the installation package size;

- 重写了 pocketbase 的表单结构；
  
  Rewrote the PocketBase form structure;

- llm wrapper引入异步架构、自定义页面提取器规范优化（含 微信公众号文章提取优化）；

  llm wrapper introduces asynchronous architecture, customized page extractor specifications optimization (including WeChat official account article extraction optimization);

- 进一步简化部署操作步骤。

  Further simplified deployment steps.
