# 小贝 5.8.2 的 OpenClaw 插件

小贝基于 OpenClaw Gateway Extended Stable **2026.10.33**，随包提供下列 **50 个插件**。源码安装、预构建包和 Docker 共用 [发行清单](../config-templates/openclaw-plugins.json)。编译保留 Gateway、Plugin SDK 和 Control UI，另保留无插件清单的图像生成公共模块 `image-generation-core`。

源码安装仍检出完整的上游 Git 源码。小贝按清单安装依赖、编译插件并从成品目录加载。核心 Worker 仍需要上游 `browser` 工作区提供部分编译依赖。预构建包和 Docker 运行层只带保留插件的源码目录。安装使用上游锁定的依赖版本。

个人微信、企业微信、Awada 和 `xiaobei-browser` 由小贝各自的安装入口管理。公共技能 `smart-search` 和其他工作区技能照常提供。

## 记忆、触发与执行

| 插件 ID | 小贝默认 | 功能和适合启用的场景 |
| --- | --- | --- |
| `memory-core` | 开启 | OpenClaw 的默认记忆引擎，负责工作区记忆的检索。建议常开。小贝模板默认不选向量服务，需要语义检索时再配置嵌入后端。 |
| `tokenjuice` | 仅 IT Engineer 试用 | 在长 `exec` / `bash` 输出进入模型上下文前进行压缩，无额外 Key。适合频繁查日志和仓库的 crew。小贝通过 `plugins.entries.tokenjuice.config.agentIds` 指定试用 crew，默认仅包含 `it-engineer`。 |
| `active-memory` | 关闭 | 在符合条件的回复前主动检索已有记忆。适合经常依赖跨会话偏好和项目历史的私人 crew，启用后先观察召回质量和轮次成本。 |
| `mcp-events` | 关闭 | 订阅已配置的 MCP 事件源并触发 OpenClaw Automations。适合由外部服务通知 crew 的流程，需支持 Events 的 MCP 服务、该服务的鉴权和公开 HTTPS 回调入口。 |
| `memory-wiki` | 关闭 | 将来源、结论及证据关系整理成可检索的本地 Wiki，可用 Obsidian 查看。适合长期跟踪同一批公司、竞品和主题，无独立 Key，需要初始化资料库并持续维护。 |
| `cua-computer` | 关闭 | 在配对的桌面节点上执行受权限控制的计算机操作。适合必须使用原生桌面应用的任务，需要兼容驱动和系统授权。 |
| `imap` | 关闭 | 监听 IMAP 邮箱，用满足条件的来信触发隔离的 agent 会话。适合工单、询价等邮件触发流程，需要邮箱凭据及来源验证配置。 |

在 `plugins.entries.<插件 ID>.enabled` 中可覆盖小贝默认值。升级时补齐缺失的开关和 Tokenjuice 试用范围，保留已有的显式设置。第三方服务的账号、Key 或权限仍需按各自接入说明配置。运行时的 Kimi 插件 ID 是 `kimi`，发行目录为 `kimi-coding`。

