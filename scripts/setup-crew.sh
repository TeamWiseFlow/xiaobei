#!/bin/bash
# setup-crew.sh - 多 Agent 系统安装脚本
# 将 crews/ 中的内置模板、共享协议、模板库部署到 ~/.openclaw/
# 幂等设计：已存在的 workspace 不会覆盖（除非 --force）
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CREWS_DIR="$PROJECT_ROOT/crews"
ADDONS_DIR="$PROJECT_ROOT/addons"
OPENCLAW_HOME="$HOME/.openclaw"
CONFIG_PATH="$OPENCLAW_HOME/openclaw.json"
FORCE=false

# 内置 Crew（main / it-engineer）在 §4 中强制注册进 openclaw.json agents.list；
# content-producer 已在 config-templates/openclaw.json agents.list 预注册（§4 仅规范化）；
# 其余对外 crew（sales-cs / ...）的 workspace 在 §1 预建，运行时由 main agent 招募时注册。
source "$SCRIPT_DIR/lib/agent-skills.sh"
source "$SCRIPT_DIR/lib/exec-tiers.sh"
source "$SCRIPT_DIR/lib/crew-workspaces.sh"

DENIED_OVERRIDES=""

usage() {
  echo "Usage: $0 [--force] [--denied-skills <agent-id>:<skill1,skill2>]"
  echo ""
  echo "Options:"
  echo "  --force                              Overwrite existing workspace files"
  echo "  --denied-skills <agent-id>:<skills>  Override denied skills for one agent (internal crews only)"
  echo ""
  echo "Examples:"
  echo "  $0"
  echo "  $0 --force"
  echo "  $0 --denied-skills main:apple-notes,slack"
  echo "  $0 --denied-skills main:slack --denied-skills it-engineer:github,coding-agent"
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --force)
      FORCE=true
      shift
      ;;
    --denied-skills)
      [ -z "$2" ] && { echo "❌ --denied-skills requires <agent-id>:<skills>"; usage; }
      case "$2" in
        *:*)
          DENIED_OVERRIDES="${DENIED_OVERRIDES}
$2"
          ;;
        *)
          echo "❌ Invalid format for --denied-skills: $2"
          echo "   Expected: <agent-id>:<skill1,skill2>"
          exit 1
          ;;
      esac
      shift 2
      ;;
    *)
      echo "❌ Unknown option: $1"
      usage
      ;;
  esac
done

resolve_denied_override_for_agent() {
  local agent_id="$1"
  local line=""
  local key=""
  local value=""

  while IFS= read -r line; do
    [ -n "$line" ] || continue
    key="${line%%:*}"
    value="${line#*:}"
    if [ "$key" = "$agent_id" ]; then
      printf '%s\n' "$value"
      return
    fi
  done <<< "$DENIED_OVERRIDES"
}

resolve_builtin_file_for_agent() {
  local agent_id="$1"
  local workspace_dir="$2"

  local workspace_file="$workspace_dir/BUILTIN_SKILLS"
  if [ -f "$workspace_file" ]; then
    printf '%s\n' "$workspace_file"
    return
  fi

  # 兼容老版本已存在 workspace（未携带 BUILTIN_SKILLS 文件）：
  # 回退到仓库模板中的 BUILTIN_SKILLS 作为默认额外技能来源。
  local template_file="$CREWS_DIR/$agent_id/BUILTIN_SKILLS"
  if [ -f "$template_file" ]; then
    printf '%s\n' "$template_file"
    return
  fi

  printf '%s\n' "$workspace_file"
}

# resolve_crew_type 由 agent-skills.sh 提供（唯一权威实现）

resolve_template_crew_type() {
  local template_dir="$1"
  resolve_crew_type "$template_dir/SOUL.md"
}

