# D21 全局技能软链化 + Wrapper 覆盖审计

> 2026-07-04 · DEVPLAN §Phase 7 续 D21 · **2026-07-12 更新：软链化已在 `apply-addons.sh` / `crew-workspaces.sh` 落地；本轮交付薄转发 wrapper 30 个 + wrapper 暴露到 `~/.openclaw/bin/`**。
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

### 3.1 本地开发实例（已落地）

`apply-addons.sh` 第 305-314 行已对公共 `skills/` 做 `ln -s` 软链到 `~/.openclaw/skills/<name>`；`scripts/lib/crew-workspaces.sh` 的 `sync_crew_skills` 对 crew `crews/<id>/skills/` 做软链到 `~/.openclaw/workspace-<id>/skills/<name>`。**软链化已完成**，本节保留作历史记录。

```bash
# 公共技能（apply-addons.sh 已跑）
for s in ~/wiseflow/skills/*/; do
    sname=$(basename "$s")
    ln -sfn "$s" "$HOME/.openclaw/skills/$sname"
done

# crew 私有技能（sync_crew_skills 已跑）
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
- `apply-addons.sh` 现走 `rm -rf + ln -s` 幂等重建（已是 symlink 时重建无害）；`sync_crew_skills` 同幂等
- openclaw skill loader 跟随软链（`local-loader.ts` readdirSync isDirectory + realpathSync）

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

### 4.2 现状（2026-07-12 复审）

**skill 按脚本入口形态三类**：

| 类别 | skill 数 | wrapper 策略 | 落 wrapper 数 |
|------|---------|------------|--------------|
| **A. 纯指导**（无 scripts/）| 25 | **不加 wrapper**（没脚本可代理）| 0 |
| **B. 单一入口**（scripts 下就一个执行脚本，或 SKILL.md 只调一个同名脚本）| 30 | **薄转发 wrapper** `<skill>/<skill>.sh` → `scripts/<entry>` | **30（全落）** |
| **C. 多并列脚本**（scripts 下多个并列脚本，按子命令选）| ~8 | **暂不加**（分发器 wrapper 引入新方言、agent 还要学；现状 SKILL.md 已写清 `./skills/<name>/scripts/<file>.sh` 绝对路径，CLAUDE.md 也强制绝对路径写法）| 0 |
| **合计** | ~63 | — | 30 |

**A 类清单（25 个纯指导，不加 wrapper）**：browser-guide、complex-task、council、smart-search、web-form-fill、login-manager（⚠️ 原文档错列 P0 wrapper，无脚本可包）、intel-gathering、investor-hunting、investor-materials、investor-outreach、investor-pipeline、lead-hunting、market-research、project-application、twitter-post、wechat-channels-publish、weibo-publish、xhs-interact、xianyu-ops、zhihu-publish、ui-demo、seo、tccli、alicloud-find-skills、demo-send、`_shared`。

**B 类清单（30 个薄转发 wrapper，2026-07-12 全落）**：

| skill | entry 脚本 | 转发链 |
|-------|----------|--------|
| email-ops | scripts/send_email.py | wrapper → py |
| pexels-footage | scripts/pexels_search.py | wrapper → py |
| pixabay-footage | scripts/pixabay_search.py | wrapper → py |
| siliconflow-img-gen | scripts/gen.py | wrapper → py |
| wxwork-drive | scripts/drive.py | wrapper → py |
| youtube-publish | scripts/publish_youtube.py | wrapper → py |
| bilibili-publish | scripts/publish_bilibili.py | wrapper → py |
| design-system-picker | scripts/pick.sh | wrapper → sh |
| init-workspace | scripts/init.sh | wrapper → sh |
| manim-explainer | scripts/render-manim.sh | wrapper → sh |
| siliconflow-tts | scripts/tts.py | wrapper → py |
| siliconflow-video-gen | scripts/gen.py | wrapper → py |
| awada-channel-setup | scripts/apply-awada-config.py | wrapper → py |
| icp-exemption | scripts/generate_pdf.py | wrapper → py |
| icp-filing | scripts/icp.sh | wrapper → sh |
| exp-invite | scripts/invite.sh | wrapper → sh |
| proactive-send | scripts/send.sh | wrapper → sh → mjs |
| douyin-publish | scripts/publish_douyin.sh | wrapper → sh → py（scripts 里已有内部 wrapper，顶层只多一跳）|
| twitter-interact | scripts/twitter_interact.sh | wrapper → sh → py |
| wx-mp-engagement | scripts/wx-mp-engagement.sh | wrapper → sh → py |
| wx-mp-hunter | scripts/wx-mp-hunter.sh | wrapper → sh → ts |
| viral-chaser | scripts/viral_chaser.sh | wrapper → sh → ts |
| xhs-content-ops | scripts/fetch_note_content.sh | wrapper → sh → ts |
| xhs-publish | scripts/publish_xhs.py | wrapper → py |
| wx-mp-publisher | scripts/publish_wx_mp.py | wrapper → py |
| wxwork-moments | scripts/post_moments.py | wrapper → py |
| generate-wenyan-theme | scripts/collect-theme-sources.js | wrapper → js |
| rss-reader | scripts/fetch-rss.mjs | wrapper → mjs |
| sales-cs-enablement | scripts/symlink_business_knowledge.py | wrapper → py |
| sales-cs-review | scripts/scan_feedback.py | wrapper → py |

**C 类清单（多并列脚本，暂不加分发器 wrapper，维持 SKILL.md 绝对路径调用）**：bd-record（5）、info-record（4）、ir-record（11）、published-track（11）、content-calibrator（8）、work-channel-binding（7）、customer-db（7）、pitch-deck（3）、swcr-register（3）、video-product（6）、html-video（2，功能分裂）。

> **为何 C 类不加**：分发器 wrapper（`<skill> <subcmd> ...` 呺由到对应脚本）是为每个 skill 单定制分发表，引入新子命令方言、agent 还要学一套；现 SKILL.md 已把 `./skills/<name>/scripts/<file>.sh` 绝对路径写死（CLAUDE.md 也强制要求），多并列脚本那种靠 SKILL.md 路径明文已治拼错。分发器是未来可选演进，本轮不做。

### 4.3 实施落地（2026-07-12）

**本轮已落**：

1. **30 个 B 类薄转发 wrapper**：每个 `skills/<name>/<name>.sh`（或 `crews/<id>/skills/<name>/<name>.sh`），薄转发到 `scripts/<entry>`，零语义负担（`exec` 转发）。
2. **`scripts/lib/skill-wrappers.sh`** 新 lib 函数：
   - `expose_skill_wrappers <skills_root>`：扫根下每个含顶层 `<name>.sh` 的 skill，`ln -sfn` 一条 symlink 到 `~/.openclaw/bin/<name>`，幂等重建（现存 symlink / 真文件 / 不存在 三态都正确重建）。
   - `ensure_openclaw_bin_in_path`：把 `~/.openclaw/bin` 注入 `~/.zshrc` / `~/.bashrc` 的 `PATH`，幂等追加（存则跳过）。
3. **接入两处 symlink 落地**：
   - `apply-addons.sh`：公共 skill symlink 段后调 `expose_skill_wrappers "$PROJECT_ROOT/skills"` + `ensure_openclaw_bin_in_path`。
   - `crew-workspaces.sh` 的 `sync_crew_skills`：crew skill symlink 跑完顺手调 `expose_skill_wrappers "$src_skills"`（lazy source 避免循环依赖）。

**未落**：

- C 类多并列脚本分发器 wrapper（~8 个 skill，按需演进，本轮不做）。
- Docker 镜像内 wrapper 暴露：容器内 `~/wiseflow` 不存在，软链失效；走 `COPY` 时把 wrapper 一并 COPY + 容器 entrypoint 自管 PATH。本轮不动 Docker。

**Wrapper 模板**（以 email-ops 为例，薄转发 py）：

```bash
#!/usr/bin/env bash
# email-ops.sh — email-ops 顶层 wrapper（薄转发）
# 让 agent 用 `email-ops <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/send_email.py；wrapper 自身只是 exec 转发，不改语义。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/scripts/send_email.py" "$@"
```

部署后 `~/.openclaw/bin/email-ops` 软链到 `skills/email-ops/email-ops.sh`，`email-ops` 在 PATH 中。

### 4.4 验收标准

dev plan §Phase 7 续 写"验收"：
- [x] 本地实例改 repo skill 即时生效（软链化，`apply-addons.sh` + `sync_crew_skills` 已落）
- [x] B 类 30 个常用 skill 均有薄转发 wrapper（全落，含发布/追爆/公众号/小红书等高频）
- [x] wrapper 暴露到 `~/.openclaw/bin/`（`expose_skill_wrappers` 幂等，三态重建验证通过）
- [x] PATH 注入幂等（`ensure_openclaw_bin_in_path`，存则跳过）
- [ ] 弱模型路径相关 exec 失败近零（部署后观察 1 周）
- [ ] C 类分发器 wrapper（未来按需演进）

---

## 五、与 D19 / D20 关系

- **D19**（内 crew T3 full）：消除 allowlist miss，本任务假设已落地
- **D20**（skill 依赖）：镜像预装常用包；D21 软链化与 D20 独立
- **D21**（本任务）：软链 + wrapper，不影响 D19 / D20

---

## 六、变更历史

- **2026-07-04**：本任务在 dev plan §Phase 7 续 标注。文档化完成；实例软链化 + wrapper 补齐等部署阶段做。
- **2026-07-12**：软链化早已在 `apply-addons.sh` / `crew-workspaces.sh` 落地（原文档误判为待做）。本轮交付 30 个 B 类薄转发 wrapper + `scripts/lib/skill-wrappers.sh` lib（暴露到 `~/.openclaw/bin/` + PATH 注入）。纠正原文档将 `login-manager` 列为 P0 wrapper 的错误（无脚本可包）；"全部 62 skill 加 wrapper"设想纠正为按入口形态三分（A 纯指导不加 / B 单一入口薄转发 / C 多并列脚本暂不加）。

---

## 七、本轮交付（2026-07-12）

- ✅ 30 个 B 类薄转发 wrapper（公共 6 + crew main 13 + content-producer 6 + it-engineer 3 + sales-cs 2；具体清单见 §4.2）
- ✅ `scripts/lib/skill-wrappers.sh` 新 lib（`expose_skill_wrappers` + `ensure_openclaw_bin_in_path`）
- ✅ `apply-addons.sh` 接 lib：公共 skill symlink 后暴露 wrapper + PATH 注入
- ✅ `scripts/lib/crew-workspaces.sh` 的 `sync_crew_skills` 接 lib：crew skill symlink 后顺手暴露 wrapper
- ✅ 验证：bash 语法全过 / 转发目标全存在 / lib 隔离测三态幂等通过 / 实测 email-ops + viral-chaser wrapper 转发链路通
- ✅ 本 doc 现状纠正：login-manager 无脚本不应列 P0 wrapper；"62 全覆盖"设想纠正为"30 薄转发 + 25 纯指导不加 + ~8 多并列暂不加"
- ⏸️ C 类分发器 wrapper（未来按需演进）
- ⏸️ Docker 镜像内 wrapper 暴露（容器走 COPY，entrypoint 自管 PATH）

按 dev plan §Phase 7 续"D21 全局技能软链化 + wrapper 覆盖审计"——**软链化早已落地，本轮 wrapper 覆盖交付完成**；C 类分发器与 Docker wrapper 暴露留作未来演进。

关联：`docs/browser-stack-replacement-spec-2026-07.md` §11 · `crews/it-engineer/MEMORY.md` D20
