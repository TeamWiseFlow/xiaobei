# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

Codex 被授权在本仓库中执行任何 git 命令（包括 push、branch、tag 等），无需逐次确认。

## Crew Template 开发规范

创建或修改 crew template（`crews/` 下的任何 crew）时，必须遵循 `docs/workspace-bootstrap-files.md` 中定义的文件职责划分：

- **AGENTS.md**：工作流程、决策树、操作步骤
- **SOUL.md**：角色定义、价值观、行为边界
- **IDENTITY.md**：名字、形象类型、性格基调、emoji、头像——仅此四项，不写工作职责或能力清单
- **TOOLS.md**：本机环境备忘（脚本路径、环境变量、工具别名）——不写工作流程，不重复 SKILL.md 内容
- **MEMORY.md**：跨会话需保留的背景知识（产品手册、用户偏好、历史记录）——不写工具使用规范
- **HEARTBEAT.md**：周期性巡检任务清单，保持短小
- **BOOTSTRAP.md**：一次性首次运行引导，完成后删除
- **USER.md**：服务对象信息

## 创建/更新 skill 时，如果涉及到脚本或者 cli 指导内容，必须遵从以下原则：
- 1、多步骤操作且涉及中间态保存的（下一步操作的某一输入为上一步返回结果），哪怕每一步都只是一条命令，也必须做脚本！
- 2、涉及多分支选择，且分支选择依靠明确变量的（如环境变量中是否有某个值，或者按某个入参的值判断分支）应该优先用脚本。
- 3、涉及 python 的，必须制作脚本，最终以 “python /path/to/script.py” 的模式调用。
- 4、**crew 专属 skill**（`crews/<crew-id>/skills/` 下的 skill）如果包含脚本，SKILL.md 中对脚本调用的路径必须使用**绝对路径**写法，即 `python3 /<workspace 绝对路径>/skills/<skill-name>/scripts/<file>` 或 `/<workspace 绝对路径>/skills/<skill-name>/scripts/<file>`。**禁止** `cd <path> && python3 ...` 复合调用、**禁止** `bash <script>` 前缀、**禁止**工作区相对路径 `./skills/...`（实测相对路径 agent 容易误拼 CWD 或误加 `cd`/`bash` 前缀导致 allowlist miss，绝对路径最稳）。

原因：openclaw exec allowlist 按命令前缀匹配，`cd` / `bash` 不在 allowlist 中；agent 的 exec 虽从 workspace CWD 执行，但实测相对路径 `./skills/...` 经常被 agent 误拼或误加前缀，直接用绝对路径最稳。注入到 TOOLS.md 的「exec 命令规范」由 `scripts/lib/agent-skills.sh` 在 setup-crew 时用真实 workspace 绝对路径渲染。

**全局 skill**（`skills/` 目录下，部署到 `~/.openclaw/skills/`）同样优先用绝对路径。openclaw 加载 skill 时会注入 `References are relative to <skill绝对路径>` 提示，agent 据此将 `./scripts/xxx.sh` 解析为绝对路径，该机制可用但仍推荐直接写绝对路径。**不得**使用 `{baseDir}`——这是旧写法，模型经常无法正确推断 `{baseDir}` 的值而误用工作区相对路径。

- 5、skill 需要的常量（如各种 ID、KEY 等），搭配脚本时优先使用环境变量，搭配 SKILL.md 时优先使用同级目录下的 json 配置。

本代码仓的 skill 是给 openclaw 使用的，以上原则是为了适配 openclaw 的规则。

## SKILL.md frontmatter 书写规范

openclaw 实际识别的 frontmatter 字段（参见 `openclaw/src/agents/skills/frontmatter.ts`）：

- 顶层：`name`、`description`（**必需**）、`user-invocable`（默认 true）、`disable-model-invocation`（默认 false）
- `metadata.openclaw.*`：`emoji`、`homepage`、`skillKey`、`primaryEnv`、`os`、`requires`、`install`、`always`

其他字段（如 Codex 的 `argument-hint`、`allowed-tools`、`license`）会被静默忽略。

**写法用 YAML block style**，不要用 flow style（嵌套花括号 + 引号）。openclaw bundled 技能和官方文档均采用 block style：

```yaml
---
name: browser-guide
description: Best practices for using the managed browser ...
metadata:
  openclaw:
    emoji: 🌐
    always: true
---
```

**注意事项**：

- `always: true` 的真实语义是"跳过 `requires` 二进制/env 检查直接判定 eligible"（见 `config-eval.ts:124`），**不是**"强制注入整个 SKILL.md"。如果 skill 没声明 `requires`，加 `always: true` 等于无意义，应删除。
- 加载阶段 openclaw 只把 `name` + `description` + SKILL.md 绝对路径塞进 system prompt 的 `<available_skills>` 块；agent 用到时才主动 read 全文。所以 frontmatter 写得再多也不会污染 system prompt，但反过来也意味着——除上述识别字段外，多余字段不会带来任何运行时收益。

## skill 依赖打包规则

产品拆分后（D8）addons/ 结构已销毁，skill 只有两层：

- **公共 skill**：`skills/<name>/`（≥2 crew 共用，部署到 `~/.openclaw/skills/`）
- **crew 专属 skill**：`crews/<crew-id>/skills/<name>/`

涉及依赖包（python/node/go）的 skill，依赖统一在仓根 `requirements.txt` / `package.json` 声明，由 `scripts/install.sh` 一次性安装。不允许单独把某个 skill 配置成独立包。这样部署时自动完成初始化，降低部署工作和风险。务必遵守！

### Python 依赖

在仓根 `requirements.txt` 声明。`scripts/apply-addons.sh` 扫描 `skills/`、`crews/*/skills/`、仓根下所有 `requirements.txt`，合并去重后 `pip install --user`。内容哈希守卫，依赖集变化才重装。

### Node 依赖

每个用到外部 npm 包的 skill，**在自己目录下放一个 `package.json`** 声明 `dependencies`（`type: "module"` 若脚本用 ESM）。`scripts/apply-addons.sh` 扫描所有含 `SKILL.md + package.json` 的 skill 目录，per-skill `npm install --omit=dev`，`node_modules` 落在仓内 skill 目录（`.gitignore` 已覆盖）。内容哈希守卫，`package.json` 变了才重装。

**不要**把 skill 的 Node 依赖写进仓根 `package.json`——`apply-addons.sh` 的 per-skill 扫描不读仓根 `package.json` 的 deps，写进去也不会被装。仓根 `package.json` 只管 `packageManager` 字段。

**判断 skill 是否需要 `package.json`**：扫 skill 下所有 `.ts`/`.js`/`.mjs` 的 `import ... from "X"`，过滤掉 `node:` 内置和相对路径，若还有残留（如 `cheerio`、`rss-parser`），就需要。现状（2026-07-12 扫描）：

| skill | 外部 npm 依赖 | 有 package.json |
|-------|--------------|----------------|
| `crews/main/skills/wx-mp-hunter` | `cheerio` | ✅ |
| `crews/main/skills/rss-reader` | `rss-parser` | ✅ |

其余 skill 的脚本只用 Node 内置模块或相对 import，不需要 `package.json`。
