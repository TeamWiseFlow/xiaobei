# 小贝（wiseflow）

小贝（wiseflow）是为 OPC/中小微企业老板们量身打造的"AI搞钱搭子"，它基于 [openclaw](https://github.com/openclaw/openclaw)，在原版基础上增加了诸多面向真实创业场景的实用技能（同时也做了很多精简和patches），目前它能帮你：

- 微信公众号文章写作、排版与推送
- 小红书图文创作与发布
- 短视频生成与多平台分发
- 爆款视频追爆分析、仿写与再创作
- 数据自动采集与每日定时复盘
- 每日热门选题
- 指定信源监控与提取
- 通过社交媒体寻找潜在客户或市场调研
- 灵感记录与思路梳理
- ”四声分析“法战略研判与讨论
- 软件著作权、ICP备案等材料生成辅助
- ……

并且你只需通过手机上的微信与他沟通，即可实现全部功能！

<img width="960" src="assets/crews.png" />

（这里图要改，改为从视频里边截图，横向排列。）

**除了微信外，我们也支持飞书和企业微信**

---

## 🚀 **v5.5.2 更新**

- **Selfmedia Operator 新增视频制作与分发能力**：一站式短视频制作（`video-product`）支持根据一个主题或一篇文章的链接全流程端到端制作短视频：自动生成脚本 → 逐段生成视频素材（声画同出）→ 合成成片
- Selfmedia Operator 打通微信视频号、小红书、抖音、Twitter/X 等平台分发，形成"制作 → 分发"闭环
- 为Selfmedia Operator引入科学的评估方案和自动复盘方案（发布前预测打分 -> 每日数据复盘 -> 根据复盘调整打分量表 -> 不断优化预测准确性)。以上已内置到所有平台的发布流程中，让运营工作不再“凭感觉”。
- **两个剪辑辅助技能**：`de-mouth`（口播视频去口误，自动识别并删除静音、语气词、卡顿词、重复句、残句）、`highlight-clipper`（ASR + 文本分析自动提取高光片段剪成多段短视频）
- **主力模型切换为 GLM-5.2，推荐火山方舟 Coding Plan**：通过 xiaobei 邀请链接订阅叠加 9.5 折，首月低至 9.4 元
- 适配openclaw 2026-6-10 版本、openclaw-weixin 2.4.6版本

详见 [CHANGELOG.md](CHANGELOG.md)

---

## 🌟 快速开始

### 0. 准备 API Key

