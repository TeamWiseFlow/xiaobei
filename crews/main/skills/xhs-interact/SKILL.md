---
name: xhs-interact
description: 小红书社交互动技能。发表评论、回复评论、点赞、关注。当用户要求评论、回复、点赞或关注小红书用户时触发。走 camoufox-cli 主推路径（反指纹 + 探活前置），browser-guide + login-manager skill 配合使用。
metadata:
  openclaw:
    emoji: 💬
    requires:
      bins:
      - camoufox-cli
---

# 小红书社交互动

通过 **camoufox-cli** 持久化 session（`xhs`，一个且只有一个持久化 session，fail-first 队列：同 session 已有命令在跑时新命令直接 fail）代替用户在小红书（xhs）上完成社交互动。

**前提条件**：先通过 login-manager skill 拿到有效 cookie + UA（详见 login-manager SKILL.md）：
1. 开持久化 session `xhs-browse` 探活：`camoufox-cli --session xhs-browse --persistent --headless --json open "https://www.xiaohongshu.com/"` + `snapshot` 看是否跳登录页
2. 跳登录页 = 失效 → 启**有头** session：`camoufox-cli --session xhs-browse --persistent --headed --json open "https://www.xiaohongshu.com/"`，告知用户在窗口里手动扫码登录，完成后**同时导出 cookie + UA**：
   - `camoufox-cli --session xhs-browse --persistent --json cookies export ~/.openclaw/logins/xhs-browse.json`
   - `camoufox-cli --session xhs-browse --persistent --json identity export ~/.openclaw/logins/xhs-browse.ua.json`
3. 关 session：`camoufox-cli --session xhs-browse --json close`

> **同时导入 cookie 和 UA**（原则 4，spec §4.2）：xhs 的 `a1`/`websectiga` 等设备指纹 cookie 必须配同一指纹的 UA，否则被风控错配。

---

## 启动一个互动用 camoufox session

每个互动任务用独立临时 session（不要复用 `xhs-browse` 持久化 session 名，fail-first 会冲突）：

```bash
SESSION="xhs-interact-$(date +%s)-$$"
# 启 session 并导入中央 cookie（camoufox-cli cookies import 格式与 cookies export 对称，零转换）
camoufox-cli --session "$SESSION" --persistent --headless --json open "https://www.xiaohongshu.com/"
camoufox-cli --session "$SESSION" --persistent --json cookies import ~/.openclaw/logins/xhs-browse.json
```

任务结束**必须 cleanup**：

```bash
camoufox-cli --session "$SESSION" --json close
```

> ⚠️ **不要**重复使用同一 session 名；不同 agent / 不同任务共享 session 会污染 cookie state + 触发风控。

---

## 获取 feed_id 和 xsec_token

所有互动操作需要 `feed_id` 和 `xsec_token`，从浏览器地址栏获取（snapshot eval）：

```
笔记 URL 格式：
https://www.xiaohongshu.com/explore/{feed_id}?xsec_token={xsec_token}&xsec_source=pc_feed

示例：
https://www.xiaohongshu.com/explore/64abc123def456?xsec_token=ABxxxxxx&xsec_source=pc_feed
→ feed_id    = 64abc123def456
→ xsec_token = ABxxxxxx
```

camoufox 拿当前 URL：
```bash
camoufox-cli --session "$SESSION" --json eval "window.location.href"
```

---

## 必做约束

- 批量操作时每次之间保持 30-60 秒间隔，避免风控。
- 每天评论不超过 20 条。
- 互动前用 `camoufox-cli eval` 验 cookie 有效（页面 snapshot 不出 `.login-container` / 不 redirect 到 login）。

---

## Feed 详情页 URL 格式

```
https://www.xiaohongshu.com/explore/{feed_id}?xsec_token={xsec_token}&xsec_source=pc_feed
```

---

## 工作流程（camoufox-cli 版本）

> **模式说明**：以下每条操作都用 `camoufox-cli` 的 `snapshot` / `eval` / `click` / `type` 子命令实现。`$SESSION` 为上文启动的 session 名。
>
> 找不到元素时**不要**盲试：先 `snapshot` 看 DOM 真实结构，再决定 selector 改写。

### 发表评论

```
1. 导航到 feed 详情页：
   camoufox-cli --session "$SESSION" --persistent --headless open <feed_url>
2. 等待 2-3 秒加载（sleep 3），调 snapshot 看 .access-wrapper / .error-wrapper
   是否出现 → 出现则笔记不可访问，停止并告知用户
3. 找评论输入框 .content-input，触发 input 事件（用 type 子命令）：
   camoufox-cli --session "$SESSION" --json type ".content-input" "评论内容"
4. 触发 input 事件（camoufox type 已隐含触发，确认 snapshot 看到值变化）
5. 找发送按钮并 click：
   camoufox-cli --session "$SESSION" --json click "<send-btn-selector>"
6. 等待 1-2 秒（sleep 2），调 snapshot 确认评论出现在评论区
```

### 回复评论

