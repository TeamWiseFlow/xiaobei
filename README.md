# 小贝（xiaobei）

小贝（xiaobei）是为OPC/中小微企业量身打造的自媒体获客智能体，底层架构基于 [openclaw](https://github.com/openclaw/openclaw)，目前它能帮你：

- 微信公众号文章写作、排版与推送
- 小红书/小绿书图文创作与发布
- 图文海报生成
- 视频生成与多平台分发（支持视频号、抖音、小红书）
- Twitter/X、微博、知乎等平台发文
- 微信朋友圈内容发布（通过企业微信接口）
- 爆款视频追爆分析、仿写与再创作（支持抖音、B站和小红书视频链接）
- 赛道头部账号DNA级复刻（目前支持小红书、微信视频号、抖音、微信公众号四个平台）
- 已发布作品数据监控与每日定时复盘
- 自媒体评论区获客
- 7*24 小时智能客服（售前接待）
- 通过社交媒体寻找潜在客户或市场调研
- 信息搜集与情报：内置 Smart Search，覆盖小红书、抖音、微博、知乎、B站、Twitter、YouTube、视频号、LinkedIn、Reddit、新闻、政务、财经、学术、购物、GitHub 等 18 类信源——无需配置任何 key、纯免费
- "四声分析"法战略研判与讨论
- 产品deck、ppt制作，投资/IR 材料准备
- 网站设计与制作、ICP 备案等材料辅助
- ……

并且你只需通过手机上的微信与他沟通，即可实现全部功能！（同时支持飞书、企业微信）

<img width="960" src="assets/feature1.jpg" />

<img width="960" src="assets/feature2.jpg" />

xiaobei 由Wiseflow (原AI首席情报官）作者 bigbrother666sh 开发。

官网：[openclaw-for-business.com](https://openclaw-for-business.com/)

---

## 🚀 **V5.7.1~5.7.2 更新**

- 小红书、抖音、视频号 DNA系统升级到2.0架构，Let's do this like an expert！
- content producer 升级为专家系统，现在除了AIGC大片外，还可以复刻众多短视频平台流行的“套路”，更易获得平台推荐流量：
  > 效果展示，xiaobei的视频号：https://openclaw-for-business.com/xiaobei-wxchannel.jpg
- xiaobei 可直接指挥content producer，用户可选择将brief出具、节点验收等委托xiaobei
- 新增抖音平台图文音乐内容发布能力，支持多图上传、选择推荐配乐与发布链接回收。
- AIGC 端点支持阿里云百炼 Agent Plan：现在无需去多个平台开通不同账号，最简只用初始安装时的百炼账号就可获得全部能力。
- 修复一键安装脚本openclaw-weixin不会自动升级的问题

详见 [CHANGELOG.md](CHANGELOG.md)

---

## 🌟 快速开始

### 0. 准备 API Key

推荐开通 [阿里云百炼「Token Plan」套餐](https://www.aliyun.com/benefit/ai/aistar?clubBiz=subTask..12766005..10274..)——一个套餐覆盖**思考与对话、图像生成、TTS 语音合成、ASR 语音识别和视频生成**全部大模型能力，无需为这些能力分别准备其他供应商账号或 Key。

> 💡 **套餐选择**：前期熟悉安装可选 **Lite 版 39 元/月**；正常使用建议 **Standard 版 139 元/月**。想继续使用火山CodePlan见下方 "模型费用说明"

> 🎬 **想用视频生成能力？** 默认可直接复用百炼 `AWK_API_KEY` 调用 `happyhorse` 系列，也可通过配置 `MODELSTUDIO_API_KEY` 和 `WORKSPACE_ID`使用百炼平台的赠送额度和“节省计划“包。

> 除了阿里云的`happyhorse`系列，我们现在也支持 minimax 的H3！详见下方[视频生成模型配置](#-视频生成模型配置)

### 推荐：一键脚本安装（预构建 tarball 路线）

一行命令，全程无需预装 Node / pnpm / git（tarball 自带 portable Node + pnpm）。脚本完成后**唯一人工输入**是填 `AWK_API_KEY`（「TOKEN PLAN」套餐的 key）。

**macOS / Linux（bash，一行命令）：**

```bash
# GitHub 线路（适合能正常访问 GitHub 的网络环境）
bash -c "$(curl -fsSL https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.sh)"
# 国内 atomgit 线路（tarball 走 atomgit.com → GitCode CDN，全程国内直连，脚本也从 raw.atomgit.com 拉取）
bash -c "$(curl -fsSL https://raw.atomgit.com/wiseflow/xiaobei/raw/master/scripts/install-atomgit.sh)"
```

**Windows（PowerShell）：**

> **Windows 用户请以管理员身份运行 PowerShell 再安装**（右键 PowerShell → "以管理员身份运行"）。
> 原因：安装过程中创建 NTFS 符号链接需要管理员权限（或开启开发者模式）；非管理员也能装，软链失败会自动回退拷贝。

```powershell
# GitHub 线路（适合能正常访问 GitHub 的网络环境）
irm https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.ps1 | iex
# 国内 atomgit 线路（tarball 走 atomgit.com → GitCode CDN，全程国内直连，脚本也从 raw.atomgit.com 拉取）
irm https://raw.atomgit.com/wiseflow/xiaobei/raw/master/scripts/install-atomgit.ps1 | iex
```

> 按网络环境选一条命令即可：能正常访问 GitHub 走 GitHub 线路（脚本 `install.sh` / `install.ps1`）；国内网络走 atomgit 线路（脚本 `install-atomgit.sh` / `install-atomgit.ps1`，全程不经 GitHub）。两条线路安装产物完全一致，只是下载源不同。

> install 脚本默认拉最新 release tag + 下载 tarball。指定版本：`export XIAOBEI_TAG=v5.6.3`（PowerShell：`$env:XIAOBEI_TAG="v5.6.3"`）。

> 💡 **下载中断 / 安装失败？多试几次就好。** tarball 体积较大（~140MB），首装还要下 Firefox 反指纹浏览器（~557MB），网络偶发中断属正常。脚本幂等，重跑会续上已下的部分。

> ⚠️ **Windows 必须装 bash**（Git Bash 或 WSL）。install.ps1 / install-atomgit.ps1 用 `tar`（Win10 1803+ 自带）解压 tarball，但 `setup-crew.sh` 是 bash 脚本，部署 crew workspace 离不开 bash。无 bash 时脚本会跳过 crew 模板部署并提示手动补跑——此时小贝团队起不来。装 Git Bash：https://git-scm.com （安装时勾选 "Add to PATH"）。

> 完整步骤：先装 Git Bash（安装时勾选 "Add to PATH"，让 bash 进 PowerShell 的 PATH）→ 再在 PowerShell 跑上面那条 `irm | iex`。

> 💡 **Windows 建议打开「开发者模式」**（设置 → 隐私和安全 → 开发者选项 → 开启开发人员模式，Win10 1703+ 支持）。安装脚本会创建两条软链：仓内 `skills/` → `~/.openclaw/skills`、各 crew 的 `skills/` → `~/.openclaw/workspace-<crew>/skills/`，让 openclaw 的 skill loader 拾取技能、且仓内改完即生效无需重跑安装。软链在 Windows 上需要开发者模式（或管理员 PowerShell）；两者都没打开时脚本会自动回退为拷贝——功能正常但技能不会随仓更新自动同步，重跑安装才会刷新。

装好后脚本最后会自动出微信绑定二维码——用手机微信扫一下、点确认，小贝就能用了。已绑过的机器自动跳过这一步。

> **目录职责**：`~/xiaobei/` = 程序（引擎 + 模板 + 脚本 + 工具 + wrapper）；`~/.openclaw/` = 运行数据（openclaw.json + daemon.env + workspaces + logs）。两者分开，升级只换 `~/xiaobei/`，用户数据不动。可用 `XIAOBEI_HOME` / `OPENCLAW_HOME` env 覆盖。

> **系统要求**：推荐 Ubuntu 22.04；支持 WSL2 / macOS（arm64 + x64）；Windows 10 1803+（x64，需 Git Bash 或 WSL）。WSL2 下脚本自动注入 GUI 显示变量。

> 🖥️ **部署机器建议**：推荐用一台 **7×24 小时常开**的电脑部署，上面**不要放置个人隐私 / 机密文件**。若你希望在日常办公电脑上安装、且只在用时启动——可以期待我们即将推出的**官方 Docker 镜像**，具体可扫下方二维码咨询掌柜👇。

> **调试模式**（前台单次启动，适合测试，不走 launchd/systemd 服务）：`~/xiaobei/bin/openclaw gateway run`

> 排障见 [`docs/install-troubleshooting.md`](docs/install-troubleshooting.md)

### 微信换绑 / 增加绑定

装好后想**换一个微信号**（换绑）或**再加一个号**，都用 `channels login` 重新出二维码。`openclaw` 不在 PATH，下面命令用全路径 `~/xiaobei/bin/openclaw`（把 `~/xiaobei/bin` 加进 PATH 后可直接敲 `openclaw`）。

**换绑（替换成新号）**：先停 gateway、清掉旧账号数据，再重新 login 出码：

```bash
~/xiaobei/bin/openclaw gateway stop
rm -rf ~/.openclaw/openclaw-weixin/
~/xiaobei/bin/openclaw gateway start
~/xiaobei/bin/openclaw channels login --channel openclaw-weixin
```

> `channels login` 出码后 8 分钟内有效，扫码慢会自动刷新，用新微信扫一下、点确认即完成。

**增加绑定（保留旧号、再加一个）**：直接再跑一次 login，用另一个微信扫：

```bash
~/xiaobei/bin/openclaw channels login --channel openclaw-weixin
```

> ⚠️ 多账号时，若两个号都能匹配同一个收件人，发消息会报 `ambiguous — N accounts matched`。所以**换号场景建议用上面的"换绑"流程清掉旧号**，避免歧义；只在确实要多号并存时用"增加绑定"。

### 升级

**已装用户重跑 install 脚本即升级**：脚本检测到 `~/.openclaw/openclaw.json` 已存在时自动走更新路线——只刷新程序目录 `~/xiaobei/`（拉新 tarball + `pnpm install --prod` 重建依赖 + 幂等刷 camoufox/weixin/awada）+ restart gateway，**不碰运行数据**（openclaw.json / workspace / daemon.env 已有 key 全保留）。要强覆盖运行数据加 `--force`（会备份旧 openclaw.json）。

```bash
# macOS / Linux（GitHub 线路）
bash -c "$(curl -fsSL https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.sh)"
# macOS / Linux（atomgit 线路，国内）
bash -c "$(curl -fsSL https://raw.atomgit.com/wiseflow/xiaobei/raw/master/scripts/install-atomgit.sh)"
# Windows (PowerShell，GitHub 线路)
irm https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.ps1 | iex
# Windows (PowerShell，atomgit 线路，国内)
irm https://raw.atomgit.com/wiseflow/xiaobei/raw/master/scripts/install-atomgit.ps1 | iex
```

> 已手动 `git clone` 仓做开发的用户仍可用 `scripts/update.sh` 走 fetch + rebuild 路线（不重装依赖、不卸 daemon）。普通用户用上面的 install 脚本即可。

### 系统与环境要求

| 项目 | 最低要求 | 推荐配置 |
|------|---------|---------|
| CPU | 2 核 | 4 核 |
| 内存 | 8 GB | 16 GB |
| 可用硬盘 | 40 GB | 120 GB |
| 带宽 | 10 Mbps | — |

- **网络**：建议使用正常住宅 IP，数据中心 IP 部分平台可能识别限制。
- 但部分发布能力又需要固定IP（平台限制，非软件能力问题），针对这个矛盾 Wiseflow team 已推出中转服务，具体可以添加下方掌柜二维码详询👇

> **💡 模型费用说明**
>
> xiaobei 底层基于 openclaw，建议先准备好大模型 API：
>
> - **主力模型（强烈推荐）**：[阿里云百炼「Token Plan」套餐](https://www.aliyun.com/benefit/ai/aistar?clubBiz=subTask..12766005..10274..) — 一个套餐已经可以覆盖xiaobei系统所需的所有大模型（思考与对话、图像生成、TTS 语音合成、ASR 语音识别和视频生成)。
>
> - **仍想用火山方舟 Coding Plan 的用户**：在默认配置模板基础上参考 [openclaw-awk.json](config-templates/openclaw-awk.json)，手动替换 `provider` 和 `agents.default` 字段即可。
>
> - **想用 [OrcaRouter](https://www.orcarouter.ai) 的用户**：OrcaRouter 是 OpenAI 兼容的模型网关，一份 key 即可路由 DeepSeek、GLM、Qwen、Claude、Gemini 等主流模型。它还在同一端点运行网关级、零信任的 AI Agent 安全防护——以默认拒绝（default-deny）的方式审查每条 prompt/response 并约束每个工具调用，无需改动应用代码。开通后获得 `ORCAROUTER_API_KEY`（`sk-orca-...`），参考 [openclaw-orcarouter.json](config-templates/openclaw-orcarouter.json) 替换 `provider` 和 `agents.default` 字段即可（或用它替换默认模板）。

> **🎬 视频生成模型配置**
>
> AI 视频生成（`aigc-video-gen`，短视频制作与素材补充都会用到）默认复用百炼 `AWK_API_KEY`，走 Agent Plan 端点。也可按需配置百炼业务空间、火山或 MiniMax：
>
> | 平台 | 环境变量 | 模型 |
> |------|---------|------|
> | 阿里云百炼 Agent Plan（默认） | `AWK_API_KEY` | `happyhorse-1.1-i2v` / `happyhorse-1.1-t2v` / `happyhorse-1.1-r2v` |
> | 阿里云百炼业务空间（可选） | `WORKSPACE_ID` + `MODELSTUDIO_API_KEY`（或 `DASHSCOPE_API_KEY`） | 同上 |
> | 火山引擎方舟 | `AWK_GEN_KEY` | `doubao-seedance-2-0-fast-260128` / `doubao-seedance-2-0-260128` / `doubao-seedance-2-0-mini-260615` |
> | minimax海螺 | `MINIMAX_API_KEY` | `minimax-H3` |
>
> 只配置百炼 `AWK_API_KEY` 时自动走 Agent Plan；若已有其他视频凭据，自动选择顺序为 MiniMax → 火山 → 百炼业务空间 → 百炼 Agent Plan。均未配置时，小贝改用 pexels/pixabay 素材模式（仍需注册获取对应的免费 Key）。`AWK_GEN_KEY` 是火山视频生成凭据，与百炼 `AWK_API_KEY` 不可混用。需要调整配置时，可以让小贝调用内置 IT Engineer 协助。

> **🧠 进阶：记忆增强与 dream（可选）**
>
> 默认配置下，小贝的记忆走 FTS 全文检索，已经够用且零额外配置。如果你记忆体量很大、想要更好的语义召回，可以接入一个 embedding 模型；也可以选择打开凌晨"做梦"机制让小贝在夜间整理记忆。
>
> 任何 OpenAI 接口格式的 embedding 服务都可以接（如阿里云百炼的 `text-embedding-v3/v4` 系列）。配置方法：把 `agents.defaults.memorySearch.provider` 从 `"none"` 改为 `"openai-compatible"`，并补上 `remote.baseUrl` / `remote.apiKey` / `model`；想开做梦就把 `plugins.entries.memory-core.config.dreaming.enabled` 改回 `true`。改完重启 gateway 生效。可以让小贝帮你完成配置。

### 配置繁琐，不想操心？

🎉 wiseflow团队现提供 **远程安装** 与 **远程技术支持** 增值服务，同时继续提供**VIP Club**（售价 **168 元/年**）服务，陪伴你从"小白"到"大神"！

VIP Club（售价 **168 元/年**），权益包括：

- 付费知识库：「手把手」安装教程、上手指南、配置全案、高阶玩法、最佳实践等……
- VIP 微信交流群：问题讨论、产品反馈、技术沟通、专家 DNA 分享……
- 官方中转服务：针对部分自媒体平台的发布技能要求固定 IP 和签名的问题，向 VIP Club 会员免费提供官方中转服务
- 会员期内所有增值服务享半价（不含 awada lane 租赁）
- 会员可申请成为服务合作商
- 会员可申请定制开发服务

*⚠️ 如存在不当使用官方中转服务、在社群发表不当言论等行为，Wiseflow 团队有权提前终止会员资格且不予退款，详见会员协议。*

另开放 **服务代理商** 合作，共享AI时代红利！详见：https://openclaw-for-business.com/pricing 

也欢迎添加"掌柜的"企业微信（由 xiaobei sales-cs 驱动）咨询了解：

<img width="360" height="360" alt="xiaobei掌柜" src="https://github.com/user-attachments/assets/b013b3fd-546e-4176-b418-57bee419e761" />

🌹 开源不易，感谢支持！

---

## 你的小贝其实不是一个人，而是一支团队

小贝的背后其实是一支 AI 团队，他们有的为小贝提供运维支撑，有的扩增小贝的能力：

### AI 团队的自主协作

小贝团队成员之间可以自主完成协作，而无需用户介入，这也是为什么您只需要一个微信入口就可以完整使用所有功能的原因，这意味着：

Crew 遇到自己不能解决的问题：
  ```text
  1. ❌ 不会停止工作
  2. ❌ 不会喊用户帮忙 （这很傻，不是吗？）
  3. ✅ 自主调用合适的 subagent 协助
  4. ✅ 问题解决后继续原任务
  ```

工作流程：

  假设小贝正在处理内容发布任务，突然遇到 API 调用失败：
  ```text
  [xiaobei] 正在发布文章到微信公众号...
  [xiaobei] 发现错误：access_token expired
  [xiaobei] 判断：这是技术问题，调用 IT Engineer
    └── [it-engineer] 收到协助请求：access_token 过期
    └── [it-engineer] 分析原因：token 刷新机制异常
    └── [it-engineer] 执行修复：重新配置 token 刷新
    └── [it-engineer] 返回结果：问题已解决
  [xiaobei] 收到解决方案，继续发布文章
  [xiaobei] 任务完成
  ```
  用户视角：整个过程用户无感知，Agent 自主完成了问题排查和修复。

<img width="960" src="assets/crews_co_work.png" />

## 专业的AI客服无需其他的系统

小贝团队中已包含强大的 AI 客服（sales-cs），您无需再额外购买或部署其他系统。只需要对小贝说："我需要招募一名客服"即可。

小贝团队中的 sales-cs 不仅可以按照预设知识库进行精准回答，同时也具有极高的情商，懂得在回答客户问题的过程中步步为营的推进成交。对客户的诘难式提问，也能妥当应对。

<img width="960" src="assets/nb1.jpg" />

*如需让客户直接用微信添加AI客服，需要注册企业微信并租赁 awada lane*

*详询"掌柜的"👆*

## 🔧 全新的浏览器栈

v5.6.0 中我们几乎重构了 OpenClaw 原版的浏览器自动化方案（详见 `docs/browser-stack-replacement-spec-2026-07.md`），v5.6.3 沿用此双线栈并按 OpenClaw v2026.7.1 重新对齐 patch：

| 项 | 说明 |
|----|------|
| `patches/camoufox-cli/` | **forked camoufox-cli**（vendor 自上游 `camoufox-cli@0.6.2`）+ 三个新功能：`upload` 命令（Playwright `setInputFiles`，发布类技能依赖）/ daemon fail-first 队列（同 session 并发直接 fail，不排队不等待）/ `identity export`（导出 UA + 指纹摘要，对应 `cookies export`）。`build.sh` 全局安装替换 `$PATH` 上的上游版 |
| `patches/browser-camoufox-pivot/` | **001 monolith 拆成 35 个单文件 patch**（`patches/` 子目录，按文件名 sort 顺序应用，降低上游漂移失效面）+ adapter + 测试 ship 在 `files/`。删 sandbox 整条路 + 删 host `local-managed` 分支 + 新增 `target=camoufox` 旁路（默认） |
| `patches/overrides.sh` | **去掉 patchright-core 注入**（playwright-core 保留给 remote-cdp 用）；保留 web_search disable |
| `002-disable-web-search-env-var` | **留**：openclaw 内置 web search 大部分需要申请 api key 甚至海外网络，小贝自带完全免费、零部署的 Smart Search 解决方案 | `OPENCLAW_DISABLE_WEB_SEARCH=1` |
| `007-prefer-camoufox-cli` | **留**（改名）：在 browser 工具描述中提示优先用 camoufox-cli 做浏览器自动化，原 browser 工具仅作兜底 | 无 |

**基于这套浏览器栈，我们沉淀了一批浏览器自动化技能**——这些技能源自我们自 AI 首席情报官项目以来长期积累的浏览器自动化技术经验，覆盖登录、填报、发布、互动、抓取等完整工作流：

| 技能 | 职责 |
|------|------|
| `browser-guide` | 浏览器操作最佳实践总纲——登录墙 / CAPTCHA / lazy-load / paywall / 有头无头场景规则 / eval 用法 |
| `smart-search` | 智能搜索——绕开 openclaw 内置 web search 的 api key 依赖，零部署免费方案 |
| `web-form-fill` | 网络表单填报——从信息搜集到浏览器填报的完整工作流，强制有头模式便于用户随时介入 |
| `login-manager` | 平台登录态管理——5 平台统一有头手动登录、探活规则、中央 cookie+UA 存储约定 |
| 各平台发布/互动 skill | `twitter-post` / `twitter-interact` / `weibo-publish` / `zhihu-publish` / `xhs-publish` / `xhs-content-ops` / `douyin-video-publish` / `wechat-channels-publish` / `xianyu-ops` / `wx-mp-hunter` / `wx-mp-engagement` 等平台专属浏览器自动化技能 |

这些技能共享同一套 forked camoufox-cli + 持久化 session 机制，登录态在 session profile 里闭环，按场景分离有头/无头模式（登录+填报走有头，自动化操作走无头），靠 session 名字符串约定共享 profile 目录与登录态。

## 目录结构

```
wiseflow/
├── openclaw/              # 上游仓库（git clone，禁止直接修改）
├── crews/                 # Crew 模板（D8 扁平化，权限由 crew-type + ALLOWED_COMMANDS 决定）
│   ├── _template/         # 空白脚手架（创建新模板的起点）
│   ├── main/              # [default] 小贝——新媒体运营 / 创业伴侣，绑 openclaw-weixin
│   ├── it-engineer/       # [built-in] IT 工程师——幕后运维 + 排障 sub-agent
│   ├── content-producer/  # 内容制作者——视频/视觉生产线
│   └── sales-cs/          # 销售型客服——绑 awada，默认禁用，按需招募
├── skills/                # 公共技能（≥2 crew 共用，smart-search / browser-guide / login-manager 等）
├── patches/               # wiseflow 基础补丁
│   ├── *.patch            # git 补丁（按序号顺序应用到 openclaw/）
│   └── overrides.sh       # pnpm 依赖覆盖（如替换 playwright → patchright）
├── config-templates/      # 配置模板（开箱即用的最佳实践）
│   ├── openclaw.json      # 默认配置模板（阿里云百炼主力 + fts-only 记忆 + dream 关）
│   ├── openclaw-awk.json  # 火山引擎方舟 Coding Plan 备选模板（主力 GLM-5.2）
│   └── openclaw-orcarouter.json # OrcaRouter 网关备选模板（主力 orcarouter/auto）
├── scripts/               # 工具脚本（详见 scripts/README.md）
│   ├── lib/               # 脚本共享工具（agent-skills.sh 等）
│   ├── install.sh         # 一键安装 + 升级（预构建 tarball 路线，macOS + Linux，GitHub 线路；重跑即升级，保留 ~/.openclaw）
│   ├── install-atomgit.sh # 一键安装 + 升级（macOS + Linux，atomgit 国内线路；全程不经 GitHub）
│   ├── install.ps1        # 一键安装 + 升级（Windows，tarball 路线，GitHub 线路；需 Git Bash/WSL）
│   ├── install-atomgit.ps1 # 一键安装 + 升级（Windows，atomgit 国内线路；需 Git Bash/WSL，全程不经 GitHub）
│   ├── update.sh          # 已 git clone 开发用户的升级路线（fetch + rebuild，不重装依赖）
│   ├── dev.sh             # 开发模式启动（前台运行 gateway）
│   ├── setup-crew.sh      # 多 crew 系统安装（同步 markdown + 注入规范，幂等）
│   └── setup-wsl2.sh      # WSL2 环境配置
└── docs/                  # 项目文档
```

运行时数据在 `~/.openclaw/`（openclaw.json、daemon.env、workspaces、sessions、camoufox profile 全在此）；程序在 `~/xiaobei/`（install.sh 解压的预构建 tarball：`openclaw/` 引擎 + `crews/` + `skills/` + `scripts/` + `tools/` portable Node/pnpm + `camoufox-cli/` fork + `bin/openclaw` wrapper）。两者职责分开：升级只换 `~/xiaobei/`，`~/.openclaw/` 用户数据不动。可用 `XIAOBEI_HOME` / `OPENCLAW_HOME` env 覆盖位置。

🌹 即日起为 xiaobei 开源版本贡献 PR（代码、文档、成功案例分享均欢迎），一经采纳，贡献者将获赠 **VIP Club 一年会员**！

## 🛡️ 许可协议

自 4.2 版本起，我们更新了开源许可协议，敬请查阅： [LICENSE](LICENSE)

## 📬 联系方式

有任何问题或建议，欢迎通过 [issue](https://github.com/TeamWiseFlow/xiaobei/issues) 留言。

商务合作（**开放定制开发与 OEM 合作，诚招代理**）请联系"掌柜的"👆，或访问官网：[openclaw-for-business.com](https://openclaw-for-business.com/pricing)。

## 🤝 xiaobei 基于如下优秀的开源项目：

- openclaw(Your own personal AI assistant. Any OS. Any Platform. The lobster way. 🦞) https://github.com/openclaw/openclaw
- camoufox(🦊 Anti-detect browser, Firefox fork — forked camoufox-cli 作为线 1 浏览器主力，vendor 进 `patches/camoufox-cli/`) https://github.com/daijro/camoufox
- Feedparser（Parse feeds in Python） https://github.com/kurtmckee/feedparser
- SearXNG（a free internet metasearch engine which aggregates results from various search services and databases） https://github.com/searxng/searxng
- opencli（A CLI for social media & web platforms — smart-search skill 借鉴了其搜索 URL 模式与平台适配方案） https://github.com/jackwener/opencli
- AiToEarn（多平台自媒体发布工具 — `published-track` 的 18 平台文本/媒体限制规则表与内容校验、twitter 互动操作模式借鉴自此） https://github.com/yikart/AiToEarn
- 文颜(Markdown文章排版美化工具，支持微信公众号、今日头条、知乎等平台。) https://github.com/caol64/wenyan
- Everything Claude Code（Claude Code 全局 skill / rule / agent 集合，wiseflow 的 complex-task 等编排 skill 借鉴了其 blueprint 和 gan-style-harness 的设计思路） https://github.com/affaan-m/everything-claude-code
- awesome-design-md（A curated collection of design systems in markdown format — Designer 内置设计系统库参考了此项目的设计系统结构） https://github.com/VoltAgent/awesome-design-md
- cheat-on-content（自媒体打分算法借鉴、取数方案借鉴） https://github.com/XBuilderLAB/cheat-on-content
- AutoClip（AI 视频智能切片系统 — `talking-head-cut` 技能的高光剪辑算法与工作流借鉴自此；`video-producer` 的 Stage 13b motion-audit 镜头抽帧打分思路亦借鉴其高光判定） https://github.com/zhouxiaoka/autoclip
- HyperFrames（HeyGen 开源的 AI 视频生成编排框架 — `video-producer` 的脚本→分镜→渲染链式工作流与两道闸门审批节奏借鉴自此） https://github.com/heygen-com/hyperframes
- html-video（nexu-io 的 HTML 视频渲染方案 — `video-producer` 的 Stage 10 静帧→成片渲染思路与素材组装约定参考自此） https://github.com/nexu-io/html-video
- ViMax（HKUDS 的视频生成框架 — `video-producer` 的机位一致性约束与素材 slot 规划借鉴其镜头规划策略） https://github.com/HKUDS/ViMax
- OpenMontage（calesthio 的开源蒙太奇剪辑方案 — `video-producer` 的 Stage 12 拼接成片+转场工作流借鉴其片段组装与节奏控制思路） https://github.com/calesthio/OpenMontage
- gbro-collage-broll（MIT — 半调纸拼贴 B-roll 三闸门方法论 — `expert-video` 的 Collage B-roll workflow 移植自此：隐喻设计法、语义色场表、visual-spec schema、静帧/视频 QA 标准照搬，闸门映射为 GATE A/B、渲染栈换成 awk-img-gen + aigc-video-gen i2v） https://github.com/pyang5166/gbro-collage-broll
- agent-skills-launch-pack_（起号方法论知识来源） https://github.com/chenjin-cmd/agent-skills-launch-pack_

## Citation

如果您在相关工作中参考或引用了本项目的部分或全部，请注明如下信息：

```
Author：Wiseflow Team
https://github.com/TeamWiseFlow/xiaobei
```

![star](https://atomgit.com/wiseflow/xiaobei/star/badge.svg) 国内托管地址：[https://atomgit.com/wiseflow/xiaobei](https://atomgit.com/wiseflow/xiaobei)

## 友情链接

[<img src="assets/atomgit.png" alt="atomgit" height="60">](https://gitcode.com/atomgit_atomcode)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[<img src="https://github.com/TeamWiseFlow/xiaobei/raw/4.x/docs/logos/SiliconFlow.png" alt="siliconflow" height="40">](https://cloud.siliconflow.cn/i/WNLYbBpi)