1. 注册 [火山引擎方舟 Coding Plan](https://volcengine.com/L/dx-wt80li-I/)（🎁 欢迎使用 xiaobei 邀请链接 / 邀请码 `5Y5A6L86`，订阅叠加 9.5 折，首月尝鲜低至 9.4 元），开通后获得 `AWK_API_KEY`（主力模型 GLM-5.2 走此通道）
2. 注册 [SiliconFlow](https://cloud.siliconflow.cn/i/WNLYbBpi)（🎁 欢迎使用xiaobei邀请链接，注册认证后获得 16 元代金券），获得 `SILICONFLOW_API_KEY`（视觉/替补模型，必申请）

> 如果习惯使用 ChatGPT / Gemini / Claude 等海外模型见下方[模型费用说明](#-模型费用说明)中的 AiHubMix 备选方案。

> 🎬 **想用 5.5.2 的视频生成能力？** 需额外开通火山方舟 `doubao-seedance-2.0` 系列或阿里云百炼 `happyhorse-1.1` 系列模型，并把对应 key（`AWK_GEN_KEY` 或 `MODELSTUDIO_API_KEY`）配置到 `daemon.env`。详见下方[视频生成模型配置](#-视频生成模型配置)。

### 1. 获取代码

至 [Releases](https://github.com/TeamWiseFlow/wiseflow/releases) 下载最新版压缩包并解压；

### 2. 一键安装

```bash
cd wiseflow
./scripts/install.sh
```

`install.sh` 会自动完成：
- 拉取最新代码
- 初始化 `openclaw.json`（内置最佳模型配置，无需手动编辑）
- 安装系统 daemon（开机自启 + 崩溃重启）
- **交互式引导你输入** `AWK_API_KEY` 和 `SILICONFLOW_API_KEY`（仅在首次或缺失时询问）
- 安装腾讯官方 `openclaw-weixin` extension，并引导扫码绑定

> **调试模式**（单次启动，适合测试）：`./scripts/dev.sh gateway`

> **系统要求**：推荐 Ubuntu 22.04；支持 WSL2 / macOS；不建议 Windows 原生

### 3. 微信对话完成 Onboard

安装完成后，打开微信搜索上一步绑定的机器人，直接发消息即可——它会主动引导你完成首次 onboard**：

1. 告诉它你的公司/品牌、产品和目标用户
2. 它会把这些业务背景存入 `business-context/`，后续招募的 crew 自动继承
3. 按需招募第一个 crew（如商务拓展、自媒体运营）
4. 团队扩大后，一条对话即可配置飞书或企业微信工作 channel

**不需要编辑配置文件、不需要手动同步信息——从安装到出活，全程对话完成。**

注：微信官方 openclaw 插件限定一个微信账号只能对应一个机器人，如果您之前已经绑定了其他 Agent（openclaw 或者 hermes 等），这会挤掉已经绑定的 agent。但是在完成 xiaobei 团队配置后，您可以将此 bot 替换回其他 agent，这不影响已经绑定工作渠道的 wiseflow crew team。

> 💡 更详细的操作指引见 [quick start](docs/quick_start.md)

### 系统与环境要求

| 项目 | 最低要求 | 推荐配置 |
|------|---------|---------|
| CPU | 2 核 | 4 核 |
| 内存 | 8 GB | 16 GB |
| 可用硬盘 | 40 GB | 120 GB |
| 带宽 | 10 Mbps | — |

- **网络**：需可访问外网；建议使用正常住宅 IP，数据中心 IP 部分平台可能识别限制
- **部署环境**：支持无头云服务器（ECS）部署，但推荐在有桌面环境的电脑上部署（日常使用中可不插显示器），浏览器自动化类技能在桌面环境下更稳定
- **操作系统**：推荐 Ubuntu 24.04；支持 Windows WSL2、macOS 15 / 26

> **💡 模型费用说明**
>
> xiaobei 底层基于 openclaw，Agent 工作流对 token 消耗有一定要求，建议先准备好大模型 API：
>
> - **主力模型（强烈推荐）**：[火山引擎方舟 Coding Plan](https://volcengine.com/L/dx-wt80li-I/) — 一个套餐覆盖 GLM-5.2、Kimi-K2.7、MiniMax-M3、DeepSeek-V4 系列、Doubao-Seed-2.0 系列等主流模型，**工具不限**，xiaobei 默认主力模型 GLM-5.2 即走此通道。需要注册并开通 Coding Plan 获得 `AWK_API_KEY`。
>   > 🎁 **通过 xiaobei 邀请链接** [https://volcengine.com/L/dx-wt80li-I/](https://volcengine.com/L/dx-wt80li-I/) **订阅**（邀请码 `5Y5A6L86`），可叠加 **9.5 折**优惠，首月尝鲜低至 **9.4 元**，订得越多折扣越大。
> - **替补 & 视觉模型**：[SiliconFlow](https://cloud.siliconflow.cn/i/WNLYbBpi) — 模型丰富，可作为主力模型的 fallback，同时提供视觉理解模型（`Qwen/Qwen3.6-27B`）和生图/生视频 API。需要注册获得 `SILICONFLOW_API_KEY`。
>   > 🎁 以上 SiliconFlow 链接为 xiaobei 邀请链接，通过此链接注册，你和 xiaobei 项目各可获得一张 16 元代金券。
>
> - **海外模型用户**：如果想使用 ChatGPT / Gemini / Claude 等海外模型，可通过 [AiHubMix](https://aihubmix.com/?aff=Gp54) 统一接入（全兼容 OpenAI 接口，国内直连）。欢迎通过此[邀请链接](https://aihubmix.com/?aff=Gp54)注册。备选配置模板见 `config-templates/openclaw-aihubmix.json`。
>
> 配置模板已预置以上最佳实践，`install.sh` 会自动检测所需环境变量并引导你输入。安装后重启 openclaw gateway 即可生效。

> **🎬 视频生成模型配置**
>
> 5.5.2 的短视频制作（`video-product`）需额外开通视频生成模型，并把对应 key 配置到 `daemon.env`（任选其一，百炼优先）：
>
> | 平台 | 环境变量 | 模型 |
> |------|---------|------|
> | 阿里云百炼（优先） | `MODELSTUDIO_API_KEY`（或 `DASHSCOPE_API_KEY`） | `happyhorse-1.1-i2v` / `happyhorse-1.1-t2v` / `happyhorse-1.1-r2v` |
> | 火山引擎方舟 | `AWK_GEN_KEY` | `doubao-seedance-2-0-fast-260128` / `doubao-seedance-2-0-260128` / `doubao-seedance-2-0-mini-260615` |
>
> 两个 key 都配了走百炼，只配 `AWK_GEN_KEY` 走火山，都没配则 `video-product` 自动降级为 pexels/pixabay 免费素材模式。注意 `AWK_GEN_KEY` 与主力模型的 `AWK_API_KEY` 是一个 key，但必须在环境变量中以不同变量名称赋值，火山视频生成只认 `AWK_GEN_KEY`。申请成功后可以让系统自带的全局IT Engineer帮你完成配置。

🎉 xiaobei 目前提供付费知识库，包含《手把手从零开始安装教程》、《安装之后三分钟上手指南》、《Openclaw自定义配置全案教程》、《Windows 下安装 WSL2 无脑教程》、《秘籍：云服务器（ECS）部署》以及各种最佳实践分享，年费仅需¥168，还能加入 **vip微信交流群** ，共同探讨交流各种玩法，还有每月一次的闭门分享（腾讯会议），陪伴你从“小白“到“大神“！

欢迎添加”掌柜的“企业微信（这背后接的就是 xiaobei sales-cs）咨询了解：

<img width="360" height="360" alt="xiaobei掌柜" src="https://github.com/user-attachments/assets/b013b3fd-546e-4176-b418-57bee419e761" />

🌹 开源不易，感谢支持！

## ✨ 小贝详细能力清单

## 小贝不是一个人在战斗

小贝的背后其实是一只AI团队，他们有的为小贝提供运维支持，有的扩增小贝的能力：

| Crew | 职责 | 关键技能 |
|------|------|---------|
| 小贝（main agent） |  ||
| IT工程师（it engineer） |  ||
| 销售型客服（sales-cs）|  |  |
| 制作师（content producer） |  |  |

### AI团队的自主协作
  
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

## 强大的AI客服就在这里

小贝的团队中包含强大的AI客服（sales-cs），您无需再额外部署其他系统。只需要对小贝说：“我需要招募一名客服”即可。

小贝团队中的sales-cs不仅可以按照预设知识库进行精准回答，同时也具有极高的情商，懂得在售前咨询中推进销售。应对客户的诘难式提问，也能妥当应对。

<img width="960" src="assets/nb1.jpg" />

*如需让客户可以通过微信与AI客服进行沟通，则需要注册企业微信并购买增值服务awada server*

*详询“掌柜的”👆*

## patches

xiaobei 通过 `patches/` 目录对 openclaw 源码打补丁，从而实现对原版openclaw的源码级改造：

| 补丁 | 说明 | 相关环境变量 |
|------|------|-------------|
| `002-disable-web-search-env-var` | 支持通过环境变量禁用 openclaw 内置 web search | `OPENCLAW_DISABLE_WEB_SEARCH=1` |
| `003-act-field-validation` | 修复浏览器 act 动作的字段验证逻辑 | 无 |
| `005-browser-timeout-env-var` | 支持通过环境变量自定义浏览器操作默认超时（原默认仅 20 秒，网络慢时容易中断） | `OPENCLAW_BROWSER_TIMEOUT_MS=60000` （执行 install.sh 脚本会自动配置）|
| `006-connectovercdp-no-defaults` | `connectOverCDP` 启用 `noDefaults: true`，避免 Patchright 修改用户浏览器状态 | 无 |

## 极简的部署和上手设计

## 目录结构

```
wiseflow/
├── openclaw/              # 上游仓库（git clone，禁止直接修改）
├── crews/                 # Crew 模板（扁平，产品拆分后 D8）
│   ├── _template/         # 空白脚手架（创建新模板的起点）
│   ├── shared/            # 共享协议（COMMAND_TIERS / CREW_TYPES）
│   ├── index.md           # 模板注册表
│   ├── it-engineer/       # [built-in] IT Engineer（sub-agent，系统运维 + 排障）
│   ├── main/# [default] 新媒体运营（创业伴侣，绑 openclaw-weixin）
│   ├── content-producer/    # 内容制作者
│   └── sales-cs/          # 销售型客服（绑 awada，默认禁用）
├── skills/                # 公共技能（≥2 crew 共用，smart-search / browser-guide / login-manager 等）
├── patches/               # wiseflow 基础补丁
│   ├── *.patch            # git 补丁（按序号顺序应用到 openclaw/）
│   └── overrides.sh       # pnpm 依赖覆盖（如替换 playwright → patchright）
├── config-templates/      # 配置模板（开箱即用的最佳实践）
│   └── openclaw.json      # 默认配置模板
├── scripts/               # 工具脚本（详见 scripts/README.md）
│   ├── lib/               # 脚本共享工具
│   ├── install.sh         # 一键安装 / 升级（推荐入口）
│   ├── apply-addons.sh    # 应用补丁 + 全局技能 + awada 注入 + build + restart
│   ├── dev.sh             # 开发模式启动（前台运行 gateway）
│   ├── setup-crew.sh      # 多 crew 系统安装（仅同步 markdown，幂等）
│   └── setup-wsl2.sh      # WSL2 环境配置
└── docs/                  # 项目文档
```

运行时数据使用上游默认位置 `~/.openclaw/`。

🌹 即日起为 xiaobei 开源版本贡献 PR（代码、文档、成功案例分享均欢迎），一经采纳，贡献者将获赠 xiaobei pro版本一年使用权！

## 🛡️ 许可协议

自4.2版本起，我们更新了开源许可协议，敬请查阅： [LICENSE](LICENSE) 

## 📬 联系方式

有任何问题或建议，欢迎通过 [issue](https://github.com/TeamWiseFlow/wiseflow/issues) 留言。

商务合作专属邮箱：`zm.zhao # foxmail.com` (发送时将 # 替换为 @)

## 🤝 xiaobei 基于如下优秀的开源项目：

- openclaw(Your own personal AI assistant. Any OS. Any Platform. The lobster way. 🦞) https://github.com/openclaw/openclaw
- Patchright(Undetected Python version of the Playwright testing and automation library) https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python
- Feedparser（Parse feeds in Python） https://github.com/kurtmckee/feedparser
- SearXNG（a free internet metasearch engine which aggregates results from various search services and databases） https://github.com/searxng/searxng
- opencli（A CLI for social media & web platforms — smart-search skill 借鉴了其搜索 URL 模式与平台适配方案） https://github.com/jackwener/opencli
- 文颜(Markdown文章排版美化工具，支持微信公众号、今日头条、知乎等平台。) https://github.com/caol64/wenyan
- Everything Claude Code（Claude Code 全局 skill / rule / agent 集合，wiseflow 的 complex-task 等编排 skill 借鉴了其 blueprint 和 gan-style-harness 的设计思路） https://github.com/affaan-m/everything-claude-code
- awesome-design-md（A curated collection of design systems in markdown format — Designer 内置设计系统库参考了此项目的设计系统结构） https://github.com/VoltAgent/awesome-design-md
- videocut-skills（视频去口误/精剪技能集 — `de-mouth` 技能原汁原味借鉴其口误检测与剪映草稿生成能力） https://github.com/Ceeon/videocut-skills
- cheat-on-content（自媒体打分算法借鉴） https://github.com/XBuilderLAB/cheat-on-content

## Citation

如果您在相关工作中参考或引用了本项目的部分或全部，请注明如下信息：

```
Author：Wiseflow Team
https://github.com/TeamWiseFlow/wiseflow
```

![star](https://atomgit.com/wiseflow/wiseflow/star/badge.svg) 国内托管地址：[https://atomgit.com/wiseflow/wiseflow](https://atomgit.com/wiseflow/wiseflow)

## 友情链接

[<img src="https://github.com/TeamWiseFlow/wiseflow/raw/4.x/docs/logos/tianqibao.png" alt="tianqibao" height="60">](https://baotianqi.cn/)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[<img src="https://resource.aihubmix.com/logo.png" alt="aihubmix" height="60">](https://aihubmix.com/?aff=Gp54)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[<img src="https://github.com/TeamWiseFlow/wiseflow/raw/4.x/docs/logos/SiliconFlow.png" alt="siliconflow" height="40">](https://cloud.siliconflow.cn/i/WNLYbBpi)
