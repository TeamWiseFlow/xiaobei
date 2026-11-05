## 测试文件布局

- 回归测试与测试夹具统一放在仓根 `test/`，按组件分目录；不要放在正式脚本或 skill 目录中。
- 移动测试时同步更新导入路径、测试入口与运行说明；确认已无用途的测试可以删除。
- 用于修改上游测试的补丁材料仍放在对应 `patches/` 补丁包内。

## 平台能力归属

- `expert-douyin` / `expert-xhs` / `expert-tiktok` / `expert-kuaishou` / `expert-twitter` 仅保留创作、发布、本人已发布作品数据获取和创作者服务；私信、评论发布/回复、点赞、收藏、关注等写操作及直播互动统一放在 `expert-bd`。
- 内容搜索、账号与作品获取、评论读取、评论/@提醒、点赞收藏提醒、新增关注通知和媒体下载使用一级技能 `douyin-hunter` / `xhs-hunter` / `tiktok-hunter` / `kuaishou-hunter` / `x-hunter` / `weibo-hunter`，不要收纳进平台专家包。缺少已实现接口的互动写能力保留为不支持，待后续有可复用方案再补齐。
- `viral-chaser` 只编排视频分析：先调用对应 hunter 获取资料与下载，再运行本地 analyzer 做转写和关键帧提取。analyzer 不集成探活、登录、链接解析或下载；快手、TikTok、X 和微博同样通过各自 hunter 执行；不支持 B 站链接。图文下载调用 hunter，分析由对应平台专家 workflow 完成。
- 公共 `smart-search` 专用于 Camoufox 浏览器搜索。当前 crew 已配置 `douyin-hunter` / `xhs-hunter` / `tiktok-hunter` / `kuaishou-hunter` / `x-hunter` / `weibo-hunter` / `wx-mp-hunter` 且任务命中其能力时优先使用；这些技能目前仅 main 配置，未配置的 crew 按已有站点浏览器规则或公开索引搜索，不调用不可用技能，不因采集技能失败就自动绕行。普通站点统一复用持久化 `default` session/profile，不按站点或类别另建 profile；自媒体专用 profile 和 API 会话按各技能实际登录约定执行；微信视频号仍没有搜索与取内容方案。
- `published-track` 只管理发布记录、查询和指标入库，不负责平台取数；具体取数全部放在对应专家包的 engagement tool，工具采集后调用 `published-track update-metrics`。
- 后续能力移植和新增平台均按此划分。抖音发布使用 Camoufox 持久化 session `douyin`；本人取数走 HTTP 接口，仅临时从同一 profile 读取 cookie/UA，不另存登录态、不走 login-manager。hunter 和 expert-bd 互动使用独立 API 登录态。
- TikTok、快手、X、微博共用 `platform-runtime` 内部运行库；登录与会话管理归运行库，由各自 hunter 暴露登录命令，不另设 `login-manager` 技能。安装时按固定四平台配置裁剪其他平台及专属依赖，不改保留平台的业务或签名代码；上游版本、包校验值、注册结构变化必须复核后再升级。

- main 的 `expert-osbi` 负责公开信息提取、跟踪、分析与市场研究，`expert-bd` 保留 Lead Hunting，负责潜客探索筛选、互动和联络；邮件联络使用公共 `email-ops`。原始资料获取按平台调用 `douyin-hunter` / `xhs-hunter` / `tiktok-hunter` / `kuaishou-hunter` / `x-hunter` / `weibo-hunter` / `wx-mp-hunter` 或公共 `smart-search`；公开直播读取与监听使用 `douyin-hunter live` / `xhs-hunter live` / `tiktok-hunter live` / `kuaishou-hunter live`，直播写操作归 BD；通用 RSS/Atom 解析和情报记录工具归 OSBI。技能操作指导必须写出具体技能名，不用“使用一级 hunter”等泛称代替。

- Awada 对用户和所有 crew（含 IT engineer）只暴露统一账号、动作和产品范围内的业务能力合集；登录设备、客户端指令/维护、历史诊断、回调扩展、通信加密和原消息转发不属于客户端接口；原生转写自动完成，手动仅提供一个转写命令；同一业务能力只保留一个公开命令和统一参数，不能仅删除前缀后保留同义动作。底层实现仅留在插件内部适配。工具说明、配置指导和技术元数据不得要求识别或选择底层平台；客户端不按账号裁剪能力或预判动作支持，兼容与执行限制由 Awada server 处理。