resolve_addon_template_crew_type() {
  local addon_dir="$1"
  local template_id="$2"
  local addon_crew_lists=""
  local addon_crew_type=""

  addon_crew_lists="$(ADDON_JSON="${addon_dir%/}/addon.json" node -e "
    try {
      const fs = require('fs');
      const addon = JSON.parse(fs.readFileSync(process.env.ADDON_JSON, 'utf8'));
      const internal = Array.isArray(addon.internal_crews) ? addon.internal_crews : [];
      const external = Array.isArray(addon.external_crews) ? addon.external_crews : [];
      console.log(JSON.stringify({ internal, external }));
    } catch (_) {
      console.log(JSON.stringify({ internal: [], external: [] }));
    }
  " 2>/dev/null || echo '{"internal":[],"external":[]}')"

  addon_crew_type="$(ADDON_CREW_LISTS="$addon_crew_lists" TEMPLATE_ID="$template_id" node -e "
    const { internal, external } = JSON.parse(process.env.ADDON_CREW_LISTS || '{\"internal\":[],\"external\":[]}');
    const id = process.env.TEMPLATE_ID;
    if (internal.includes(id) && external.includes(id)) console.log('CONFLICT');
    else if (internal.includes(id)) console.log('internal');
    else if (external.includes(id)) console.log('external');
    else console.log('');
  " 2>/dev/null || echo "")"

  if [ "$addon_crew_type" = "CONFLICT" ]; then
    echo "❌ addon template $template_id listed in both internal_crews and external_crews" >&2
    return 1
  fi

  if [ -z "$addon_crew_type" ]; then
    addon_crew_type="external"
  fi

  printf '%s\n' "$addon_crew_type"
}

sync_addon_templates_to_runtime() {
  local target_type="$1"
  local dest_root="$2"
  local addon_dir=""
  local template_dir=""
  local template_id=""
  local addon_crew_type=""
  local runtime_template_dir=""

  [ -d "$ADDONS_DIR" ] || return 0

  for addon_dir in "$ADDONS_DIR"/*/; do
    [ -d "$addon_dir" ] || continue
    [ -f "${addon_dir}addon.json" ] || continue
    [ -d "${addon_dir}crew" ] || continue

    for template_dir in "$addon_dir"/crew/*/; do
      [ -d "$template_dir" ] || continue
      [ -f "${template_dir}SOUL.md" ] || continue

      template_id="$(basename "$template_dir")"
      addon_crew_type="$(resolve_addon_template_crew_type "$addon_dir" "$template_id")"
      [ "$addon_crew_type" = "$target_type" ] || continue

      runtime_template_dir="$dest_root/$template_id"
      rm -rf "$runtime_template_dir"
      copy_crew_template_contents "$template_dir" "$runtime_template_dir"
      ensure_soul_crew_type "$runtime_template_dir/SOUL.md" "$addon_crew_type"
    done
  done
}

sync_agent_skill_filter() {
  local agent_id="$1"
  local agent_override=""
  agent_override="$(resolve_denied_override_for_agent "$agent_id")"

  local workspace_dir=""
  workspace_dir="$(node -e "
    const fs = require('fs');
    const c = JSON.parse(fs.readFileSync('$CONFIG_PATH', 'utf8'));
    const agent = (c.agents?.list || []).find((entry) => entry.id === '$agent_id');
    const configured = typeof agent?.workspace === 'string' && agent.workspace.trim()
      ? agent.workspace.trim()
      : '~/.openclaw/workspace-$agent_id';
    console.log(configured.replace(/^~(?=\\/|$)/, process.env.HOME));
  " 2>/dev/null)"

  if [ -z "$workspace_dir" ] || [ ! -d "$workspace_dir" ]; then
    echo "  ⚠️  workspace for agent '$agent_id' not found, skip skill filter sync"
    return
  fi

  local denied_file="$workspace_dir/DENIED_SKILLS"
  local builtin_file=""
  builtin_file="$(resolve_builtin_file_for_agent "$agent_id" "$workspace_dir")"
  local skills_result=""
  skills_result="$(resolve_agent_skills_json \
    "$agent_id" \
    "$workspace_dir" \
    "" \
    "$builtin_file" \
    "$agent_override" \
    "$denied_file" \
    "$PROJECT_ROOT" \
    "$OPENCLAW_HOME")"

  # JSON 数组 → 写入明确的 allowlist
  AGENT_ID="$agent_id" AGENT_SKILLS_RESULT="$skills_result" node -e "
    const fs = require('fs');
    const c = JSON.parse(fs.readFileSync('$CONFIG_PATH', 'utf8'));
    const list = c.agents?.list || [];
    const idx = list.findIndex((entry) => entry.id === process.env.AGENT_ID);
    if (idx >= 0) {
      const skillsResult = process.env.AGENT_SKILLS_RESULT || '';
      list[idx] = { ...list[idx], skills: JSON.parse(skillsResult || '[]') };
      fs.writeFileSync('$CONFIG_PATH', JSON.stringify(c, null, 2) + '\\n');
    }
  "
}