本版建议让 `memory-wiki` 保持关闭。日常偏好和工作记录继续由 `memory-core` 和工作区 Markdown 承担。等 OSBI 有跨周复用的信源、可复查的竞品结论和持续修订需求时，可以选一个 crew 试用。小贝的多 crew 场景建议先用按 agent 隔离的 vault。 [OpenClaw Memory Wiki 指南](https://docs.openclaw.ai/plugins/memory-wiki)

下一版本的 OSBI 待评估项是本地定时生成日报、周报，并由对应 crew 主动推送。先验证原生 Automations 能否完成定时与投递。有独立服务需要在产出完成后通知 Gateway 时，再评估使用 MCP Events 作为事件入口。本版提供插件。 [OpenClaw MCP Events 指南](https://docs.openclaw.ai/automation/mcp-events)

## 消息渠道

| 插件 ID | 功能和适合启用的场景 |
| --- | --- |
| `discord` | Discord 频道、私信和语音协作。用于已有 Discord 服务器的团队，需 bot 配置。 |
| `feishu` | 飞书/Lark 消息及授权的办公工具。用于在飞书内与 crew 协作，需应用凭据和权限。 |
| `slack` | Slack 消息、线程和应用事件。用于已有 Slack 工作区的团队，需 Slack App。 |
| `telegram` | Telegram 私信和群聊。用于 Telegram 通知及交互，需 BotFather Token。 |
| `whatsapp` | WhatsApp Web 会话。用于 WhatsApp 消息，需扫码关联设备。 |
| `x` | X 上的受限提及处理与公开回复。用于明确授权的社交渠道，需 X API 授权及允许名单。 |

## 模型与推理服务

为拥有相应账号、订阅或本地实例的用户启用。云服务通常需要 API Key 或 OAuth。也可继续在 OpenClaw 配置中使用自定义 API 端点。

| 插件 ID | 功能和适合启用的场景 |
| --- | --- |
| `anthropic` | Claude API 和受支持的 Claude CLI 接入。已有 Anthropic 账号时使用。 |
| `anthropic-vertex` | Google Vertex AI 上的 Claude。已有 GCP 项目、区域和 Vertex 权限时使用。 |
| `cloudflare-ai-gateway` | 经 Cloudflare AI Gateway 转发模型调用。已有网关且集中管理鉴权和用量时使用。 |
| `deepseek` | DeepSeek 官方推理端点。用于已开通的 DeepSeek 通用或推理模型。 |
| `fireworks` | Fireworks 托管模型。已有 Fireworks 项目或模型部署时使用。 |
| `github-copilot` | GitHub Copilot 模型入口。已有 Copilot 权益时授权使用。 |
| `google` | Gemini / Google AI 及 Vertex AI 接入。已有 Google AI 或 GCP 项目时使用。 |
| `groq` | Groq 推理及媒体理解。使用 Groq 托管模型或语音转写时启用。 |
| `huggingface` | Hugging Face 推理 API。通过 Hugging Face 调用所选模型时使用。 |
| `kimi-coding` | Kimi Coding 接入。已有 Kimi Coding 权益时使用。 |
| `longcat` | LongCat 模型。已有 LongCat API 额度时使用。 |
| `minimax` | MiniMax API 和 OAuth 接入。已有 MiniMax API 额度或授权权益时使用。 |
| `mistral` | Mistral API。使用 Mistral 模型或其平台能力时启用。 |
| `moonshot` | Moonshot API。已有 Moonshot 平台额度并使用 Kimi 模型时启用。 |
| `nvidia` | NVIDIA 托管推理。通过 NVIDIA 模型目录或相应端点调用时使用。 |
| `ollama` | 连接 Ollama 实例。适合本地推理，需先启动服务并准备模型。 |
| `openai` | OpenAI 模型和受支持的 API 能力。使用 OpenAI 账号或端点时启用。 |
| `opencode` | OpenCode Zen 模型接入。已有 Zen 账号时使用。 |
| `opencode-go` | OpenCode Go 模型接入。已有 Go 订阅时使用。 |
| `openrouter` | 聚合多个模型提供商。需要在一个账号下切换多个厂商模型时使用。 |
| `qianfan` | 百度智能云千帆平台。已有千帆项目和推理额度时使用。 |
| `qwen` | Qwen Cloud 模型。已有相应平台账号和推理额度时使用。 |
| `stepfun` | 阶跃星辰服务。已有 StepFun 模型额度时使用。 |
| `tencent` | 腾讯云 TokenHub 和 Token Plan。已有相应平台权益时使用。 |
| `together` | Together AI 托管推理。已有 Together AI 模型额度时使用。 |
| `volcengine` | 火山引擎模型及语音服务。已有火山方舟或相应语音服务配置时使用。 |
| `xai` | xAI 模型和相关媒体能力。需要调用 Grok 时启用，小贝模板默认关闭该插件。 |
| `xiaomi` | 小米 MiMo 接入。已有 MiMo API 额度时使用。 |
| `zai` | Z.AI / GLM 模型。已有相应 API 或 Coding Plan 权益时使用。 |

## 文档、语音和会议

| 插件 ID | 功能和适合启用的场景 |
| --- | --- |
| `azure-speech` | Azure Speech 文字转语音。用于语音文件、语音消息和电话，需 Azure Speech Key 和区域。 |
| `document-extract` | 本地提取附件文本，必要时生成页面图片。适合 PDF 等文档处理，无独立 Key。 |
| `fish-audio-speech` | Fish Audio 托管语音合成。需要 Fish Audio 声音及流式输出时使用，需 API Key。 |
| `microsoft` | Microsoft Edge TTS。用于通用文字转语音，通过 Edge 在线服务生成，常规用法无需 Azure Key。 |
| `github` | 公开 GitHub 链接预览与文档读取。用于阅读公开仓库资料，无需单独配置 Key。 |
| `web-readability` | 从已经获取的 HTML 提取正文。用于文章和资料读取，无独立 Key。 |
| `voice-call` | 通过 Twilio、Telnyx 或 Plivo 拨打、接听电话。需号码、服务凭据和回调配置。 |
| `zoom-meetings` | 以 Chrome 浏览器访客身份加入 Zoom 会议。小贝模板默认关闭。启用后需使用已配对的 OpenClaw 节点，该节点须支持 `zoommeetings.chrome` 和原生 `browser.proxy`，并具备所选模式需要的音频设备。小贝的本机 Camoufox 不提供此接口。 |

## 裁剪范围

上游常规源码构建中有 117 个插件未随小贝提供。它们的发行目录 ID 如下。

```text
a2a acpx admin-http-rpc advisor agentsapi alibaba amazon-bedrock amazon-bedrock-mantle
apple-fm arcee baseten beam bonjour brave browser buzz byteplus canvas cerebras chutes
clawrouter clickclack cloudflare code-mode-quickjs codex cohere comfy copilot copilot-proxy
crabbox deepgram deepinfra device-pair diagnostics-otel diagnostics-prometheus diffs
diffs-language-pack duckduckgo elevenlabs exa facetime fal featherless file-transfer firecrawl
geolocation gmi google-meet googlechat gradium imessage inworld irc kie kilocode line linux-node
litellm llama-cpp llm-task lmstudio lobster logbook matrix mattermost mcp-relay memory-lancedb
meta microsoft-foundry migrate-claude migrate-hermes msteams muse mxc nextcloud-talk nostr novita
oc-path onepassword onnx openshell parallel particle perplexity pixverse policy radius raft reef
runway searxng senseaudio session-share sglang signal slack-huddles sms synology-chat synthetic
talk-voice tavily team-reports teams-meetings tlon tts-local-cli twitch typesafe vault venice
vercel-ai-gateway visitor-access vllm voyage vydra workboard zalo zalouser
```

`qa-channel` 与 `qa-lab` 是上游私有 QA 构建项，也未随包提供。通用搜索继续由 `smart-search` 提供。
