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

> **纯浏览器操作方案**：本 skill 自身不吃 cookie，**严禁** `cookies import` 造登录会话——浏览器操作一律走 login-manager 真实登录后的**持久化 session `douyin`**（登录态 + 指纹冻结在 session profile 里）。探活 / 有头登录 / 导出 cookie+UA 全交 login-manager，本 skill 只复用持久化 session 做发布操作。

---

## 前置条件

1. **login-manager 已登录 `douyin`**：持久化 session `douyin` 是登录态。首次使用 / 失效时走 login-manager 流程（不在本 skill 内做）：
   ```bash
   camoufox-cli --session douyin --persistent --headed --json open "https://creator.douyin.com/"
   # 告知用户在窗口里手动完成创作者中心登录，确认后：
   login-manager --platform douyin
   ```
   login-manager 一条命令闭环导出+验证+落中央存储（供 viral-chaser / published-track 消费）+ close session。本 skill 发布时 douyin-publish run 会使用 `--session douyin --persistent` 重起无头 session。
2. 视频文件准备好（mp4 / mov）
3. 抖音创作者中心已实名认证（必须，本人手机号 + 身份证）

---

## 使用方式

### 一键全流程

```bash
douyin-publish run \
  --video /path/to/video.mp4 \
  --title "视频标题" \
  --caption "视频描述 #话题1 #话题2"
```

`run` 内部串：upload → fill → publish → get-link。
`run` 之前确认 session 已登录。

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

> **注意**：本 skill **没有 `login` 子命令、也没有 `cleanup` 子命令**——探活/登录/导出 cookie+UA 全交 login-manager；持久化 session `douyin` 用完即 close（登录态在磁盘 profile，下次重起无头即恢复），只在 session 卡死时由调用方手动 `camoufox-cli --session douyin --json close` teardown。

---

## 创作者中心 URL

上传页：`https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web`

视频管理页：`https://creator.douyin.com/creator-micro/content/manage`（取链接用）

---

## 必做约束

- **用完即 close 持久化 session `douyin`**——登录态 + 指纹冻结在磁盘 profile，不留进程占内存；下次发布 `--session douyin --persistent` 重起无头即恢复。只在 session 卡死时 `camoufox-cli --session douyin --json close` teardown。
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