# 输出 openclaw.json 中所有 agent 的 "id<TAB>workspace" 行（workspace 解析 ~ → $HOME）。
# 供 §4b/4b.5/4d/4e/4f 的 while 循环消费——原同一 node -e 块在此处之前重复了 5 次。
list_agent_workspaces() {
  node -e "
    const fs = require('fs');
    const home = process.env.HOME || '';
    const c = JSON.parse(fs.readFileSync('$CONFIG_PATH', 'utf8'));
    for (const a of (c.agents?.list || [])) {
      if (!a?.id) continue;
      const ws = (typeof a.workspace === 'string' && a.workspace.trim()
        ? a.workspace.trim() : ('~/.openclaw/workspace-' + a.id))
        .replace(/^~(?=\/|\$)/, home);
      console.log(a.id + '\t' + ws);
    }
  " 2>/dev/null
}

if [ ! -d "$CREWS_DIR" ]; then
  echo "❌ crews/ directory not found at $CREWS_DIR"
  exit 1
fi

# 检查是否应通过 apply-addons.sh 调用（确保 global skills 已安装到 openclaw/skills/）
CALLED_FROM_APPLY_ADDONS="${CALLED_FROM_APPLY_ADDONS:-false}"
if [ "$CALLED_FROM_APPLY_ADDONS" != "true" ] && [ -d "$ADDONS_DIR" ]; then
  addon_count="$(find "$ADDONS_DIR" -mindepth 2 -maxdepth 2 -name addon.json 2>/dev/null | wc -l)"
  if [ "$addon_count" -gt 0 ]; then
    echo "⚠️  检测到 $addon_count 个 addon，建议通过 apply-addons.sh 运行以确保 addon global skills 正确安装"
    echo "   直接运行 setup-crew.sh 可能导致 addon 提供的 global skills 未被纳入 crew 技能配置"
  fi
fi

echo "📦 Setting up Agent System (crews)..."

# ─── 1. 部署所有 Crew workspace（扫 crews/ 顶层，幂等） ──────────
# D8 扁平化后不再经 crew_templates/hrbp_templates 中转，直接把 crews/<id>/ 同步到
# ~/.openclaw/workspace-<id>/。已存在则跳过（保留用户编辑），仅做幂等 guide 注入。
# main / it-engineer 在 §4 中额外强制注册进 openclaw.json；content-producer 已在模板
# agents.list 预注册（§4 仅规范化其 skills / allowAgents）；sales-cs 等对外 crew 的
# workspace 在此预建，运行时由 main agent 招募时注册进 openclaw.json。
for agent_dir in "$CREWS_DIR"/*/; do
  [ -d "$agent_dir" ] || continue
  agent_dir="${agent_dir%/}"
  agent_id="$(basename "$agent_dir")"
  # 跳过脚手架模板与非合法目录
  [ "$agent_id" = "_template" ] && continue
  [ -f "$agent_dir/SOUL.md" ] || continue
  dest="$OPENCLAW_HOME/workspace-$agent_id"

  if [ -d "$dest" ] && [ "$FORCE" != "true" ]; then
    echo "  ⚠️  workspace-$agent_id already exists, keeping user files (use --force to overwrite)"
    # 仅做幂等注入（有标记则跳过，不覆盖用户编辑的内容）
    inject_file_edit_guide "$dest/TOOLS.md"
    inject_exec_guide "$dest/TOOLS.md" "$dest"
    inject_python_exec_guide "$dest/TOOLS.md"
    inject_agents_md_sections "$dest/AGENTS.md"
    inject_feishu_media_guide "$dest/USER.md"
    continue
  fi

  copy_crew_template_contents "$agent_dir" "$dest"
  # 安装有 package.json 的 skill 的 npm 依赖
  for skill_pkg in "$dest/skills"/*/package.json; do
    [ -f "$skill_pkg" ] || continue
    skill_dir="$(dirname "$skill_pkg")"
    skill_name="$(basename "$skill_dir")"
    echo "  📦 installing deps for skill: $skill_name"
    (cd "$skill_dir" && npm install --production --silent 2>/dev/null) || \
      echo "  ⚠️  npm install failed for skill: $skill_name" >&2
  done
  echo "  ✅ workspace-$agent_id installed"
  inject_file_edit_guide "$dest/TOOLS.md"
  inject_exec_guide "$dest/TOOLS.md" "$dest"
  inject_python_exec_guide "$dest/TOOLS.md"
  inject_agents_md_sections "$dest/AGENTS.md"
  inject_feishu_media_guide "$dest/USER.md"
done