```
1. 导航到 feed 详情页（camoufox-cli open）
2. 等待 2-3 秒加载，确认页面可访问
3. 滚动到目标评论：
   - 已知 comment_id：eval "document.querySelector('#comment-${comment_id}').scrollIntoView()"
   - 已知 user_id：eval "document.querySelector('[data-user-id=\"${user_id}\"]').scrollIntoView()"
   - 若需滚动加载更多评论：eval 多次 window.scrollBy(0, 800) + sleep 1
     观察 .end-container 出现即到底（最多 7 次）
4. 点击目标评论的回复按钮（.interactions .reply）：
   camoufox-cli --session "$SESSION" --json click ".interactions .reply"
5. 输入回复内容到 .content-input（camoufox type 子命令）
6. 点击发送按钮（camoufox click）
7. sleep 1-2s，snapshot 确认回复已发出
```

### 点赞 / 取消点赞

**选择器**：`.like-wrapper`（推荐）或 `.interact-container .left .like-wrapper`

```
1. 导航到 feed 详情页
2. 等待 2-3 秒加载
3. 检查当前点赞状态（eval）：
   camoufox-cli --session "$SESSION" --json eval \
     "document.querySelector('.like-wrapper').classList.contains('like-active')"
4. 若需点赞，click 点赞按钮（推荐 JS 方式，最稳）：
   camoufox-cli --session "$SESSION" --json eval \
     "document.querySelector('.like-wrapper').click(); 'ok'"
5. sleep 1-2s，eval 验状态：
   camoufox-cli --session "$SESSION" --json eval \
     "document.querySelector('.like-wrapper').classList.contains('like-active')"
6. 若状态未变化，重试一次；仍失败则报告
```

> 若 `click` / `eval` 触发风控：先 teardown 当前 session（`camoufox-cli --session "$SESSION" --json close`），等 60s 后开新 session 重试；仍触发则报告用户该平台当日风控未解，转其他笔记或择日再试。

### 关注 / 取关

#### 关注用户

```
1. 导航到用户主页：camoufox-cli ... open "https://www.xiaohongshu.com/user/profile/${user_id}"
2. sleep 3 加载
3. 找关注按钮：snapshot 找文本为"关注"的按钮 / eval ".user-actions .follow-btn"
4. click 关注按钮
5. sleep 1-2s，snapshot 确认按钮变为"已关注"
```

#### 取关用户

```
1. 导航到用户主页
2. 找"已关注"按钮（同上 selector）
3. click 后确认弹出确认框，click"取消关注"
4. sleep 1-2s，确认按钮变为"关注"
```

---

## Pitfalls

### pitfall: xsec_token_required

- **触发**：手拼 `/explore/{feed_id}` 裸路径，没带 `xsec_token`
- **症状**：页面 403 或 redirect 到错误页（`error_code=300017` 或 `300031`）
- **workaround**：feed_id + xsec_token **必须从搜索结果/笔记列表的链接中提取**，不能手拼 URL。如果只有 feed_id，先搜索对应笔记获取 signed URL

### pitfall: like_count_compressed_format

- **触发**：读取点赞数时
- **症状**：显示 `2.1w`、`1.5万`、`1.2k` 等压缩格式而非数字
- **workaround**：解析规则：`w` = 万 = ×10000，`万` = ×10000，`k` = ×1000。例：`2.1w` = 21000，`1.5万` = 15000，`1.2k` = 1200

### pitfall: security_block_on_repeated_access

- **触发**：短时间高频互动（连续点赞/评论多个笔记）
- **症状**：页面显示"安全限制"/"访问链接异常"
- **workaround**：每次操作间隔 30-60 秒；触发后 60s 内不重试

### pitfall: comment_section_lazy_load

- **触发**：需要找到较早的评论
- **症状**：评论未出现在 DOM 中
- **workaround**：逐段向下滚动加载（eval window.scrollBy + sleep），每次滚动后等待 0.5-1 秒；到达 `.end-container` 说明到底部；最多滚动 7 次

### pitfall: creator_center_is_different_host

- **触发**：在主站 `www.xiaohongshu.com` 找发布/草稿入口
- **症状**：主站无完整创作者功能
- **workaround**：创作者相关操作（查看草稿、创作者数据）需访问 `creator.xiaohongshu.com`

### pitfall: camoufox_session_leak

- **触发**：任务结束未调 `session-cleanup`，daemon 残留
- **症状**：下次启动同一 session 名冲突，cookie state 污染
- **workaround**：每个互动任务**必须**三步走——`cookie-import` → 操作 → `session-cleanup`；不要跨任务复用 session 名

### pitfall: cookie_expired_during_interaction

- **触发**：互动过程中小红书 session 过期
- **症状**：页面突然 redirect 到 login / 互动操作 401
- **workaround**：立即 `close` 当前 session（`camoufox-cli --session "$SESSION" --json close`）→ 重走 login-manager 有头登录流（导出 cookie+UA）→ 开新 session 重试；不要盲 retry 当前 session

---

## 错误处理

| 情况 | 处理 |
|------|------|
| cookie 失效（`login-manager check xhs-browse` exit 2） | 重走 login-manager 有头登录流（导出 cookie+UA）→ 重启 session |
| 页面出现登录墙 | 同上重走 login-manager 登录流 |
| 点赞状态未变化 | 重试一次，仍未变化则报告错误 |
| camoufox click/eval 失败 / 超时 | 改用 `eval` 走 JS 方式（最稳）；再失败 → teardown session 等 60s 开新 session 重试 |
| xsec_token 缺失/无效 | 从搜索结果链接中重新获取 signed URL，不要手拼 |
| 安全限制/访问异常 | 停止操作 60 秒后重试，或换笔记操作 |
| camoufox daemon 残留 | `camoufox-cli close --all` 兜底清掉；下个任务开新 session |
