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

通过 **camoufox-cli** 持久化 session `douyin`(一个且只有一个持久化 session,fail-first 队列:同 session 已有命令在跑时新命令直接 fail)在抖音创作者中心发布视频。

> **纯浏览器操作方案**:本 skill 自身不吃 cookie,**严禁** `cookies import` 造登录会话--浏览器操作一律走 login-manager 真实登录后的**持久化 session `douyin`**(登录态 + 指纹冻结在 session profile 里)。探活 / 有头登录 / 导出 cookie+UA 全交 login-manager,本 skill 只复用持久化 session 做发布操作。

---

## 如果登录失效:使用 login-manager 重新登录

走 login-manager skill 流程,复用 `douyin` 持久化 session

```bash
camoufox-cli --session douyin --persistent --headed --json open "https://www.douyin.com"
# 告知用户在窗口里手动完成创作者中心登录,确认后:
login-manager --platform douyin
```

login-manager 一条命令闭环导出+验证+落中央存储(供 viral-chaser / published-track 消费)+ close session。本 skill 发布时 douyin-publish run 会使用 `--session douyin --persistent` 重起无头 session。

---

## 使用方式

### 一键全流程

```bash
douyin-publish run \
  --video /path/to/video.mp4 \
  --title "视频标题" \
  --caption "视频描述 #话题1 #话题2"
```

`run` 内部串:upload → fill → publish → get-link。

### 分步调用(agent 按需)

```bash
# 1. 上传视频（返回 session 名，后续步骤用）
douyin-publish upload --video video.mp4

# 2. 填标题/描述 + 自主声明
#    fill 命令内部自动完成：填标题 -> 填简介 -> 选自主声明"内容由AI生成" -> 点"确定"按钮
#    自主声明下拉不存在时不阻断（部分账号/页面无此选项）
douyin-publish fill --session <s> --title "标题" --caption "描述"

# 3. 点发布（注入拦截器捕获 aweme_id 写入 localStorage，返回 aweme_id）
douyin-publish publish --session <s>

# 4. 取视频链接
douyin-publish get-link --session <s>
```

> **get-link 取链接策略**(2026-07-17 事故修正):`publish` 阶段从发布 API 响应里抓 `aweme_id` 写进 `localStorage.douyin_last_aweme_id`(同源跨发布→管理导航存活,不像 `window` 变量随跳转销毁)。`get-link` 首选读 localStorage 拼 `https://www.douyin.com/video/<aweme_id>`,读不到才回退管理页 DOM。`run` 全流程在 `close` session 之前就拿到链接,不依赖 close 后重开。

> **注意**：本 skill **没有 `login` 子命令、也没有 `cleanup` 子命令**--执行过程中任何时候发现登录态已失效，重走 login-manager 登录流程。
>
> **自主声明流程**（2026-07-17 真机确认）：点开"请选择自主声明"下拉 -> 选"内容由AI生成" -> **点弹窗右下角粉色"确定"按钮**让声明生效。`fill` 命令已内置此流程。

---

## 创作者中心 URL

上传页:`https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web`

视频管理页:`https://creator.douyin.com/creator-micro/content/manage`(取链接用)

---

## 必做约束

- **用完即 close 持久化 session `douyin`**--登录态 + 指纹冻结在磁盘 profile,不留进程占内存;下次发布 `--session douyin --persistent` 重起无头即恢复。只在 session 卡死时 `camoufox-cli --session douyin --json close` teardown。
- 同 session 已有命令在跑时,新命令 fail-first(返回 `session douyin 正忙,请等待当前操作完成后再试`)--读到这条文本就等当前操作完成再重试,不要盲试。
- **严禁 `cookies import`**:浏览器操作不开临时 session 再 import cookie 那一套,会触发平台风控。
- 执行过程中任何时候发现登录态已失效,则走 login-manager 有头重登流。
- **不导出 cookie / UA**:导出是 login-manager 的事,本 skill 不调用 `cookies export` / `identity export`。

---

## Pitfalls

### pitfall: douyin_login_required_on_creator_center

- **触发**:访问 `creator.douyin.com` 未登录态
- **症状**:页面跳到 `creator.douyin.com/login` 或出现登录弹窗
- **workaround**:脚本返回 `exit 2`(session 失效),由调用方走 **login-manager 有头手动重登流**,不在本 skill 内自管重登。

### pitfall: real_name_auth_required

- **触发**:未实名认证的账号
- **症状**:创作者中心提示"请先完成实名认证"才能发布
- **workaround**:用户自己走实名认证流程(脚本帮不上)

### pitfall: video_too_long_or_wrong_format

- **触发**:上传非 mp4 / mov 格式,或视频时长超限
- **症状**:上传后转码失败 / 客户端拒收
- **workaround**:转 mp4 + 检查时长(抖音支持最长 15 分钟)

### pitfall: dom_changes_creator_center

- **触发**:抖音创作者中心前端改版
- **症状**:selector 找不到(input / button 位置变化)
- **workaround**:部署后真机验证更新 selector(见 `docs/post-deploy-verification.md`)

### pitfall: upload_transcode_timeout

- **触发**:视频上传后转码超时(大文件 / 网络波动)
- **症状**:`camoufox_wait_for_selector` 轮询标题表单超时,脚本报 `视频上传/转码超时（标题表单未出现）`
- **workaround**:检查视频大小(建议 < 100MB);超时后截图排查是 DOM 改版还是转码慢;确认 DOM 已渲染后可用分步命令(`fill` / `publish`)手动继续

### pitfall: ai_declaration_confirm

- **触发**:选完自主声明"内容由AI生成"后未点"确定"按钮
- **症状**:声明弹窗卡住,发布按钮被遮挡,无法点发布
- **workaround**:`fill` 命令已内置点"确定"步骤;分步手动操作时需注意选完声明后必须点"确定"

### pitfall: rate_limit_after_burst_publish

- **触发**:短时间内连续发布多条
- **症状**:平台风控 / 上传被拒 / 提示"操作过于频繁"
- **workaround**:每天 ≤ 5 条;触发后 30 分钟内不重试

---

## Notes

- Docker 内对内 crew exec full(无 allowlist 限制)
- 限频建议:单抖音号每 24h ≤ 5 条发布;触发风控立即降级
- 失败回退:浏览器模拟失败 → 维持现状(让用户自己手动发)
- 抖音创作者中心 DOM 改版频繁:selector 需部署后真机验证(见 `docs/post-deploy-verification.md`)
