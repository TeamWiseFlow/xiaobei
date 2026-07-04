# 上游 catchup 评估报告（2026-07-04）

> 整合 `~/.claude/projects/-home-wukong-wiseflow/memory/02-upstream-sources.md` 6 个上游的最新进展。
> **评估日期**：2026-07-04
> **本仓 master HEAD**：92d... 实际为 `5e7be4a` 后续 → 见 git log（dev session commit 头）
> **本轮决策**：本机实例不动 + 部署后统一处理；上游 catchup **强烈建议升级 openclaw v6.10 → v6.11**

## 一、6 个上游 catchup 总览

| # | 上游 | 本仓 catchup | 上游 HEAD | 间隔 | catch? | 优先级 |
|---|------|------------|----------|------|-------|--------|
| 1 | openclaw/openclaw | aa69b12d (v2026.6.10) | 3706c2b3bd (v2026.6.11 release + 持续开发) | 1 release (4 天) | **强烈建议** | P0 |
| 2 | Kaliiiiiiiiii-Vinyzu/patchright | v1.60.2 | v1.60.2 (PyPI 2026-06-29) | 一致 | **不** | — |
| 3 | jackwener/OpenCLI | 8ed8ca26 (2026-06-13) | v1.0.21 (2026-07-03) | 持续活跃 | **仅观察** | P3 |
| 4 | yikart/AiToEarn | 74e884f0 (v2.4.0, 2026-05-21) | v2.5.0 (2026-06-24) | 1 release (10 天) | **选择性**（Twitter 规则）| P1 |
| 5 | wechat-article/wechat-article-exporter | 未记录 | v2.3.19 (docker package) | 持续 | **不** | — |
| 6 | cv-cat/Spider_XHS | 未记录 | 持续合并 PR | 持续 | **不** | — |

---

## 二、openclaw v2026.6.10 → v2026.6.11（**强烈建议升级**）

### 2.1 关键变更