## Docker 部署规范

- 用户态镜像、Compose service 和持久卷统一使用 **xiaobei** 命名；不得新增 `wiseflow-*` 镜像或卷名。
- 运行态只持久化 `/root/.openclaw` 和 `/root/.camoufox-cli`。入口脚本必须从镜像 seed 初始化空卷，且不得覆盖已有用户状态。
- Gateway/noVNC 默认只绑定 `127.0.0.1`，不得默认公开无密码 noVNC。

## Crew Template 开发规范

创建或修改 crew template（`crews/` 下的任何 crew）时，必须遵循 `docs/workspace-bootstrap-files.md` 中定义的文件职责划分：

- **AGENTS.md**：工作流程、决策树、操作步骤；本机环境备忘统一放在其中的 `## Tools` 节
- **SOUL.md**：角色定义、价值观、行为边界
- **IDENTITY.md**：名字、形象类型、性格基调、emoji、头像——仅此四项，不写工作职责或能力清单
- **Tools 节**：脚本路径、环境变量名称、工具别名等本机备忘；不保存密钥值，不重复 SKILL.md 操作手册。OpenClaw 2026.10.4 已退役独立 `TOOLS.md`，模板和安装脚本不得重新生成；旧文件由用户升级后手动删除，setup 不迁移或清理
- **MEMORY.md**：跨会话需保留的背景知识（产品手册、用户偏好、历史记录）——不写工具使用规范
- **HEARTBEAT.md**：已退役，不再提供模板或部署；旧文件由用户升级后手动删除，实际周期任务由原生 Automation / 心跳 scratch 管理
- **BOOTSTRAP.md**：一次性首次运行引导，完成后删除
- **USER.md**：服务对象信息

- internal crew 模板不写 `### Python 环境`；该段由统一提示生成器在每次 setup 时清理旧区块并重建到 AGENTS.md 的 `## Tools` 节末尾，路径按实际部署生成，其他本机备注保留。`workspace-guides.py` 内的提示统一按标题删除旧段落后重写，保留段落外的用户正文，不做已有标题即跳过或逐条对齐。
- external crew 的 AGENTS.md 模板必须直接包含完整操作规范，明确禁止自行创建、修改或执行 Python 脚本；缺少能力或需要编程时写入本工作区 `feedback/YYYY-MM-DD.md`。安装与升级脚本不向 external crew 自动注入提示，不要求其 spawn 未配置的 IT Engineer；已部署实例的自定义正文保持不变。

## 创建/更新 skill 时，如果涉及到脚本或者 cli 指导内容，必须遵从以下原则：
- 1、多步骤操作且涉及中间态保存的（下一步操作的某一输入为上一步返回结果），哪怕每一步都只是一条命令，也必须做脚本！
- 2、涉及多分支选择，且分支选择依靠明确变量的（如环境变量中是否有某个值，或者按某个入参的值判断分支）应该优先用脚本。
- 3、涉及 python 的，必须制作脚本，最终以 “python /path/to/script.py” 的模式调用。
- 4、skill 目前已经全面实施wrapper模式，规避agent自行拼接路径带来的潜在错误风险，具体见 `docs/docker-distribution.md`
- 5、skill 需要的常量（如各种 ID、KEY 等），搭配脚本时优先使用环境变量，搭配 SKILL.md 时优先使用同级目录下的 json 配置。

本代码仓的 skill 是给 openclaw 使用的，以上原则是为了适配 openclaw 的规则。

## SKILL.md frontmatter 书写规范

openclaw 实际识别的 frontmatter 字段（参见 `openclaw/src/agents/skills/frontmatter.ts`）：

- 顶层：`name`、`description`（**必需**）、`user-invocable`（默认 true）、`disable-model-invocation`（默认 false）
- `metadata.openclaw.*`（可选）：`emoji`、`homepage`、`skillKey`、`primaryEnv`、`os`、`requires`、`install`、`always`

其他字段（如 claude code 的 `argument-hint`、`allowed-tools`、`license`）会被静默忽略。

