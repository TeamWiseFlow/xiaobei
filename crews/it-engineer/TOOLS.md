# IT Engineer Agent — Tools

### 运行环境铁律：OpenClaw 控制面操作 **一律走 MCP 工具**，不跳 CLI

直接使用CLI会触发写运行中 Gateway 共享的 `dist/`，极端情况下导致系统崩坏。

**铁律**：生产 Gateway 运行中，以下操作全部走 MCP 工具，**不允许走 `pnpm openclaw` / `node dist/index.js` 任何 CLI 入口**：

| 需求 | 工具 |
|------|------|
| cron 查询 / 增删改 / 运行历史 / 手动触发 | `cron` MCP 工具 |
| config 查询 / 修改 / 应用 / 重启 Gateway | `gateway` MCP 工具 |
| 会话 查询 / 历史 / 状态 / 送信 / spawn | `sessions_list` / `sessions_history` / `session_status` / `sessions_send` / `sessions_spawn` |
| 节点 / 文件传输 / 调用 | `nodes` / `file_fetch` / `file_write` / `dir_list` / `dir_fetch` |
| 技能架库 增删改查 | `skill_workshop` |

看起来“只读”的 `pnpm openclaw cron list / cron show / cron runs / config get` 同样会触发 build，**同样是雷区**。

### GitHub / 代码相关（需已启用 github、gh-issues、coding-agent 技能）
- `github`：读取 xiaobei 和 OpenClaw 仓库的最新信息（commits、releases、README）
- `gh-issues`：查看 xiaobei 和 OpenClaw 的 issue，了解已知问题和修复状态
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
2. **日志是第一线索**：遇到问题先查日志，再猜原因
3. **验证结果**：每次操作后确认效果（如重启后检查服务是否正常运行）

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