# OpenCLI v1.8.6 借鉴分析（2026-07-05）

> **背景**：本轮已借鉴 v1.8.2（per-category source guides，#46 完成）。本报告分析 **v1.8.4 / v1.8.5 / v1.8.6** 3 个新 release 的**值得借鉴**变更。
>
> **架构约束不变**（dev plan §3.0 / memory 02-upstream-sources.md）：OpenCLI 走**浏览器扩展 + page.evaluate**，xiaobei 走 **camoufox-cli + CDP**。**不搬代码**，只吸收 design pattern。

## 一、v1.8.4-1.8.6 关键变更

### v1.8.6（2026-07-03）— 最新，**最相关**

```
fix(browser): end-to-end command deadlines, safe transport retries, CDP timeouts
refactor(transport): exactly-once command transport — journal, waiters, absolute deadlines
fix(extension): preserve network capture across ensureAttached re-attach
fix(core): stop silently swallowing pipeline context + daemon WS errors
fix(weibo): resolve uid before the full auth probe to avoid HTTP 400
fix(twitter): match localized delete menu + poll for late-hydrating article
chore(extension): bump to 1.0.21
```

### v1.8.5（mid-2026）

```
~40+ adapter fixes (B站付费内容 / 小红书 hydration / Twitter API 错误翻译)
feat(archive): Internet Archive read-only adapter
feat(semanticscholar): Semantic Scholar academic graph adapter
feat(chatgpt): project commands
feat(smzdm): 什么值得买 search interaction metrics
feat(linkedin): messaging + Sales Navigator 整合
feat(juejin): 掘金 read-only adapter
feat(xianyu): 闲鱼 inbox/messages/reply
feat(adapter): Mercury reimbursement helpers
feat(gemini): model + thinking selection
```

### v1.8.4（mid-2026）

```
feat(auth): login/whoami for 50 sites in one batch + aggregate status + refresh
feat(linkedin): consolidate profile, jobs, posts, projects
feat(xiaohongshu): 评论 userId / profileUrl + follow/unfollow + paginate past 10-row cap
feat(slock): Slock collaboration adapter (messages, channels, tasks)
chore(release): 1.8.4
```

---

## 二、对 xiaobei 借鉴分析

### 2.1 强相关：v1.8.6 命令可靠性 / 超时模式

**v1.8.6 核心模式**：

```python
# OpenCLI 模型（伪代码）
def execute_command(cmd, deadline_absolute_ms, retry_policy):
    """End-to-end command with hard deadline + safe retry + journal."""
    start = monotonic_ms()
    
    # Journal: 记录所有尝试
    journal = []
    for attempt in range(retry_policy.max_attempts):
        try:
            result = await transport.execute(cmd, timeout=deadline_absolute_ms - (monotonic_ms() - start))
            journal.append({"attempt": attempt, "ok": True, "elapsed_ms": ...})
            return result, journal
        except DaemonWSError as e:
            journal.append({"attempt": attempt, "ok": False, "error": e})
            if monotonic_ms() - start > deadline_absolute_ms:
                return ErrorResult("DEADLINE_EXCEEDED"), journal
            time.sleep(backoff(attempt))  # safe retry
    return ErrorResult("MAX_RETRIES"), journal
```

**本仓 camoufox-cli 调用现状**（`crews/main/skills/twitter-interact/scripts/twitter_interact.py`）：

```python
def camoufox_eval(session: str, js: str, timeout: int = 30) -> Optional[str]:
    cmd = [CAMOUFOX_BIN, "--session", session, "--json", "eval", js]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        env = json.loads(result.stdout)
        data = env.get("data")
        return data if isinstance(data, str) else json.dumps(data)
    except json.JSONDecodeError:
        return result.stdout
```

**缺口**：
1. **无绝对 deadline**：每个 `subprocess.run` 有独立 `timeout`，但没有"整个任务（如 login + 操作 + cleanup）的总时间硬约束"
2. **无 safe retry**：失败直接返回 None，没有 exponential backoff
3. **无 journal**：失败不记录，事后排查缺日志

**借鉴实施建议**（本轮不做，**记录到 Phase 6+**）：