# 注：原 §2/§3（shared 协议 / crew_templates / hrbp_templates 模板库同步）已移除。
# D8 扁平化 + 去 hrbp 化后 crews/shared/ 不存在、无 agent 消费 crew_templates/，
# 对外 crew 的 channel reply rules 注入改在 §4 对 workspace 直接做（见 inject_channel_reply_rules 调用）。

# ─── 4. 更新 openclaw.json（合并内置 Crew + skills 过滤） ────────
if [ -f "$CONFIG_PATH" ]; then
  echo "  📝 Merging agent config into openclaw.json..."

  # 规范化所有 agent workspace 路径
  OPENCLAW_HOME="$OPENCLAW_HOME" node -e "
    const fs = require('fs');
    const c = JSON.parse(fs.readFileSync('$CONFIG_PATH', 'utf8'));
    const openclawHome = process.env.OPENCLAW_HOME || (process.env.HOME + '/.openclaw');
    const currentHome = process.env.HOME || '';
    let changed = false;

    // 兼容旧模板误写：agents.defaults.model.imageModel 应迁移到 agents.defaults.imageModel.primary
    const defaults = c.agents?.defaults;
    if (defaults && defaults.model && typeof defaults.model === 'object' && !Array.isArray(defaults.model)) {
      const misplacedImageModel = defaults.model.imageModel;
      if (typeof misplacedImageModel === 'string' && misplacedImageModel.trim()) {
        if (!defaults.imageModel || typeof defaults.imageModel !== 'object' || Array.isArray(defaults.imageModel)) {
          defaults.imageModel = {};
        }
        if (!defaults.imageModel.primary) {
          defaults.imageModel.primary = misplacedImageModel.trim();
        }
        delete defaults.model.imageModel;
        changed = true;
      }
    }

    for (const agent of (c.agents?.list || [])) {
      if (typeof agent.workspace !== 'string') continue;
      const ws = agent.workspace.trim();
      if (ws.startsWith('~/')) {
        agent.workspace = openclawHome + ws.slice('~/.openclaw'.length);
        changed = true;
      } else if (ws.startsWith('/') && currentHome && !ws.startsWith(currentHome + '/') && ws !== currentHome) {
        const m = ws.match(/\/\.openclaw\/(workspace-[^/]+)\$/);
        if (m) {
          agent.workspace = openclawHome + '/' + m[1];
          changed = true;
        }
      }
    }
    if (changed) fs.writeFileSync('$CONFIG_PATH', JSON.stringify(c, null, 2) + '\n');
  " && echo "  ✅ Agent workspace paths normalized"

  MAIN_OVERRIDE="$(resolve_denied_override_for_agent "main")"
  IT_OVERRIDE="$(resolve_denied_override_for_agent "it-engineer")"
  MAIN_BUILTIN_FILE="$(resolve_builtin_file_for_agent "main" "$OPENCLAW_HOME/workspace-main")"
  IT_BUILTIN_FILE="$(resolve_builtin_file_for_agent "it-engineer" "$OPENCLAW_HOME/workspace-it-engineer")"

  MAIN_SKILLS_RESULT="$(resolve_agent_skills_json \
    "main" \
    "$OPENCLAW_HOME/workspace-main" \
    "" \
    "$MAIN_BUILTIN_FILE" \
    "$MAIN_OVERRIDE" \
    "$OPENCLAW_HOME/workspace-main/DENIED_SKILLS" \
    "$PROJECT_ROOT" \
    "$OPENCLAW_HOME")"
  IT_SKILLS_RESULT="$(resolve_agent_skills_json \
    "it-engineer" \
    "$OPENCLAW_HOME/workspace-it-engineer" \
    "" \
    "$IT_BUILTIN_FILE" \
    "$IT_OVERRIDE" \
    "$OPENCLAW_HOME/workspace-it-engineer/DENIED_SKILLS" \
    "$PROJECT_ROOT" \
    "$OPENCLAW_HOME")"

  MAIN_SKILLS_RESULT="$MAIN_SKILLS_RESULT" IT_SKILLS_RESULT="$IT_SKILLS_RESULT" OPENCLAW_HOME="$OPENCLAW_HOME" node -e "
    const fs = require('fs');
    const path = require('path');
    const c = JSON.parse(fs.readFileSync('$CONFIG_PATH', 'utf8'));
    const openclawHome = process.env.OPENCLAW_HOME || (process.env.HOME + '/.openclaw');

    const applySkills = (entry, skillsResult) => {
      return { ...entry, skills: JSON.parse((skillsResult || '[]').trim() || '[]') };
    };

    if (!c.agents) c.agents = {};
    if (!Array.isArray(c.agents.list)) c.agents.list = [];

    const upsertAgent = (id, buildNext) => {
      const idx = c.agents.list.findIndex((entry) => entry.id === id);
      const prev = idx >= 0 ? c.agents.list[idx] : {};
      const next = buildNext(prev);
      if (idx >= 0) c.agents.list[idx] = next;
      else c.agents.list.push(next);
    };

    const getCrewType = (id) => {
      if (id === 'main' || id === 'it-engineer') return 'internal';
      const agent = c.agents.list.find((entry) => entry.id === id);
      if (!agent) return 'external';
      const wsRaw = typeof agent.workspace === 'string' && agent.workspace.trim()
        ? agent.workspace.trim()
        : ('~/.openclaw/workspace-' + id);
      const ws = wsRaw.replace(/^~(?=\\/|$)/, process.env.HOME || '');
      const soulPath = path.join(ws, 'SOUL.md');
      try {
        const soul = fs.readFileSync(soulPath, 'utf8');
        const match = soul.match(/^crew-type:\\s*(internal|external)\\s*$/m);
        return match ? match[1] : 'external';
      } catch (_) {
        return 'external';
      }
    };

    upsertAgent('main', (prev) => {
      // Main Agent 只能 spawn 它招募的非内置 internal agent + it-engineer（固定）
      const BUILTIN_IDS = new Set(['main', 'it-engineer']);
      const prevAllowAgents = Array.isArray(prev?.subagents?.allowAgents) ? prev.subagents.allowAgents : [];
      const filteredAllowAgents = prevAllowAgents.filter(
        (id) => !BUILTIN_IDS.has(id) && getCrewType(id) === 'internal'
      );
      // it-engineer 固定追加：所有对内 crew 均可 spawn IT 协助执行任务
      const allowAgents = [...new Set([...filteredAllowAgents, 'it-engineer'])];
      const base = {
        ...prev,
        id: 'main',
        default: prev.default ?? true,
        name: prev.name || 'Main Agent',
        workspace: prev.workspace || openclawHome + '/workspace-main',
        // thinkingDefault 不显式设——main 继承 agents.defaults.thinkingDefault（medium）；
        // 若用户在 openclaw.json 手动给 main 设过则 prev 保留（...prev 已带）。
        reasoningDefault: 'off',
        subagents: {
          ...(prev.subagents || {}),
          allowAgents: allowAgents,
        },
      };
      return applySkills(base, process.env.MAIN_SKILLS_RESULT);
    });

    upsertAgent('it-engineer', (prev) => {
      const base = {
        ...prev,
        id: 'it-engineer',
        name: prev.name || 'IT Engineer',
        workspace: prev.workspace || openclawHome + '/workspace-it-engineer',
        thinkingDefault: 'high',
        reasoningDefault: 'off',
      };
      return applySkills(base, process.env.IT_SKILLS_RESULT);
    });

    // 为所有其他对内 Crew 实例也追加 it-engineer spawn 权限
    // （它们在 depth=1 时需要 maxSpawnDepth>=2，由 agents.defaults.subagents.maxSpawnDepth 保证）
    const PROTECTED_IDS = new Set(['main', 'it-engineer']);
    for (const agent of c.agents.list) {
      if (PROTECTED_IDS.has(agent.id)) continue;
      const crewType = getCrewType(agent.id);
      if (crewType === 'internal') {
        // 非内置对内 crew：确保 it-engineer 在 allowAgents 中
        const prevAllow = Array.isArray(agent.subagents?.allowAgents) ? agent.subagents.allowAgents : [];
        if (!prevAllow.includes('it-engineer')) {
          agent.subagents = {
            ...(agent.subagents || {}),
            allowAgents: [...new Set([...prevAllow, 'it-engineer'])],
          };
        }
        if (!agent.reasoningDefault) agent.reasoningDefault = 'off';
      } else {
        if (!agent.reasoningDefault) agent.reasoningDefault = 'off';
      }
    }

    // 为所有 Agent 追加自身 ID 到 allowAgents，确保显式 self-spawn 合法
    // （隐式 self-spawn 不传 agentId 时本就放行，但 agent 常显式传入自身 ID，
    //   此时必须通过 allowlist 检查，否则会被拒绝）
    for (const agent of c.agents.list) {
      if (!agent.id) continue;
      const prevAllow = Array.isArray(agent.subagents?.allowAgents) ? agent.subagents.allowAgents : [];
      if (!prevAllow.includes(agent.id)) {
        agent.subagents = {
          ...(agent.subagents || {}),
          allowAgents: [...new Set([...prevAllow, agent.id])],
        };
      }
    }

    // 默认确保微信 onboarding 入口存在；工作 channel 由 main agent 后续引导绑定。
    if (!Array.isArray(c.bindings)) c.bindings = [];
    const hasMainWeixin = c.bindings.some((binding) =>
      binding?.agentId === 'main' && binding?.match?.channel === 'openclaw-weixin'
    );
    if (!hasMainWeixin) {
      c.bindings.push(
        { agentId: 'main', comment: 'openclaw-weixin -> Main Agent onboarding entry', match: { channel: 'openclaw-weixin' } }
      );
    }

    fs.writeFileSync('$CONFIG_PATH', JSON.stringify(c, null, 2) + '\\n');
  "

  # 同步所有已注册 agent 的技能过滤
  AGENT_IDS="$(node -e "
    const fs = require('fs');
    const c = JSON.parse(fs.readFileSync('$CONFIG_PATH', 'utf8'));
    console.log((c.agents?.list || []).map((entry) => entry.id).join('\\n'));
  " 2>/dev/null)"
  while IFS= read -r agent_id; do
    [ -n "$agent_id" ] || continue
    sync_agent_skill_filter "$agent_id"
  done <<< "$AGENT_IDS"
  echo "  ✅ Agent skill filters synchronized"
  echo "  ✅ openclaw.json updated"

  # ─── 4b. 幂等同步模板 ALLOWED_COMMANDS → workspace ────────────────
  # 只注入模板中的 + 行（缺失时追加），不覆盖 workspace 已有条目（包括私有技能）
  while IFS=$'\t' read -r a_id a_ws; do
    [ -n "$a_id" ] || continue
    template_ac="$CREWS_DIR/$a_id/ALLOWED_COMMANDS"
    workspace_ac="$a_ws/ALLOWED_COMMANDS"
    [ -f "$template_ac" ] || continue
    if [ ! -f "$workspace_ac" ]; then
      cp "$template_ac" "$workspace_ac"
    else
      while IFS= read -r line; do
        [[ "$line" =~ ^\+ ]] || continue
        grep -qxF "$line" "$workspace_ac" || echo "$line" >> "$workspace_ac"
      done < "$template_ac"
    fi
  done < <(list_agent_workspaces)

  # ─── 4b.5. 自动注入 skill scripts → ALLOWED_COMMANDS（幂等）──
  # 扫描每个 agent 的 skill 列表，将带 scripts/ 的技能脚本路径追加到 ALLOWED_COMMANDS。
  # workspace-local skill → +./skills/<skill>/scripts/<file>（相对路径）
  # 全局 skill（openclaw/skills/）→ +<abs_path>（绝对路径）
  echo "  📝 Auto-injecting skill script commands into ALLOWED_COMMANDS..."
  while IFS=$'\t' read -r a_id a_ws; do
    [ -n "$a_id" ] || continue
    [ -d "$a_ws" ] || continue
    local_ac="$a_ws/ALLOWED_COMMANDS"

    # 读取该 agent 在 openclaw.json 中已写入的 skills 列表
    agent_skills_json="$(AGENT_ID="$a_id" node -e "
      const fs = require('fs');
      const c = JSON.parse(fs.readFileSync('$CONFIG_PATH', 'utf8'));
      const agent = (c.agents?.list || []).find((e) => e.id === process.env.AGENT_ID);
      console.log(JSON.stringify(agent?.skills || []));
    " 2>/dev/null)"

    [ -n "$agent_skills_json" ] || continue

    # 收集该 agent 所有 skill 的脚本路径
    script_entries="$(collect_skill_script_commands "$a_ws" "$agent_skills_json" "$PROJECT_ROOT")"
    [ -n "$script_entries" ] || continue

    # 确保文件存在且以换行符结尾（追加前只需检查一次）
    if [ ! -f "$local_ac" ]; then
      printf '# Auto-generated by setup-crew.sh — skill script allowlist\n' > "$local_ac"
    elif [ -s "$local_ac" ] && [ "$(tail -c 1 "$local_ac" 2>/dev/null | wc -l)" -eq 0 ]; then
      # tail -c 1 | wc -l: 若末字节为 \n 则 wc -l=1，否则 wc -l=0
      # （不能直接用 $(tail -c 1) != $'\n'，因为命令替换会吞掉末尾 \n 导致永远不等）
      printf '\n' >> "$local_ac"
    fi

    # 幂等追加：已有则跳过
    added_count=0
    while IFS= read -r entry; do
      [ -n "$entry" ] || continue
      # 幂等追加：已有 +entry 则跳过；若有同名 -entry 否决条目也跳过
      entry_cmd="${entry#+}"
      if grep -qxF "$entry" "$local_ac" 2>/dev/null; then
        continue
      fi
      if grep -qxF "-${entry_cmd}" "$local_ac" 2>/dev/null; then
        continue
      fi
      printf '%s\n' "$entry" >> "$local_ac"
      added_count=$((added_count + 1))
    done <<< "$script_entries"

    [ "$added_count" -gt 0 ] && echo "    ✅ $a_id: +${added_count} script entries injected"
  done < <(list_agent_workspaces)
  echo "  ✅ Skill script commands synced to ALLOWED_COMMANDS"

  # ─── 4c. 应用 Command Tier → exec-approvals + tools.exec ──────
  echo "  📝 Applying command tier exec policies..."
  EXEC_APPROVALS_PATH="$OPENCLAW_HOME/exec-approvals.json"
  apply_exec_tiers "$CONFIG_PATH" "$EXEC_APPROVALS_PATH" "$CREWS_DIR" "$PROJECT_ROOT"

  # ─── 4d. 注入渠道回复规则到已部署的对外 crew workspaces ──────
  while IFS=$'\t' read -r a_id a_ws; do
    [ -n "$a_id" ] || continue
    [ -f "$a_ws/SOUL.md" ] || continue
    [ "$(resolve_crew_type "$a_ws/SOUL.md")" = "external" ] || continue
    inject_channel_reply_rules "$a_ws/AGENTS.md"
    inject_agents_md_sections "$a_ws/AGENTS.md"
    inject_file_edit_guide "$a_ws/TOOLS.md"
    inject_exec_guide "$a_ws/TOOLS.md" "$a_ws"
    inject_python_exec_guide "$a_ws/TOOLS.md"
  done < <(list_agent_workspaces)
  echo "  ✅ Channel reply rules synced to deployed external crew workspaces"

  # ─── 4e. 注入标准 AGENTS.md sections 到已部署的对内 crew workspaces ──
  while IFS=$'\t' read -r a_id a_ws; do
    [ -n "$a_id" ] || continue
    [ -f "$a_ws/AGENTS.md" ] || continue
    inject_agents_md_sections "$a_ws/AGENTS.md"
    inject_feishu_media_guide "$a_ws/USER.md"
    inject_file_edit_guide "$a_ws/TOOLS.md"
    inject_exec_guide "$a_ws/TOOLS.md" "$a_ws"
    inject_python_exec_guide "$a_ws/TOOLS.md"
  done < <(list_agent_workspaces)
  echo "  ✅ Standard AGENTS.md sections synced to all deployed workspaces"

  # ─── 4f. 确保所有 skill 脚本有执行权限 ──────────────────────────
  while IFS=$'\t' read -r a_id a_ws; do
    [ -n "$a_id" ] || continue
    [ -d "$a_ws/skills" ] || continue
    chmod_count="$(find "$a_ws/skills" -name '*.sh' -not -executable -exec chmod +x {} + -print | wc -l)"
    [ "$chmod_count" -gt 0 ] && echo "    ✅ $a_id: chmod +x on $chmod_count scripts"
  done < <(list_agent_workspaces)
  echo "  ✅ Skill scripts ensured executable"
