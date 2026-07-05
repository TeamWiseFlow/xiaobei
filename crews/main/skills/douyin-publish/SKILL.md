---
name: douyin-publish
description: 通过浏览器自动化发布视频到抖音创作者中心（camoufox-cli 主推）。绕过
  抖音开放平台资质限制。
metadata:
  openclaw:
    emoji: 🎤
    requires:
      bins:
      - python3
      - camoufox-cli
---

# 抖音内容发布

> **核心原因**：抖音开放平台发布能力申请被驳回（主体资质不满足）→ 改走浏览器模拟，绕过资质限制。
>
> **形态**：用 camoufox-cli 启 headless 会话 + login-manager 拿 cookie + 创作者中心填表上传 + 发布 + 取链接。

---

## 前置条件

1. login-manager 已有 `douyin` cookie（中央存储 `~/.openclaw/logins/douyin.json`）
2. 首次使用需走 login-manager 扫码登录流程（`qr-headless` + `qr-confirm`）
3. 视频文件准备好（mp4）
4. 抖音创作者中心已实名认证（必须，本人手机号 + 身份证）

---

## 使用方式

### 一键全流程

```bash
python3 ./skills/douyin-publish/scripts/publish_douyin.py run \
  --video /path/to/video.mp4 \
  --title "视频标题" \
  --caption "视频描述 #话题1 #话题2"
```

### 分步调用（agent 按需）

```bash
# 1. 探活（exit 0 = 有效, 2 = 失效需扫码登录）
python3 ./publish_douyin.py login

# 2. 上传视频（返回 session 名，后续步骤用）
python3 ./skills/douyin-publish/scripts/publish_douyin.py upload --video video.mp4

# 3. 填标题/描述
python3 ./skills/douyin-publish/scripts/publish_douyin.py fill --session <s> --title "标题" --caption "描述"

# 4. 点发布
python3 ./skills/douyin-publish/scripts/publish_douyin.py publish --session <s>

# 5. 取视频链接
python3 ./skills/douyin-publish/scripts/publish_douyin.py get-link --session <s>

# 6. 清理（最后一步必调）
python3 ./skills/douyin-publish/scripts/publish_douyin.py cleanup --session <s>
```

---

## 创作者中心 URL

`https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web`

视频管理页：`https://creator.douyin.com/creator-micro/content/manage`（取链接用）

---

## Cookie 管理

走 `login-manager` skill（同 crew 私有）：

```bash
# 失效后扫码重登
login-manager.sh qr-headless douyin
# → 发 QR PNG 给用户
login-manager.sh qr-confirm douyin --session <s> --timeout 180
```

`login-manager` 平台 key：`douyin`。

---

## 与 wechat-channels-publish 的对比

| 维度 | 微信视频号 | 抖音 |
|------|----------|------|
| URL | `channels.weixin.qq.com/platform/post/create` | `creator.douyin.com/creator-micro/content/upload` |
| 微前端 | wujie + shadow DOM | 普通 React DOM（无 shadow） |
| 登录 | 微信扫码 | 抖音创作者中心扫码（手机号+验证码） |
| 浏览器方案 | camoufox-cli 主推 | camoufox-cli 主推 |
| 凭据 | login-manager `wechat-channels` | login-manager `douyin` |
| 视频发布后 | 链接 `weixin.qq.com/sph/xxx` | 链接 `douyin.com/video/xxx` |

---

## 形态仿 wechat-channels-publish

- 6 个子命令：login / upload / fill / publish / get-link / cleanup
- run 命令一键跑全流程
- camoufox 启 headless + persistent 会话（每任务一 session）
- 上传走 `DataTransfer` + `File` 对象注入（绕过 CDP setFileInput 在某些 DOM 下的限制）
- 等待页面状态变化（轮询 `body.innerText`）
- 失败模式：DOM 改版 / 按钮找不到 / 转码超时

---

## Pitfalls

### pitfall: douyin_login_required_on_creator_center

- **触发**：访问 `creator.douyin.com` 未登录态
- **症状**：页面跳到 `creator.douyin.com/login` 或出现登录弹窗
- **workaround**：走 login-manager `qr-headless + qr-confirm` 重新登录抖音

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
- **workaround**：spike 验证后更新 selector；本轮交付 selector 是公开推测

### pitfall: rate_limit_after_burst_publish

- **触发**：短时间内连续发布多条
- **症状**：平台风控 / 上传被拒 / 提示"操作过于频繁"
- **workaround**：每天 ≤ 5 条；触发后 30 分钟内不重试

### pitfall: camoufox_session_leak

- **触发**：任务结束未 cleanup
- **症状**：下次启动 session 冲突
- **workaround**：每个发布任务**必须** cleanup（`session-cleanup` 或 `cmd cleanup`）

---

## Spike 验证 checklist（部署后真机测试）

> 跟 wechat-channels-publish 一样的 8 个 selector 需 spike 验证：
> - 上传 input 元素（`input[type="file"][accept*="video"]`）
> - 标题输入（`input[placeholder*="标题"]`）
> - 描述 contenteditable（`div[contenteditable][data-placeholder*="描述"]`）
> - 发布按钮（`button:has-text("发布")`）
> - 上传成功文本（"上传成功"）
> - 发布成功提示（"发布成功"）
> - 视频管理页第一条 selector（`[class*="content-item"]:first-child`）
> - 视频链接 selector（`a[href*="/video/"]` 或 data-aweme-id）

**验收**：跑通一条真实视频从 upload 到 get-link 全流程。

---

## 凭据

- 本 skill 只需要 `login-manager` 中央 cookie（session token，容器内闭环），不持任何抖音官方 API 凭据
- 抖音发布走浏览器模拟（client 端操作，不经 relay 代理）

---

## Notes

- Docker 内 `command-tier=T3` full（无 allowlist 限制）
- 限频建议：单抖音号每 24h ≤ 5 条发布；触发风控立即降级
- 失败回退：浏览器模拟失败 → 维持现状（让用户自己手动发）
- 抖音创作者中心 DOM 改版频繁：selector 需 spike 验证
