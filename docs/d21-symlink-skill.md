# D21 全局技能软链化 + Wrapper 覆盖审计

> 2026-07-04 · DEVPLAN §Phase 7 续 D21 · **状态：设计阶段；本轮仅文档化，实例软链化与 wrapper 补齐等部署阶段统一处理**。
>
> 背景：当前 `~/.openclaw/skills/` 是**拷贝**（改 repo 要 reinstall）；弱模型路径拼接错主要来自 baseDir 拼接 + allowlist miss。D19 已消掉 allowlist miss（内 crew T3 full），剩"拼错绝对路径"靠 wrapper 上 PATH 解。

## 一、问题

### 1.1 当前路径（拷贝模式）

```
本仓:    skills/browser-guide/                 → /home/wukong/.openclaw/skills/browser-guide/ (拷贝)
部署时:  apply-addons.sh cp -r skills/X/ → ~/.openclaw/skills/X/
```

**问题**：改 repo 里的 `SKILL.md` 或 `scripts/foo.py` → 实例不更新，要 reinstall。
**影响**：开发期反复 reinstall，部署期镜像重建才更新。

### 1.2 弱模型路径拼接错

agent 调 skill 时需拼绝对路径：
```bash
python3 /home/wukong/.openclaw/workspace-main/skills/login-manager/scripts/login-manager.sh check douyin
```

弱模型（小参数模型）拼错路径很常见：
- 漏 `workspace-` → 拼到 `~/.openclaw/skills/`
- 漏 `<crew>/` 段 → 路径无效
- 错位 `login_manager.py` vs `login-manager.sh`（下划线 vs 短横线）

**影响**：exec denied（路径无效）、`No such file`、错误地调到其他 skill 的脚本。

---

## 二、目标

1. **本地开发实例软链化**：改 repo 立即生效，告别 reinstall 循环
2. **Wrapper 覆盖审计**：每个常用 skill 都有 `<skill>.sh` wrapper，agent 调 `<skill> <cmd>` 零路径拼接
3. **Docker 镜像维持 COPY**（重建即更新，软链无收益）
4. **不**软链到 `openclaw/skills`（bundled）——会降优先级 + 耦合版本树 + 不治路径错

---

## 三、软链化方案

### 3.1 本地开发实例（部署后做）

```bash
# 公共技能
for s in ~/wiseflow/skills/*/; do
    sname=$(basename "$s")
    ln -sfn "$s" "$HOME/.openclaw/skills/$sname"
done

# crew 私有技能（按 workspace）
for crew in main content-producer it-engineer sales-cs; do
    for s in ~/wiseflow/crews/$crew/skills/*/; do
        sname=$(basename "$s")
        ln -sfn "$s" "$HOME/.openclaw/workspace-$crew/skills/$sname"
    done
done
```

**注意**：
- 软链到本仓 `~/wiseflow/skills/<name>`（**不**软链到 `openclaw/skills` bundled）
- 软链本身是 Linux filesystem 操作，**不**走 openclaw 配置
- 重新 `apply-addons.sh` 跑时**保留**软链（脚本里要跳过已存在 symlink，**不** rm -rf 后 cp）

### 3.2 Docker 镜像（维持 COPY）

```dockerfile
# Dockerfile wiseflow-layer 阶段（dev plan §Phase 6）
COPY skills/ /root/.openclaw/skills/
COPY crews/main/skills/ /root/.openclaw/workspace-main/skills/
COPY crews/content-producer/skills/ /root/.openclaw/workspace-content-producer/skills/
COPY crews/it-engineer/skills/ /root/.openclaw/workspace-it-engineer/skills/
# sales-cs 默认不 COPY（用户启用时由 it-engineer 单独处理）
```

**为何不软链**：容器内 `~/wiseflow` 不存在（代码 COPY 进镜像）；软链目标失效。

### 3.3 排除项

**不**软链到 `openclaw/skills`（bundled）：

```bash
# ❌ 不要这样做
ln -sfn ~/wiseflow-pro/openclaw/skills/email-ops ~/.openclaw/skills/email-ops
```

**理由**：
- 降优先级：openclaw bundled skill 优先级低于用户 skill；如果软链到 bundled，覆盖了 bundled 的版本
- 耦合版本树：openclaw 升级会换 skill 版本，本仓 skill 跟版本树绑死
- 不治路径错：bundled skill 路径错是 openclaw bug，应在 openclaw 修复，不是绕过