**写法用 YAML block style**，不要用 flow style（嵌套花括号 + 引号）。openclaw bundled 技能和官方文档均采用 block style：

```yaml
---
name: browser-guide
description: Best practices for using the managed browser ...
---
```

**注意事项**：

- `always: true` 的真实语义是"跳过 `requires` 二进制/env 检查直接判定 eligible"（见 `config-eval.ts:124`），**不是**"强制注入整个 SKILL.md"。如果 skill 没声明 `requires`，加 `always: true` 等于无意义，应删除。
- 加载阶段 openclaw 只把 `name` + `description` + SKILL.md 绝对路径塞进 system prompt 的 `<available_skills>` 块；agent 用到时才主动 read 全文。所以 frontmatter 写得再多也不会污染 system prompt，但反过来也意味着——除上述识别字段外，多余字段不会带来任何运行时收益。

## SKILL.md 内容书写规范

SKILL.md 是写给**执行时的智能体**看的操作手册，不是开发日志。内容只写指导性指令、正例、反例：

- ✅ 直接写"应该怎么做""不要怎么做"，配 ✅ 正例 / ❌ 反例
- ❌ 不写排查故事、历史往来、开发经历、思路背景、踩坑全过程
- 经验教训要提炼成一条可执行的规则，而不是一段叙事

## skill 依赖打包规则

产品拆分后（D8）addons/ 结构已销毁，skill 只有两层：

- **公共 skill**：`skills/<name>/`（≥2 crew 共用，部署到 `~/.openclaw/skills/`）
- **crew 专属 skill**：`crews/<crew-id>/skills/<name>/`

涉及依赖包（python/node/go）的 skill，依赖统一在仓根 `requirements.txt` / `package.json` 声明，由 `scripts/install.sh` 一次性安装。不允许单独把某个 skill 配置成独立包。这样部署时自动完成初始化，降低部署工作和风险。务必遵守！

### Python 依赖

在仓根 `requirements.txt` 声明。源码、预构建包和 Docker 统一调用 `scripts/python-runtime.mjs`，使用项目锁定的 CPython 与 `tools/python` 共享 venv；扫描公共技能、crew 技能及仓根依赖，合并去重后由该解释器安装。依赖标记归 venv，解释器或依赖变化时重建，不使用系统/用户级 pip、`--user` 或 `--break-system-packages`。agent 默认解释器通过原生 `tools.exec.pathPrepend` 接入；Python Tools 指导仅给 internal crew，不扩大 sales-cs 等 external crew 的权限。

### Node 依赖

每个用到外部 npm 包的 skill，**在自己目录下放一个 `package.json`** 声明 `dependencies`（`type: "module"` 若脚本用 ESM）。`scripts/apply-addons.sh` 扫描所有含 `SKILL.md + package.json` 的 skill 目录，per-skill `npm install --omit=dev`，`node_modules` 落在仓内 skill 目录（`.gitignore` 已覆盖）。内容哈希守卫，`package.json` 变了才重装。

**不要**把 skill 的 Node 依赖写进仓根 `package.json`——`apply-addons.sh` 的 per-skill 扫描不读仓根 `package.json` 的 deps，写进去也不会被装。仓根 `package.json` 只管 `packageManager` 字段。

**判断 skill 是否需要 `package.json`**：扫 skill 下所有 `.ts`/`.js`/`.mjs` 的 `import ... from "X"`，过滤掉 `node:` 内置和相对路径，若还有残留（如 `cheerio`、`rss-parser`），就需要。只用 Node 内置模块或相对 import，不需要 `package.json`。

### Playwright 与 Chromium 共用

- 所有技能共用 `browser/package.json` 锁定的 `playwright-core`，仅安装到 `browser/node_modules`；技能不得另声明 `playwright` / `playwright-core` / `@playwright/test`，不得安装 Python Playwright。
- Chromium headless shell 由 `scripts/install-playwright.mjs` 在安装/升级时预装，唯一缓存是 `browser/.browsers`；不要在技能内下载、回退系统 Chrome 或另建浏览器缓存。
- Node 使用 `browser/scripts/shared-playwright.mjs`，Python 使用 `browser/bridge/shared_playwright.py`；缺依赖交统一安装器修复，技能执行时不临时下载。平台会话与网页浏览仍走 xiaobei-browser/Camoufox。