```python
def camoufox_eval_with_reliability(
    session: str, js: str,
    *,
    timeout: int = 30,
    deadline_ms: int = 60_000,  # 整个任务硬 deadline
    max_retries: int = 2,
    backoff_base_s: float = 1.5,
) -> tuple[Optional[str], dict]:
    """End-to-end reliable eval with absolute deadline + safe retry + journal.
    
    Returns: (result, journal)
    journal keys: attempts[], elapsed_ms, error (if any), deadlined (bool)
    """
    start = monotonic_ms()
    journal = {"attempts": [], "error": None, "deadlined": False}
    
    for attempt in range(max_retries + 1):
        try:
            result = subprocess.run(
                [...], capture_output=True, text=True,
                timeout=min(timeout, (deadline_ms - monotonic_ms() + start) / 1000),
                check=False,
            )
            elapsed = monotonic_ms() - start
            journal["attempts"].append({"n": attempt, "elapsed_ms": elapsed, "rc": result.returncode})
            
            if result.returncode == 0 and result.stdout.strip():
                return _parse_stdout(result.stdout), journal
            
            # rc != 0 or empty → retry
            if elapsed + (backoff_base_s ** attempt) * 1000 > deadline_ms:
                journal["deadlined"] = True
                break
            time.sleep((backoff_base_s ** attempt) * 1000 / 1000)
        except subprocess.TimeoutExpired:
            elapsed = monotonic_ms() - start
            journal["attempts"].append({"n": attempt, "elapsed_ms": elapsed, "error": "TimeoutExpired"})
            if elapsed > deadline_ms:
                journal["deadlined"] = True
                break
            time.sleep(backoff_base_s ** attempt)
    
    journal["error"] = "MAX_RETRIES" if not journal["deadlined"] else "DEADLINE_EXCEEDED"
    return None, journal
```

**Phase 6+ 实施**（不本轮）：
1. 在 `crews/main/skills/login-manager/scripts/login_manager.py`（已是 Python 核心）加 reliable_eval helper
2. `crews/main/skills/twitter-interact/scripts/twitter_interact.py`（已有 27 单测）替换所有 camoufox_eval
3. 加 `journal` 字段到 `cmd_*.json` 输出，部署后做排故更清晰
4. `crews/main/skills/douyin-publish/scripts/publish_douyin.py` + `wx-mp-engagement/scripts/fetch_engagement.py` 同样替换

### 2.2 中等相关：v1.8.6 exactly-once command transport (journal)

**OpenCLI 模型**：
- 每条 command 有 **unique id**
- daemon 持久化 journal（已发送 + 已 ack）
- 新 client 接手时：检查 journal，避免重复发送
- absolute deadline：过期 entry 自动清理

**本仓类似**：
- `login-manager write_storage` 用 `temp + os.replace` 原子写（**已实现**）
- `twitter-interact record_action` 写 freq tracker（**已实现**）
- 缺：command-level journal（重发场景）

**借鉴**：
- 本仓**不需要** exactly-once（camoufox-cli 是同步的，单进程；不像 OpenCLI daemon 异步）
- 但**绝对 deadline** 概念值得借鉴（已见 2.1）

### 2.3 中等相关：v1.8.6 `fix(extension): preserve network capture across ensureAttached re-attach`

**OpenCLI 模型**：
- Browser 重新 attach 时（断线重连），保留 network capture 状态
- 不需要重新注册 capture handlers

**本仓**：
- camoufox session 跨 camoufox-cli 调用是独立的（`--session` 参数）
- 我们的"网络拦截"是**进程级**——每次启动新 camoufox process
- 借鉴**价值低**（架构不同）

### 2.4 中等相关：v1.8.6 `fix(core): stop silently swallowing pipeline context + daemon WS errors`

**OpenCLI 模型**：
- 之前：error 被 silently catch，log 写一半
- 现在：error **必须** propagate + 完整 stack trace

**本仓**：
- `crews/main/skills/twitter-interact/scripts/twitter_interact.py` 主入口已有 try/except → sys.exit(1)
- login-manager 同
- douyin-publish 同
- **本仓已基本做对**（exit code 1 + stderr message）

**借鉴**：
- 偶尔有 silent `pass` / 异常吞掉的地方需要审计
- **建议**（不本轮）：grep 一次 `crews/main/skills/*/scripts/*.py` 看有没有 `except: pass` 模式

### 2.5 中等相关：v1.8.5 大量 adapter 修复（40+）

**修复**（典型）：
- B 站付费内容 / 字幕 bangumi PGC bvid 支持
- 小红书 hydration 竞态
- Twitter API 错误翻译
- 知乎 numeric entities 解码
- 12306 endpoint rotation
- Reddit / Zhihu pagination
- ...

