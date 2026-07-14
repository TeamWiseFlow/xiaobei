---
name: douyin-publish
description: 通过浏览器自动化发布视频到抖音创作者中心。纯浏览器操作方案。
metadata:
  openclaw:
    emoji: 🎤
    requires:
      bins:
      - python3
      - camoufox-cli
---

# 抖音内容发布

通过 **camoufox-cli** 持久化 session `douyin`（一个且只有一个持久化 session，fail-first 队列：同 session 已有命令在跑时新命令直接 fail）在抖音创作者中心发布视频。

> **纯浏览器操作方案**：本 skill 自身不吃 cookie，**严禁**通过 `cookies import` 导入 cookie 造登录会话——浏览器操作一律走 login-manager 真实登录后的**持久化 session**（登录态 + 指纹冻结在 session profile 里）。
>
> **使用login-manager技能完成登录操作**：login-manager会引导用户完成手机号+验证码 / 抖音 APP 扫码登录，以及导出 cookie + UA 落中央存储，这是为了供非浏览器类脚本（`viral-chaser`、`published-track` 等）消费。导出 + 有头登录由 login-manager 负责，本 skill 只消费 login-manager 留下的持久化 session。

---

## 职责划分（与 login-manager 的边界）

| 职责 | 归属 |
|------|------|
| 探活（验 session 是否仍登录态） | login-manager |
| 有头手动登录（手机号+验证码 / 抖音 APP 扫码） | login-manager |
| 导出 cookie + UA 落中央存储 | login-manager |
| 复用持久化 session 做浏览器发布操作 | **douyin-publish（本 skill）** |

---

## 前置条件

1. login-manager 已就位：持久化 session `douyin` 是登录态，且中央存储 `~/.openclaw/logins/douyin.json` + `~/.openclaw/logins/douyin.ua.json` 已导出（cookie + UA 同一指纹，供 viral-chaser / published-track 消费）。
   - 首次使用 / 登录态失效时，调用方走 **login-manager 有头手动登录流**（不在本 skill 内做）：
     - `camoufox-cli --session douyin --persistent --headed --json open "https://creator.douyin.com/"`
     - 告知用户「**抖音** 浏览器已打开，请在窗口里手动完成创作者中心登录（手机号+验证码 / 抖音 APP 扫码），完成后告诉我」
     - 登录就位后**同时导出 cookie + UA**（由 login-manager 流程负责）：
       - `camoufox-cli --session douyin --persistent --json cookies export ~/.openclaw/logins/douyin.json`
       - `camoufox-cli --session douyin --persistent --json identity export ~/.openclaw/logins/douyin.ua.json`
     - 登录后**不关 session**——持久化 session `douyin` 登录态留着给本 skill 做发布操作复用，主动 close 会破坏复用。
2. 视频文件准备好（mp4 / mov）
3. 抖音创作者中心已实名认证（必须，本人手机号 + 身份证）

> **同时导出 cookie 和 UA**：抖音设备指纹 cookie 必须配同一指纹的 UA，否则被风控错配。本 skill 走持久化 session `douyin`（登录态 + 指纹冻结在 session profile 里），**自身运行不读中央 cookie 文件**——探活也是 `open + snapshot` 看跳登录页，不走中央存储。导出 cookie+UA 落中央存储仅为供 viral-chaser / published-track 等下游脚本消费（不是本 skill 用）+ 与 login-manager 5 平台统一步骤保持一致。

---

## 使用方式

### 一键全流程

```bash
douyin-publish run \
  --video /path/to/video.mp4 \
  --title "视频标题" \
  --caption "视频描述 #话题1 #话题2"
```

`run` 内部串：upload → fill → publish → get-link。**不**自管 login 探活——探活交 login-manager，由调用方在调 `run` 之前确认 session 已登录。

### 分步调用（agent 按需）

```bash
# 1. 上传视频（返回 session 名，后续步骤用）
douyin-publish upload --video video.mp4

# 2. 填标题/描述
douyin-publish fill --session <s> --title "标题" --caption "描述"

# 3. 点发布
douyin-publish publish --session <s>

# 4. 取视频链接
douyin-publish get-link --session <s>
```

> **注意**：本 skill **没有 `login` 子命令、也没有 `cleanup` 子命令**——探活/登录/导出 cookie+UA 全交 login-manager；持久化 session `douyin` 不主动 close（登录态留着下次用），只在 session 卡死时由调用方手动 `camoufox-cli --session douyin --json close` teardown。

---

## 创作者中心 URL

上传页：`https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web`

视频管理页：`https://creator.douyin.com/creator-micro/content/manage`（取链接用）

---

## 必做约束

- **不主动 close 持久化 session `douyin`**——登录态 + 指纹冻结留着下次用。只在 session 卡死时 `camoufox-cli --session douyin --json close` teardown。
- 同 session 已有命令在跑时，新命令 fail-first（返回 `session douyin 正忙，请等待当前操作完成后再试`）——读到这条文本就等当前操作完成再重试，不要盲试。
- **严禁 `cookies import`**：浏览器操作不开临时 session 再 import cookie 那一套，会触发平台风控。
- **不导出 cookie / UA**：导出是 login-manager 的事，本 skill 不调用 `cookies export` / `identity export`。

---

## Pitfalls

### pitfall: douyin_login_required_on_creator_center

- **触发**：访问 `creator.douyin.com` 未登录态
- **症状**：页面跳到 `creator.douyin.com/login` 或出现登录弹窗
- **workaround**：脚本返回 `exit 2`（session 失效），由调用方走 **login-manager 有头手动重登流**，不在本 skill 内自管重登。

### pitfall: real_name_auth_required

- **触发**：未实名认证的账号
- **症状**：创作者中心提示"请先完成实名认证"才能发布
- **workaround**：用户自己走实名认证流程（脚本帮不上）

### pitfall: video_too_long_or_wrong_format

- **触发**：上传非 mp4 / mov 格式，或视频时长超限
- **症状**：上传后转码失败 / 客户端拒收
- **workaround**：转 mp4 + 检查时长（抖音支持最长 15 分钟）

### pitfall: dom_changes_creator_center

- **触发**：抖音创作者中心前端改版
- **症状**：selector 找不到（input / button 位置变化）
- **workaround**：部署后真机验证更新 selector（见 `docs/post-deploy-verification.md`）；首轮交付 selector 是公开推测

### pitfall: rate_limit_after_burst_publish

- **触发**：短时间内连续发布多条
- **症状**：平台风控 / 上传被拒 / 提示"操作过于频繁"
- **workaround**：每天 ≤ 5 条；触发后 30 分钟内不重试

---

## Notes

- Docker 内对内 crew exec full（无 allowlist 限制）
- 限频建议：单抖音号每 24h ≤ 5 条发布；触发风控立即降级
- 失败回退：浏览器模拟失败 → 维持现状（让用户自己手动发）
- 抖音创作者中心 DOM 改版频繁：selector 需部署后真机验证（见 `docs/post-deploy-verification.md`）
- **形态仿 wechat-channels-publish**：5 个子命令（upload / fill / publish / get-link / run），无 login 子命令、无 cleanup 子命令。run 命令一键跑全流程。走持久化 session `douyin`（登录态 + 指纹冻结在 session profile 里），跑完不主动 close。上传走 `camoufox-cli upload` 命令（底层 Playwright `setInputFiles`）。等待页面状态变化（轮询 `body.innerText`）。失败模式：DOM 改版 / 按钮找不到 / 转码超时。