v2026.6.11 release notes（[2026-06-30 官方](https://docs.openclaw.ai/releases/2026.6.11)）核心主题："rough edges that make OpenClaw feel less dependable"。

#### Channel delivery reliability（**与 wiseflow 强相关**）

| Channel | 关键修复 |
|---------|----------|
| **Feishu** | voice replies 显示 duration（#89172）— wiseflow 主力 channel |
| Telegram | reply 正确附加 / 进度清理 / 接力会话 / webhook 重启不丢消息（#89911, #90475, #95004, #95007, #95183, #95577, #97543） |
| WhatsApp | group 上下文保留 / quote 修复（#94338, #95483, #95914, #95935, #96220） |
| Discord | long reply 截断修复（#95661）/ 语音会话接力 / progress preview 修复 |
| Google Chat | DM routing 修复（#58993）/ 内部 failure banner 修复（#95084） |
| iMessage | 延迟 link preview 不再产生多 turn（#93143, #94442） |
| Matrix | E2EE 长时间 gateway 内存修复（#94942, #95240） |
| Mattermost | slash commands / DM 上下文 / `/oc_queue` 调优（#95546, #95550, #95552, #96244） |

#### Provider & model recovery

- Anthropic fallback：Claude Opus 4.8 自动 fallback（#97000+；wiseflow 走 ark/glm-latest，但 anthropic 是 fallback 通道）
- OpenAI Responses / OpenRouter / Azure / Mistral / Google 大量改进
- **Reasoning leakage 修复**（#92356）：reasoning-capable model 在 Telegram/WhatsApp 等 channel 不再暴露内部 reasoning 文本
- Fast mode fallback 一致性改进
- OpenClaw 0.11.2 持久化修复（#96124）

#### Session, memory & trust continuity

- Memory QMD 改进（#93113, #93394, #94369, #94811, #95087, #95274）
- Session 修复（tool output 过大 / 长时间运行 / save 失败）
- **Encrypted Matrix recovery 安全性**（#95720）
- Trusted package sources 防止 lookalike 攻击（#12c34fc）
- **Control UI DOMPurify 漏洞修复**（#95691 GHSA-cmwh-pvx-8882）

#### Gateway, Security & Trust

- Restart drain 不阻塞 traffic（#94915）
- systemd-managed gateway 内存压力下保持 channel 连接（#93585）
- Long-context tool-heavy session prompt-cache 保留（#95624）
- Plugin policies 跨 registry 改动保留（#94545）
- 多个 Windows / macOS / Linux 平台修复

#### Slack router relay mode（#94707）

多 gateway 部署新模式——本仓不涉及（单 gateway），**不**catch。

#### Raft External Agent wake bridge（#95497）

外部 agent 通过 CLI 唤醒 openclaw——本仓不涉及，**不**catch。

#### Official plugin installation

- Codex / OpenClaw Codex 兼容（#89612）
- Plugin 依赖 EOVERRIDE 修复（#91786）
- Pinned plugin 更新修复（#95541）
- Windows ARM64 Node 匹配下载（fac091b）

### 2.2 升级影响评估

#### patch 影响

| Patch | 6.10 状态 | 6.11 状态（预测）| 行动 |
|-------|----------|------------------|------|
| 002 (disable-web-search-env-var) | apply OK | 大概率仍 apply | 不动 |
| 003 (act-field-validation) | apply OK | 大概率仍 apply | 不动 |
| 005 (browser-timeout-env-var) | apply OK | 大概率仍 apply | 不动 |
| 006 (connectovercdp-no-defaults) | apply OK | 大概率仍 apply | 不动 |

**0 patch re-port 风险**（无 001 / 004 已删，6.11 文件结构变化应在 6.10 基础上的小修）。

#### wiseflow 业务影响

| 能力 | 6.10 | 6.11 改进 | 风险 |
|------|------|----------|------|
| Feishu 通道 | OK | voice duration 修复（不影响功能） | 无 |
| 飞书 / 微信 channel config | 已知 | 多个 routing 修复 | 需 spike |
| GLM-5.2 主力 model | 128K tokens | 仍 128K（#91724 保护）| 无 |
| Cron SQLite | 已知 | memory 状态 / QMD 改进 | 无 |
| exec-approvals 6.10 重构 | OK | restart drain 改善 | 无 |
| Gateway restart 流程 | 已知 | handoff 改进 | 无 |

#### openclaw-weixin 插件兼容性

- 本仓 `openclaw-weixin.version.json` 锁版本——需查 6.11 是否兼容
- 若不兼容 → 同步升级 weixin 插件

### 2.3 升级路径

按 [[03-openclaw-upgrade]] 流程：

1. `cd ~/wiseflow-pro/openclaw` → `git fetch origin --tags` → `git checkout v2026.6.11`
2. 顺序 `git apply --check` 现有 4 patch（002/003/005/006），全部应 OK
3. **无失败则**直接 update `openclaw.version` 到 `v2026.6.11` + `OPENCLAW_COMMIT`
4. `pnpm install --frozen-lockfile && pnpm build`
5. 本机实例部署验证
6. commit：`chore(sync): update openclaw to v2026.6.11, ...`

**预估工时**：30-60 分钟（无 patch 失败场景）。

### 2.4 风险

- 6.11 距今 4 天 release——稳定度尚可，但新 channel 行为可能影响**未 spike 的子能力**（如未测的第三方 channel）
- 本轮已 commit 22 个（camoufox 集成 / 火山生图 / bilibili-publish relay / douyin-publish 浏览器模拟 / main 改名 / IR 三模式 / BD 合入 / D21 设计 等）—— 升级 openclaw 时**应**重新跑**所有 68 单元测试** + 心跳 dry-run
- 若升级 + 部署 → 需用户确认时机（**生产 Gateway 重启会断所有 session**）

### 2.5 决策建议

**建议升级**。理由：
1. 6.10 落后 1 个稳定 release（4 天）
2. 6.11 含**大量 channel 修复**（Feishu / Telegram / WhatsApp / Discord 等）—— 风险降低
3. **0 patch re-port**（现有 4 patch 在 6.10 + 6.11 都应 apply OK）
4. wiseflow 主力是 Feishu 通道，6.11 Feishu 修复直接受益
5. 部署阶段一并升级（**当前本机实例不动**，但 6.11 升级可在 6.10 基础上的 atomic 升级）

**何时升**：与本机源码部署同步（用户已确认"先源码部署，验证后再做 Docker"）。**本轮不升**（本机实例不动）；源码部署时一并升。

---

## 三、patchright v1.60.2（不升级）

### 3.1 当前状态

- 本仓 catchup: v1.60.2（`patches/overrides.sh` 默认）
- PyPI 最新: v1.60.2 (2026-06-29)
- Playwright 最新: 1.60.0 (2026-05-11) — patchright 跟 playwright 同步
- 6 月以来无新版

### 3.2 决策

**暂不升级**。理由：
1. patchright 自动跟随 playwright（无 patchright 单独版本节奏）
2. 本仓 Phase 4.5 已切 camoufox-cli 主推路径（patchright 是 fallback）—— patchright 重要性降级
3. 6 月以来无新 release——没有明确收益

### 3.3 何时 catch

- Playwright 大版本更新时（如 1.61+）—— patchright 跟同步升级
- 反检测被新 Cloudflare 拦截时—— patchright 升级可能修复

---

## 四、OpenCLI jackwener/opencli（仅观察）

### 4.1 当前状态

- 本仓 catchup: 8ed8ca26 (2026-06-13)
- 上游 HEAD: v1.0.21 (2026-07-03) — 持续活跃
- 上游核心主题："AI-driven self-healing" / "vigilant mode"

### 4.2 决策

**仅观察 design pattern 更新，不 catch 代码**。理由：
1. **架构不兼容**：OpenCLI 走浏览器扩展 + `page.evaluate`，Wiseflow 走 CDP + API
2. 本仓仅借鉴**smart-search 设计模式**（Sitemap pitfalls/fallback/re-entry / 搜索频率限制 / 搜索摘要规范）
3. 这些 design pattern 已吸收到 `skills/smart-search/SKILL.md`

### 4.3 何时 catch

- OpenCLI 出新"site-specific"模式（如 LinkedIn / Twitter 爬取），与本仓的 BD 流程有交集——评估借鉴
- 出"vigilant mode"反检测相关新概念——评估与 Phase 4.5 camoufox 集成点

---

## 五、AiToEarn yikart/AiToEarn v2.5.0（选择性 catch）

### 5.1 当前状态

- 本仓 catchup: 74e884f0 (v2.4.0, 2026-05-21)
- 上游 HEAD: v2.5.0 (2026-06-24)
- v2.5.0 重点："Twitter publishing improved: Twitter APIs now support richer posting, interaction, typed publishing options, and stronger response definitions"

### 5.2 决策

**选择性 catch：Twitter 平台规则表更新**。理由：
1. 本仓借鉴的 18 平台限制规则表——Twitter 部分 v2.5.0 有更新
2. 文字 / 媒体 / 互动类型限制可能变了
3. 仅 catch Twitter 相关——其他平台本仓未集成

### 5.3 何时 catch

- 部署阶段做一次 AiToEarn 平台限制表对比更新（特别是 Twitter）
- 内容校验脚本如有更新——评估借鉴（viral-chaser / published-track 相关）

---

## 六、wechat-article-exporter（不 catch）

### 6.1 当前状态

- 本仓 catchup: 未记录
- 上游 HEAD: v2.3.19 (docker package, 仍在迭代)
- 已知背景：wechat-article-exporter 是 desktop browser + 无微信登录的 guest session token 架构

### 6.2 决策

**不 catch**。理由：
1. dev plan §Phase 4.6 方案 B（容器内 mitmproxy + camoufox）— 仅备选，本轮 spike A 优先
2. 即使方案 B 实施，wechat-article-exporter 是**桌面浏览器架构**，与本仓**容器内 camoufox 架构**需大幅改造
3. 优先做方案 A 验证（camoufox 跑创作者中心）

### 6.3 何时 catch

- Phase 4.6 spike A 失败后启方案 B 时再评估
- 公众号创作者中心 DOM 大改时（如 wechat-article-exporter 已适配新 DOM）— 借鉴其字段映射

---

## 七、Spider_XHS cv-cat（不 catch）

### 7.1 当前状态

- 本仓 catchup: 未记录
- 上游 HEAD: 持续合并 PR（feat/update_060428）
- 已知背景：Spider_XHS 是 QR 登录 + cookie 抓取的小红书爬虫

### 7.2 决策

**不 catch**。理由：
1. **架构不兼容**：Spider_XHS 走 QR 登录 + 移动端协议，Wiseflow 走 CDP + 浏览器
2. 本仓已通过 Phase 4.5.4 收敛浏览器类 skill（viral-chaser / xhs-content-ops / xhs-interact 全部改用 camoufox-cli）
3. cv-cat 也出了 `XhsSkills`（小红书 Skills 库）—— 架构可能更近，但**与本仓已有 skill 重复**

### 7.3 何时 catch

- 小红书创作者中心 DOM 大改时（如 cv-cat 适配新 DOM）— 借鉴
- 小红书新增"视频号"或"直播"功能——评估

---

## 八、本轮行动项

| 项 | 行动 | 时机 |
|---|------|------|
| **P0** openclaw 升级 | 按 [[03-openclaw-upgrade]] 流程：v6.10 → v6.11 | 源码部署时（用户已确认先源码部署后 Docker） |
| **P1** AiToEarn Twitter 规则 | 抓 v2.5.0 平台限制表，更新本仓 published-track skill | 源码部署后，单独 1 个 commit |
| **P3** 持续观察 | openclaw 后续 release + OpenCLI 重大更新 | 心跳 / 用户提醒 |
| **不** | patchright（无新版）| — |
| **不** | wechat-article-exporter / Spider_XHS（架构不兼容）| — |

---

## 九、注意事项

- **openclaw 升级前置检查**：源码部署前，按 `03-openclaw-upgrade.md` 流程完整跑一遍（切版本→验 patch→重新生成→提交）
- **本轮 commit 兼容性**：22 个本轮 commit 不会因 openclaw 升级失效——camoufox-cli 是 npm 全局，login-manager 是 Python stdlib，bilibili-publish / douyin-publish / siliconflow-img-gen 都跟 openclaw 解耦
- **部署后验证**：升级后必跑 `tests/` 全部 68 单测 + 心跳 dry-run
- **回滚预案**：升级前 `cp openclaw{,.bak-<date>}` 全量备份；3 天观察期，若心跳异常 `git checkout v2026.6.10` 回滚

---

关联：
- `~/.claude/projects/-home-wukong-wiseflow/memory/02-upstream-sources.md`（上游来源表）
- `~/.claude/projects/-home-wukong-wiseflow/memory/03-openclaw-upgrade.md`（升级流程）
- `docs/phase-4.5-design.md`（camoufox 集成设计）
- `docs/d21-symlink-skill.md`（D21 软链化设计）