**对本仓借鉴价值**：
- 大量都是 **adapter-specific**（B站 / 小红书 / Twitter 各自的 DOM 改动）
- 我们的 camoufox 集成不走 OpenCLI 路径，**不直接受益**
- 但**设计模式**（如 hydration 竞态处理、API 错误翻译）可借鉴

**具体可借鉴**：
- **hydration 竞态**：小红书经常 SPA 切换路由后元素没 ready → 需 `waitForElement` helper
- **API 错误翻译**：OpenCLI 维护 `classifyFetchError` 工具（dev plan #38 patchright 也有类似 `classifyFetchError`）→ 本仓 camoufox 错误是字符串，没有结构化分类
- **pagination cursor**：增量游标 vs total — OpenCLI 多平台用 cursor，本仓 fetch-and-update-metrics.sh 是单次 fetch 拿全量（xhs/bilibili/douyin）

### 2.6 低相关：v1.8.5 新 adapter 30+

新增 adapter（Internet Archive / Semantic Scholar / Suno / Mercury / Juejin / Xianyu / Trae / Antigravity / CodeX / ChatGPT-app / Kimi / Qoder / NotebookLM / LinkedIn Learning / Booking / 12306 / 360 / etc.）

**对本仓**：
- 全部不集成（架构不兼容）
- 但有**借鉴概念**：
  - **NotebookLM**（AI 笔记集成）→ 对应 IR 模式 1（business-model-polish）相关
  - **Semantic Scholar**（学术图谱）→ 对应 IR 模式 1 + smart-search 学术分类
  - **Juejin**（掘金）→ 本仓 smart-search per-category 已有 "tech / juejin" 推荐

**借鉴**：
- smart-search per-category 源 guides 已写"tech / juejin"——OpenCLI v1.8.5 加了 juejin adapter 验证了"掘金是 tech 类值得搜"的判断
- NotebookLM / Semantic Scholar 可作 v2 增强

### 2.7 低相关：v1.8.4 `feat(auth): login/whoami for 50 sites in one batch + aggregate status`

**OpenCLI 模型**：
- 50+ 适配器**统一** `auth login` / `auth whoami` / `auth status` / `auth refresh` 命令
- 一条 `auth status` 查全部 50 个适配器的登录态

**本仓**：
- `login-manager status-all`（Phase 4.5.2 已实现）— 批量查所有平台 cookie
- 但**只查 cookie 文件存在**，**不**查实际登录态（需要 probe_platform HTTP 调用）

**借鉴**：
- 现状 status-all 够用（cookie 文件存在 = 登录态有效）
- 未来可加"active session probe"（类似 OpenCLI quickCheck）—— 但需要 HTTP probe 各种平台，工作量大
- **不本轮实施**

---

## 三、本轮建议动作

| 项 | 行动 | 时机 |
|---|------|------|
| **2.1 借鉴 v1.8.6 命令可靠性模式** | 写 `camoufox_eval_with_reliability` helper；`login_manager` + `twitter_interact` 等核心 skill 替换 | **Phase 6+**（随可靠部署一起做）|
| **2.5 借鉴 API 错误翻译** | 写 `classify_camoufox_error` helper | **Phase 6+**（或不实施）|
| **2.7 借鉴 auth aggregate** | 加 `login-manager status-all --probe` 模式（active HTTP probe）| **Phase 6+**（或不做）|
| **本轮不实施** | 上面所有 | — |

## 四、本轮落地（已做）

✅ patchright 升级 1.60.2 → 1.61.1（commit `7c35ed1`）
✅ 写本借鉴分析 doc

## 五、长期观察

- OpenCLI v1.8.7+ 持续观察
- v1.8.x → v1.9 / v2.0 重大变更时启动新一轮 catchup

---

关联：
- `docs/upstream-catchup-2026-07.md`（6 上游综合 catchup 报告）
- `docs/ai-catchup-2026-07-twitter-and-search.md`（AiToEarn Twitter + OpenCLI smart-search 借鉴）
- `memory/02-upstream-sources.md`（上游来源表）
- `memory/30-client-dev-session-2026-07-04.md`（本轮开发约束）
- `memory/40-wiseflow-pro-sandbox.md`（借鉴项目代码仓规则）
