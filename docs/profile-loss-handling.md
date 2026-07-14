# profile 丢失 / 损坏 / 指纹错配 处理规范

> spec `browser-stack-replacement-spec-2026-07.md` §8（补充 D，强化原则 5）。
> 本文档是 canonical 程序，供 login-manager / browser-guide / 各平台 skill 引用。
> HEARTBEAT.md 约束 4 已落地「凌晨心跳跳过 + 等白天」策略，本文档补白天恢复流程。

## 核心原则

**profile 丢失 / 损坏 / 指纹错配 → 重建 + 重登录，绝对不允许导入 cookie 造会话。**

| # | 原则 |
|---|------|
| 5 | 严禁浏览器方案导入 cookie（登录失效必须重新登录流程） |
| 补充 D | profile 丢失：重建 + 重登录，绝对不允许导入 |
| 3 | 登录对齐：douyin / twitter / xhs / weibo / zhihu / xianyu / reddit / youtube **有头**登录；wechat-channel / wx-mp 无头截图 QR |

## 为什么禁止导入

xhs `a1` / `websectiga` 等设备指纹 cookie 与浏览器指纹绑定。导入到**不同指纹**的 profile 会错配 → 被风控检测 → 限流 / 封号。

**2026-06-29 教训**：凌晨心跳里 xhs-browse 无登录态，Agent 用 CDP `Network.setCookies` 注入 22 个 cookie 强造会话后批量抓取，**当日触发小红书风控、账号被处罚**（HEARTBEAT.md 约束 4 详记）。

任何「用 cookie 造一个登录会话」的动作都禁止——包括：
- ❌ camoufox-cli `cookies import` 把中央存的 cookie 灌进一个**新指纹**的 profile
- ❌ CDP `Network.setCookies` 注入
- ❌ 反复刷新 / 重导航 profile 页试图「刷出」登录态
- ❌ 不带 xsec_token 硬调 feed API 试 fallback

## camoufox-cli `cookies import` 的合法用途

forked camoufox-cli 保留上游 `cookies export/import` 命令（spec §1.2 不改，JSON = Playwright `add_cookies` 格式，零转换）。**合法用途仅限**：

- **同指纹 profile 的 cookie 备份 / 恢复**：同一 `--persistent` profile（`camoufox-cli.json` 指纹冻结）的 cookies export 出来再 import 回去，指纹一致，无错配风险。
- **跨设备迁移同一指纹**：把 profile 整体（`camoufox-cli.json` + `cookies.sqlite` + state）一起搬，不是只搬 cookie。

**禁止**：profile 已丢 / 指纹已变时，用 `cookies import` 把中央存的 cookie 灌进新 profile 试图恢复登录——这正是补充 D 禁止的动作。

## 白天恢复流程（profile 丢失 / 损坏 / 指纹错配）

由用户白天执行（凌晨心跳只跳过 + 记录 + 汇总上报，见 HEARTBEAT.md 约束 4）。

### 1. 确认 profile 状态

```bash
# 检查持久化 profile 目录
ls ~/.camoufox-cli/profiles/<platform>/
# 若 camoufox-cli.json 缺失 / cookies.sqlite 损坏 / 目录被删 → profile 丢失
```

login-manager 探活失败（`login-manager check <platform>` exit 2）且确认非网络问题 → 走重建。

### 2. 删除旧 profile（彻底）

```bash
rm -rf ~/.camoufox-cli/profiles/<platform>
# 同时清中央 cookie + UA（已失效，留着会诱导误用 import）
rm -f ~/.openclaw/logins/<platform>.json ~/.openclaw/logins/<platform>.ua.json
```

### 3. 重建 profile + 重登录（按原则 3 选模式）

```bash
# 有头登录（douyin / twitter / xhs-publish / xhs-browse / weibo / zhihu / xianyu / reddit / youtube）
login-manager login-headed <platform>
# → camoufox-cli --session <platform> --persistent --headed open <login-url>
# → 用户在 Firefox 窗口完成登录
# → login-manager 导出 cookie + UA（forked cli identity export）
# → close

# 无头截图 QR（wechat-channel / wx-mp）
login-manager qr-headless <platform>
# → 发 QR PNG 给用户
login-manager qr-confirm <platform> --session <s> --timeout 180
```

### 4. 验证

```bash
login-manager check <platform>   # exit 0 = 恢复成功
```

## 临时性 session 不受影响

不涉及登录的站点（新闻 / rss-reader / intel-gathering 等纯浏览取数）走 forked cli 默认临时 profile（每次随机指纹，关闭自清），**没有 profile 丢失概念**——临时 profile 本就一次性。补充 A。

## 引用

- spec：`docs/browser-stack-replacement-spec-2026-07.md` §8 + 原则 3 / 5 + 补充 D
- HEARTBEAT：`crews/main/HEARTBEAT.md` 约束 4（凌晨跳过 + 等白天）
- forked cli：`patches/camoufox-cli/`（`cookies export/import` + `identity export`）
- 调研：`docs/browser-extension-replacement-research.md` §12
