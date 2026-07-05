# IT Engineer Agent — Tools

## 可用工具

### 通用工具
- 文件读写：读取日志、配置文件，修改 workspace 文件
- Shell 执行：运行系统命令、检查状态、查看日志

### WiseFlow 内置脚本（需先 cd 到 WiseFlow 项目目录再执行）

> WiseFlow 项目路径见同目录的 `OFB_ENV.md`（历史命名保留，每次 `setup-crew.sh` 自动更新，里面有完整命令）。

```bash
# 开发模式前台启动（含日志输出）
cd <WISEFLOW_PROJECT_ROOT> && ./scripts/dev.sh gateway

# 生产模式重新安装后台服务
cd <WISEFLOW_PROJECT_ROOT> && ./scripts/reinstall-daemon.sh

# 重新同步 crew 配置（幂等，安全执行）
cd <WISEFLOW_PROJECT_ROOT> && ./scripts/setup-crew.sh

# 重新应用 addons
cd <WISEFLOW_PROJECT_ROOT> && ./scripts/apply-addons.sh
```

> ⚠️ **生产 Gateway 运行中不得调用 `pnpm openclaw <subcommand>`**。`pnpm openclaw` 入口在 npm script 里绑了 “每次先 build”，这个 build 会占 CPU、写运行中 Gateway 共享的 `dist/`，多次连续调用可能令系统崩坏（2026-06-29 发生过两次，详见 MEMORY.md）。包括看起来“只读”的 `cron list / cron show / cron runs / config get` 都是高风险雷区。
>
> 所有 cron / config / sessions / status 类的查询与增删改，全部走 MCP 工具：
>
> | 需求 | 用什么 |
> |------|--------|
> | cron 查询 / 增删改 / 运行历史 | `cron` MCP 工具，`action` 支持 list/get/add/update/remove/run/runs |
> | config 查询 / 修改 / 应用 / 重启 | `gateway` MCP 工具，`action` 支持 config.get/config.patch/config.apply/restart |
> | 会话查询 / 历史 / 状态 | `sessions_list` / `sessions_history` / `session_status` |
> | 节点 / 文件传输 / 接口调用 | `nodes` / `file_fetch` / `file_write` / `dir_list` / `dir_fetch` |
>
> 上游 OpenClaw CLI 仅在开发机、升级后首次迁移、或研发手动排查时使用；IT Engineer 在运行环境 **不主动** 调用。如果确实需要，须提前与用户确认 Gateway 可接受崩溃重启。

### GitHub / 代码相关（需已启用 github、gh-issues、coding-agent 技能）
- `github`：读取 WiseFlow 和 OpenClaw 仓库的最新信息（commits、releases、README）
- `gh-issues`：查看 WiseFlow 和 OpenClaw 的 issue，了解已知问题和修复状态
- `coding-agent`：用于分析代码问题、生成配置文件、解读报错信息

### 腾讯云管理（需已启用 tccli 技能）
- `tccli`：腾讯云命令行工具速查，管理 CVM、Lighthouse、VPC、SSL、DNSPod 等云资源
  - 前置条件：已安装 `tccli`（`pip3 install tccli`）并配置密钥
  - 用途：查看实例状态、启停服务器、管理域名解析、证书部署、安全组配置等

### 阿里云 Skills 搜索（需已启用 alicloud-find-skills 技能）
- `alicloud-find-skills`：搜索、发现和安装阿里云官方 Agent Skills
  - 前置条件：已安装 `aliyun` CLI（>= 3.3.3）并配置认证凭据
  - 用途：按意图/关键词搜索阿里云 skill、浏览类目、查看 skill 详情、安装 skill
  - 安全：仅使用只读 API（ListCategories / SearchSkills / GetSkillContent），不暴露 AK/SK

## 工具使用规则

1. **备份重要文件**：修改 `~/.openclaw/openclaw.json` 前，先备份
2. **脚本优先**：优先使用 WiseFlow 内置脚本，不要直接操作 `openclaw/` 目录下的代码
3. **日志是第一线索**：遇到问题先查日志，再猜原因
4. **验证结果**：每次操作后确认效果（如重启后检查服务是否正常运行）

## SEO 技术工具

```
# Lighthouse 性能/SEO 评分（需要 Chrome）
npx lighthouse https://yoursite.com --only-categories=performance,seo --output json

# sitemap 验证（检查格式和可访问性）
curl -sf https://yoursite.com/sitemap.xml | python3 -c "import sys; import xml.etree.ElementTree as ET; ET.parse(sys.stdin); print('✅ sitemap valid')"

# robots.txt 检查
curl -sf https://yoursite.com/robots.txt

# 内链/外链状态检测（使用 xurl 技能或 curl 批量检查）
curl -o /dev/null -s -w "%{http_code}" https://yoursite.com/some-page

# Google Search Console（通过浏览器访问，或使用 GSC API）
# API 文档：https://developers.google.com/webmaster-tools/v1/api_reference_index
```

| 工具 | 用途 |
|------|------|
| `smart-search` | 搜索 SEO 最佳实践、查找竞品技术方案 |
| `coding-agent` | 生成 sitemap.xml、JSON-LD Schema、robots.txt 内容 |