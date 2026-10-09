# profile 丢失 / 损坏 / 指纹错配 处理规范

> spec `browser-stack-replacement-spec-2026-07.md` §8（补充 D，强化原则 5）。
> 本文档供 browser-guide 和各平台技能引用。平台登录按当前技能入口执行；X/TikTok/微博登录由 platform-runtime 内部管理。
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

对应平台 `check` 返回明确鉴权失败时，先检查原 profile 是否完整。API 鉴权失败不等于 profile 丢失；网络、风控和浏览器技术错误不能据此重建。

### 2. 备份损坏的 profile

确认损坏并取得用户同意后，由对应平台流程关闭并备份旧 profile，再重建。不要清空其他账号、整个平台凭据目录或其他平台状态。X/TikTok/微博的新导出先在临时目录验证，成功才替换指定账号；失败保留旧 API 会话。

### 3. 重建 profile + 重登录（按原则 3 选模式）

| 平台 | 当前登录入口 |
|---|---|
| X / TikTok / 微博 | 对应 `x-hunter` / `tiktok-hunter` / `weibo-hunter` 的 `login --account <alias>`；用户确认后 `export --account <alias>` |
| 快手 | `kuaishou-hunter login/login-confirm` 的 QR/SMS 流程，不使用浏览器 profile |
| 抖音发布/本人取数 | `douyin-publish login`，同一持久 profile，不导出中央 Cookie |
| 抖音采集/互动 | `douyin-login` 的独立 API 登录流程 |
| 小红书 PC / Creator | `xhs-hunter login` / `xhs-publish login` 各自管理的 API 会话 |
| 其他平台 | 阅读该平台技能，使用其现有登录流程 |

X/TikTok/微博的导出规则见 [运行库登录说明](../crews/main/skills/platform-runtime/references/login.md)。TikTok 写能力需要同次 Studio 会话材料，不能以普通 Cookie 登录成功代替。

### 4. 验证

调用同一平台工具的 `check`，确认在线身份属于预期账号。导出成功不代表发布、私信等写能力已经验收；依照对应工具限制处理。

## 临时性 session 不受影响

不涉及登录的站点（新闻 / rss-reader / intel-gathering 等纯浏览取数）走 forked cli 默认临时 profile（每次随机指纹，关闭自清），**没有 profile 丢失概念**——临时 profile 本就一次性。补充 A。

## 引用

- spec：`docs/browser-stack-replacement-spec-2026-07.md` §8 + 原则 3 / 5 + 补充 D
- HEARTBEAT：`crews/main/HEARTBEAT.md` 约束 4（凌晨跳过 + 等白天）
- forked cli：`patches/camoufox-cli/`（`cookies export/import` + `identity export`）
- 调研：`docs/browser-extension-replacement-research.md` §12