else
  echo "  ⚠️  openclaw.json not found at $CONFIG_PATH"
  echo "     Will be created on first start (dev.sh / reinstall-daemon.sh)"
fi

# ─── 5. 写入 OFB_ENV.md（仅 it-engineer） ──────────────────────
# 仅源码部署需要：路径随机器可变，故记录成文件供 IT engineer AGENTS.md 读取。
# Docker 部署不跑 setup-crew.sh，路径固定（/opt/openclaw + /root/.openclaw），
# AGENTS.md 已环境自感知，无需 OFB_ENV.md。
# main agent 不持有此文件：环境变量运维归 IT engineer，main 需加变量时 spawn it-engineer。
generate_ofb_env_md() {
  local workspace_dir="$1"
  local agent_label="$2"

  if [ -d "$workspace_dir" ]; then
    if [ "$(uname -s)" = "Darwin" ]; then
      _ENV_FILE_PATH="$HOME/.openclaw/service-env/ai.openclaw.gateway.env"
      _ENV_FILE_FORMAT="export KEY='value'"
      _ENV_FILE_FORMAT_DESC="shell export 格式，一行一个"
      _ENV_FILE_QUOTE_NOTE="4. **单引号转义**：值中含单引号时需转义为 \`'\\''\`"
    else
      _ENV_FILE_PATH="$HOME/.openclaw/daemon.env"
      _ENV_FILE_FORMAT="KEY=value"
      _ENV_FILE_FORMAT_DESC="systemd EnvironmentFile 格式，一行一个"
      _ENV_FILE_QUOTE_NOTE=""
    fi
    cat > "$workspace_dir/OFB_ENV.md" << ENVEOF
# wiseflow 环境信息（由 setup-crew.sh 自动生成，勿手动编辑）

- **wiseflow 项目路径**：$PROJECT_ROOT
- **openclaw 子目录**：$PROJECT_ROOT/openclaw
- **配置文件**：$OPENCLAW_HOME/openclaw.json

## 环境变量文件

### 是什么

gateway 进程启动时从此文件读取环境变量，注入到所有 Agent 的运行时环境中。像 API Key、超时参数这类配置，不能硬编码在代码或 openclaw.json 里，必须放在这里。

### 文件位置

\`$_ENV_FILE_PATH\`

### 写入格式

\`$_ENV_FILE_FORMAT\`（$_ENV_FILE_FORMAT_DESC）

### 何时编辑

当你需要为某个技能添加新的环境变量时（如新的 API Key、新的超时配置）。典型场景：

- 用户要求启用某个需要 API Key 的技能（如 email-ops 需要 SMTP 变量、pexels-footage 需要 PEXELS_API_KEY）
- IT Engineer 需要调整 gateway 运行时参数
- 新增 Crew 模板依赖了新的外部服务

### 注意事项

1. **写入前先检查**：grep 确认该 key 是否已存在，避免重复写入
2. **写入后必须重启**：编辑完成后必须重启 gateway 使新变量生效
3. **禁止内联**：不要在 exec 调用中写 \`KEY=value python3 script.py\`，这会导致 allowlist miss
$_ENV_FILE_QUOTE_NOTE

## 常用操作命令

\`\`\`bash
# 开发模式启动
cd $PROJECT_ROOT && ./scripts/dev.sh gateway

# 重新同步 crew 配置（幂等）
cd $PROJECT_ROOT && ./scripts/setup-crew.sh

# 重新应用 addons
cd $PROJECT_ROOT && ./scripts/apply-addons.sh

# 升级 wiseflow 系统（须确认系统空闲）
cd $PROJECT_ROOT && ./scripts/install.sh

# 仅重装后台服务（不更新代码）
cd $PROJECT_ROOT && ./scripts/install.sh --skip-crew

# 直接调用上游 CLI（如需）
cd $PROJECT_ROOT/openclaw && pnpm openclaw <subcommand>
\`\`\`
ENVEOF
    echo "  ✅ OFB_ENV.md updated in $agent_label workspace"
  fi
}

# OFB_ENV.md 仅写入 it-engineer workspace：环境变量 / 路径运维是 IT engineer 职责，
# main agent 不直接编辑 daemon.env，需要加环境变量时 spawn it-engineer 执行。
generate_ofb_env_md "$OPENCLAW_HOME/workspace-it-engineer" "it-engineer"

# --- 注入 env 文件路径指引到 TOOLS.md（仅 it-engineer）---
_OFB_ENV_FILE=""
if [ "$(uname -s)" = "Darwin" ]; then
  _OFB_ENV_FILE="$HOME/.openclaw/service-env/ai.openclaw.gateway.env"
else
  _OFB_ENV_FILE="$HOME/.openclaw/daemon.env"
fi
inject_env_file_guide "$OPENCLAW_HOME/workspace-it-engineer/TOOLS.md" "$_OFB_ENV_FILE"

# ─── 6. 完成 ──────────────────────────────────────────────────────
echo ""
echo "✅ Agent System installed!"
echo ""
echo "Installed locations:"
echo "  Workspaces:          $OPENCLAW_HOME/workspace-<crew-id>/ (one per crews/*, _template 除外)"
echo "  Config:              $CONFIG_PATH"