---

## 四、Wrapper 覆盖审计

### 4.1 Wrapper 是什么

skill 顶层（`skills/<name>/<name>.sh`）放一个**薄壳 wrapper**，代理到 `scripts/xxx.py`。agent 调：

```bash
# 之前（要拼绝对路径）
python3 ~/.openclaw/workspace-main/skills/login-manager/scripts/login-manager.sh check douyin

# 之后（PATH 友好）
login-manager check douyin   # wrapper 在 PATH 中
```

### 4.2 现状（2026-07-04 审计）

| 类别 | skill 数 | 有顶层 wrapper | 缺 wrapper |
|------|---------|---------------|----------|
| 公共技能（skills/）| 10 | 0 | 10（全部缺）|
| crew main 私有 | 32 | 0 | 32（全部缺；login-manager / published-track / wx-mp-hunter 等虽 SKILL.md 写绝对路径，仍无 wrapper）|
| crew content-producer | 8 | 0 | 8 |
| crew it-engineer | 7 | 0 | 7 |
| crew sales-cs | 5 | 0 | 5 |

**全部 62 个 skill 都没有顶层 wrapper**。但**SKILL.md 写绝对路径**的 skill 有 ~10 个（一致性较好）。

### 4.3 实施计划（部署阶段）

按 dev plan §Phase 7 续 写"常用 skill 没 wrapper 的加上"——本轮不做（部署时统一处理）。

**优先 P0 列表**（最常用 + 风险最高）：

| 优先级 | skill | 理由 |
|-------|-------|------|
| P0 | `login-manager` | 9 子命令，cookie 状态机核心；agent 高频调用 |
| P0 | `published-track` | 发布记录 1B + 复盘主入口；心跳任务 |
| P0 | `bilibili-publish` / `douyin-publish` | 发布技能，路径错会发到错平台 |
| P1 | `xhs-content-ops` / `xhs-interact` / `xhs-publish` | 小红书三件套，BD 高频 |
| P1 | `viral-chaser` | 追爆分析 + 视频生成入口 |
| P1 | `content-calibrator` | 打分 + 预测 |
| P2 | `investor-pipeline` / `business-model-polish` | IR 三模式入口 |
| P2 | `wx-mp-hunter` / `wx-mp-engagement` | 公众号相关 |
| P3 | 其他 50+ skill | 按需补齐 |

**Wrapper 模板**（以 login-manager 为例）：

```bash
#!/usr/bin/env bash
# skills/login-manager/login-manager.sh
# Wrapper：让 agent 用 `login-manager <cmd>` 调脚本，零路径拼接
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/scripts/login-manager.sh" "$@"
```

部署时把 wrapper 加到 `~/.openclaw/bin/login-manager`（软链到 `skills/login-manager/login-manager.sh`），让 `login-manager` 在 PATH 中。

### 4.4 验收标准

dev plan §Phase 7 续 写"验收"：
- [ ] 本地实例改 repo skill 即时生效（软链化）
- [ ] 常用 skill 均有 wrapper（P0 全部，P1 半数）
- [ ] 弱模型路径相关 exec 失败近零（部署后观察 1 周）

---

## 五、与 D19 / D20 关系

- **D19**（内 crew T3 full）：消除 allowlist miss，本任务假设已落地
- **D20**（skill 依赖）：镜像预装常用包；D21 软链化与 D20 独立
- **D21**（本任务）：软链 + wrapper，不影响 D19 / D20

---

## 六、变更历史

- **2026-07-04**：本任务在 dev plan §Phase 7 续 标注。文档化完成；实例软链化 + wrapper 补齐等部署阶段做。

---

## 七、本轮交付

- ✅ 本 doc（设计 + 审计 + 实施计划）
- ⏸️ 实际软链化（部署阶段做，本机实例本轮不动）
- ⏸️ Wrapper 补齐（部署阶段做，~62 skill 需补 P0 8 个 + P1 4 个 + P2 4 个）

按 dev plan §Phase 7 续"D21 全局技能软链化 + wrapper 覆盖审计"——本任务**文档化完成**；实施待部署阶段。

关联：`docs/browser-stack-replacement-spec-2026-07.md` §11 · `crews/it-engineer/MEMORY.md` D20
