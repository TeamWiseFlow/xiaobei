#!/bin/bash
# setup-crew.sh - 多 Agent 系统安装脚本
# 将 crews/ 中的内置模板、共享协议、模板库部署到 ~/.openclaw/
# 已存在的 workspace 保留用户正文（--force 可整文件覆盖），生成提示按当前版本更新。
# 仅部署当前版本模板；旧 TOOLS.md / HEARTBEAT.md 由用户升级后手动删除。
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CREWS_DIR="$PROJECT_ROOT/crews"
ADDONS_DIR="$PROJECT_ROOT/addons"
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-$OPENCLAW_HOME/openclaw.json}"
FORCE=false
source "$SCRIPT_DIR/lib/python-runtime.sh"
xiaobei_use_python_runtime "$PROJECT_ROOT"

# 内置 Crew（main / it-engineer）在 §4 中强制注册进 openclaw.json agents.entries；
# content-producer 已在 config-templates/openclaw.json agents.entries 预注册（§4 仅规范化）；
# 其余对外 crew（sales-cs / ...）的 workspace 在 §1 预建，运行时由 main agent 招募时注册。
source "$SCRIPT_DIR/lib/agent-skills.sh"
source "$SCRIPT_DIR/lib/exec-tiers.sh"
source "$SCRIPT_DIR/lib/crew-workspaces.sh"
export XIAOBEI_AGENT_ROSTER_MODULE="$SCRIPT_DIR/lib/agent-roster.cjs"

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
    const agent = require(process.env.XIAOBEI_AGENT_ROSTER_MODULE).getAgent(c, '$agent_id');
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
    const {getAgent, setAgent} = require(process.env.XIAOBEI_AGENT_ROSTER_MODULE);
    const agent = getAgent(c, process.env.AGENT_ID);
    if (agent) {
      const skillsResult = process.env.AGENT_SKILLS_RESULT || '';
      setAgent(c, process.env.AGENT_ID, { ...agent, skills: JSON.parse(skillsResult || '[]') });
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
    for (const a of require(process.env.XIAOBEI_AGENT_ROSTER_MODULE).listAgents(c)) {
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
# ~/.openclaw/workspace-<id>/。已存在则保留用户编辑，仅维护 internal crew 的运行指导。
# main / it-engineer 在 §4 中额外强制注册进 openclaw.json；content-producer 已在模板
# agents.entries 预注册（§4 仅规范化其 skills / allowAgents）；sales-cs 等对外 crew 的
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
    # §2.3：已部署 workspace 仍同步 crew 专属 skill（覆盖），保留用户正文；internal 的换行、exec 和 Python 区块每次重建
    # 及部署实例自定义 skill（sync_crew_skills 只覆盖仓库里同名的 skill）
    sync_crew_skills "$agent_dir" "$dest"
    # skill 声明文件（BUILTIN_SKILLS / DENIED_SKILLS）跟仓库走：陈旧条目会让 openclaw.json
    # 的 skills allowlist 指向已改名 / 已收纳的技能，crew 直接失去这批能力。
    sync_skill_declaration_files "$agent_dir" "$dest" "$PROJECT_ROOT" "$OPENCLAW_HOME"
    inject_internal_workspace_guides "$dest" "$VIRTUAL_ENV"
    continue
  fi

  copy_crew_template_contents "$agent_dir" "$dest"
  # §2.3：统一走 sync_crew_skills 装 skill + npm 依赖（fresh 分支 copy_crew_template_contents
  # 已把 skills/ 拷过去，这里再刷一遍保证与仓库一致并装依赖）
  sync_crew_skills "$agent_dir" "$dest"
  echo "  ✅ workspace-$agent_id installed"
  inject_internal_workspace_guides "$dest" "$VIRTUAL_ENV"
done

# ─── 1.5 共享业务知识目录：统一布局、迁移与目录软链 ───────────────────
# 正文固定为 business_knowledge/business_knowledge.md；只共享目录，不创建文件软链。
# 与 sales-cs-enablement 共用同一实现，保留旧正文和用户自定义 workspace 文档。
MAIN_WS="$OPENCLAW_HOME/workspace-main"
knowledge_workspaces=(--workspace "$MAIN_WS")
for ws in "$OPENCLAW_HOME"/workspace-*/; do
  [ -d "$ws" ] || continue
  [ "$(basename "$ws")" = "workspace-main" ] && continue
  knowledge_workspaces+=(--workspace "${ws%/}")
done
MAIN_WORKSPACE="$MAIN_WS" REPO_MAIN="$CREWS_DIR/main" python3 \
  "$CREWS_DIR/main/skills/sales-cs-manager/tools/sales-cs-enablement/scripts/symlink_business_knowledge.py" \
  "${knowledge_workspaces[@]}" --backup-dir "$OPENCLAW_HOME/backups"

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

    for (const agent of require(process.env.XIAOBEI_AGENT_ROSTER_MODULE).listAgents(c)) {
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
      require(process.env.XIAOBEI_AGENT_ROSTER_MODULE).setAgent(c, agent.id, agent);
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

  MAIN_SKILLS_RESULT="$MAIN_SKILLS_RESULT" IT_SKILLS_RESULT="$IT_SKILLS_RESULT" OPENCLAW_HOME="$OPENCLAW_HOME" PROJECT_ROOT="$PROJECT_ROOT" node -e "
    const fs = require('fs');
    const path = require('path');
    const c = JSON.parse(fs.readFileSync('$CONFIG_PATH', 'utf8'));
    const openclawHome = process.env.OPENCLAW_HOME || (process.env.HOME + '/.openclaw');

    const applySkills = (entry, skillsResult) => {
      return { ...entry, skills: JSON.parse((skillsResult || '[]').trim() || '[]') };
    };

    const {listAgents, getAgent, setAgent} = require(process.env.XIAOBEI_AGENT_ROSTER_MODULE);
    if (!c.agents) c.agents = {entries: {}};

    const upsertAgent = (id, buildNext) => {
      const prev = getAgent(c, id) || {};
      const next = buildNext(prev);
      setAgent(c, id, next);
    };

    const getCrewType = (id) => {
      if (id === 'main' || id === 'it-engineer') return 'internal';
      const agent = getAgent(c, id);
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
        ...(!c.agents.entries ? {default: prev.default ?? true} : {}),
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
        // thinkingDefault 不显式设--与其他 crew 一致继承 agents.defaults.thinkingDefault；
        // 若用户在 openclaw.json 手动给 it-engineer 设过则 prev 保留（...prev 已带）。
        reasoningDefault: 'off',
      };
      return applySkills(base, process.env.IT_SKILLS_RESULT);
    });

    // 系统运维默认由 IT 持有；已有明确的系统 owner 是实例设置，保留不覆盖。
    const agentDefaults = c.agents.defaults || (c.agents.defaults = {});
    if (agentDefaults.systemAgent === undefined ||
        (agentDefaults.systemAgent && typeof agentDefaults.systemAgent === 'object' &&
         !Object.hasOwn(agentDefaults.systemAgent, 'agentId'))) {
      agentDefaults.systemAgent = { ...(agentDefaults.systemAgent || {}), agentId: 'it-engineer' };
    }

    // 为所有其他对内 Crew 实例也追加 it-engineer spawn 权限
    // （它们在 depth=1 时需要 maxSpawnDepth>=2，由 agents.defaults.subagents.maxSpawnDepth 保证）
    const PROTECTED_IDS = new Set(['main', 'it-engineer']);
    for (const agent of listAgents(c)) {
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
      setAgent(c, agent.id, agent);
    }

    // 为所有 Agent 追加自身 ID 到 allowAgents，确保显式 self-spawn 合法
    // （隐式 self-spawn 不传 agentId 时本就放行，但 agent 常显式传入自身 ID，
    //   此时必须通过 allowlist 检查，否则会被拒绝）
    for (const agent of listAgents(c)) {
      if (!agent.id) continue;
      const prevAllow = Array.isArray(agent.subagents?.allowAgents) ? agent.subagents.allowAgents : [];
      if (!prevAllow.includes(agent.id)) {
        agent.subagents = {
          ...(agent.subagents || {}),
          allowAgents: [...new Set([...prevAllow, agent.id])],
        };
      }
      setAgent(c, agent.id, agent);
    }

    // 与 config template 一致：微信所有登录账号进入 main；工作渠道按具体账号绑定，
    // 不生成 feishu -> main 的通配兜底。已有实例的 binding 原样保留。
    if (!Array.isArray(c.bindings)) c.bindings = [];
    const hasMainWeixin = c.bindings.some((binding) =>
      binding?.agentId === 'main' && binding?.match?.channel === 'openclaw-weixin'
    );
    if (!hasMainWeixin) {
      c.bindings.push(
        { agentId: 'main', comment: 'openclaw-weixin -> Main Agent onboarding entry', match: { channel: 'openclaw-weixin', accountId: '*' } }
      );
    }

    // 注入 skill 软链 target 白名单（软链方案，spec §2.3 演进）
    // crew skills 软链到 ~/.openclaw/workspace-<id>/skills/，source="openclaw-workspace"
    // 走 containment gate（shouldEnforceConfiguredSkillRootContainment=true），
    // 软链 target（仓路径）必须在 allowSymlinkTargets 里才不被拒（否则 warn escaped skill path）。
    // managed skills（~/.openclaw/skills）走 "openclaw-managed" 无 gate，不需要，但加上无害且未来对齐。
    // 仅源码部署生效（Docker 不跑 setup-crew.sh，Docker 用 COPY 不软链）。
    const projectRoot = process.env.PROJECT_ROOT;
    if (projectRoot) {
      const targets = [
        path.join(projectRoot, 'crews'),
        path.join(projectRoot, 'skills'),
      ].map((d) => { try { return fs.realpathSync(d); } catch { return null; } })
        .filter((d) => typeof d === 'string');
      if (targets.length) {
        if (!c.skills) c.skills = {};
        if (!c.skills.load) c.skills.load = {};
        const existing = Array.isArray(c.skills.load.allowSymlinkTargets) ? c.skills.load.allowSymlinkTargets : [];
        c.skills.load.allowSymlinkTargets = [...new Set([...existing, ...targets])];
      }
    }

    fs.writeFileSync('$CONFIG_PATH', JSON.stringify(c, null, 2) + '\\n');
  "

  # 同步所有已注册 agent 的技能过滤
  AGENT_IDS="$(node -e "
    const fs = require('fs');
    const c = JSON.parse(fs.readFileSync('$CONFIG_PATH', 'utf8'));
    console.log(require(process.env.XIAOBEI_AGENT_ROSTER_MODULE).listAgents(c).map((entry) => entry.id).join('\\n'));
  " 2>/dev/null)"
  while IFS= read -r agent_id; do
    [ -n "$agent_id" ] || continue
    sync_agent_skill_filter "$agent_id"
  done <<< "$AGENT_IDS"
  echo "  ✅ Agent skill filters synchronized"
  echo "  ✅ openclaw.json updated"

  # ─── 4b. 幂等同步模板 ALLOWED_COMMANDS → workspace（仅对外 crew）──
  # 只注入模板中的 + 行（缺失时追加），不覆盖 workspace 已有条目（包括私有技能）
  # 对内 crew 跳过：internal → security:full，apply_exec_tiers 不读 ALLOWED_COMMANDS（见 exec-tiers.sh 权限模型）。
  # crew-type 以 workspace SOUL.md 为准（与 4c 一致）；SOUL.md 缺失时 resolve_crew_type 兜底 external，照常生成（fail-closed）。
  while IFS=$'\t' read -r a_id a_ws; do
    [ -n "$a_id" ] || continue
    [ "$(resolve_crew_type "$a_ws/SOUL.md")" = "external" ] || continue
    template_ac="$CREWS_DIR/$a_id/ALLOWED_COMMANDS"
    workspace_ac="$a_ws/ALLOWED_COMMANDS"
    [ -f "$template_ac" ] || continue
    if [ ! -f "$workspace_ac" ]; then
      cp "$template_ac" "$workspace_ac"
    else
      while IFS= read -r line; do
        [[ "$line" =~ ^\+ ]] || continue
        # 幂等检查：用 bash 内置逐行比，不调 grep（MSYS2 grep 对含全角括号的中文路径
        # workspace 文件 open() 时字节解错码，会卡死扫不进——setup-crew 实测卡 30min+ 元凶）
        _found=0
        while IFS= read -r _existing; do [[ "$_existing" == "$line" ]] && _found=1 && break; done < "$workspace_ac"
        [[ "$_found" == "1" ]] || echo "$line" >> "$workspace_ac"
      done < "$template_ac"
    fi
  done < <(list_agent_workspaces)

  # ─── 4b.5. 自动注入 skill scripts → ALLOWED_COMMANDS（幂等，仅对外 crew）──
  # 扫描每个 agent 的 skill 列表，将带 scripts/ 的技能脚本路径追加到 ALLOWED_COMMANDS。
  # workspace-local skill → +./skills/<skill>/scripts/<file>（相对路径）
  # 全局 skill（openclaw/skills/）→ +<abs_path>（绝对路径）
  # 对内 crew 跳过：internal → security:full，该文件无任何运行时消费者，生成只会误导成"受白名单约束"。
  echo "  📝 Auto-injecting skill script commands into ALLOWED_COMMANDS..."
  while IFS=$'\t' read -r a_id a_ws; do
    [ -n "$a_id" ] || continue
    [ -d "$a_ws" ] || continue
    [ "$(resolve_crew_type "$a_ws/SOUL.md")" = "external" ] || continue
    local_ac="$a_ws/ALLOWED_COMMANDS"

    # 读取该 agent 在 openclaw.json 中已写入的 skills 列表
    agent_skills_json="$(AGENT_ID="$a_id" node -e "
      const fs = require('fs');
      const c = JSON.parse(fs.readFileSync('$CONFIG_PATH', 'utf8'));
      const agent = require(process.env.XIAOBEI_AGENT_ROSTER_MODULE).getAgent(c, process.env.AGENT_ID);
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
      # 用 bash 内置逐行比，不调 grep（MSYS2 grep 对含全角括号的中文 workspace 路径 open()
      # 字节解错码卡死——setup-crew 实测卡 30min+ 元凶；bash 自己的 read 不经 MSYS2 grep）
      _has_pos=0 _has_neg=0
      while IFS= read -r _existing; do
        [[ "$_existing" == "$entry" ]] && _has_pos=1
        [[ "$_existing" == "-${entry_cmd}" ]] && _has_neg=1
      done < "$local_ac"
      if [[ "$_has_pos" == "1" ]]; then
        continue
      fi
      if [[ "$_has_neg" == "1" ]]; then
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
  apply_exec_tiers "$CONFIG_PATH" "$CREWS_DIR" "$PROJECT_ROOT"
  node "$SCRIPT_DIR/python-runtime.mjs" configure --root "$PROJECT_ROOT" --config "$CONFIG_PATH"

  # ─── 4e. 注入标准 AGENTS.md sections 到已部署的对内 crew workspaces ──
  while IFS=$'\t' read -r a_id a_ws; do
    [ -n "$a_id" ] || continue
    inject_internal_workspace_guides "$a_ws" "$VIRTUAL_ENV"
  done < <(list_agent_workspaces)
  echo "  ✅ Standard AGENTS.md sections synced to deployed internal workspaces"

  # ─── 4f. 确保所有 skill 脚本有执行权限 ──────────────────────────
  while IFS=$'\t' read -r a_id a_ws; do
    [ -n "$a_id" ] || continue
    [ -d "$a_ws/skills" ] || continue
    # BSD find（macOS）不支持 -executable（GNU 专属），用 ! -perm -u+x 兼容两者。
    chmod_count="$(find "$a_ws/skills" -name '*.sh' ! -perm -u+x -exec chmod +x {} + -print 2>/dev/null | wc -l)"
    [ "$chmod_count" -gt 0 ] && echo "    ✅ $a_id: chmod +x on $chmod_count scripts"
  done < <(list_agent_workspaces)
  echo "  ✅ Skill scripts ensured executable"

  # ─── 4g. 确保 program bin 在 gateway env 的 PATH 里 ──────────
  # systemd user service 不 source shell rc，PATH 只能经 EnvironmentFile 注入
  # （Linux: daemon.env / Darwin: service-env/ai.openclaw.gateway.env）。
  # EnvironmentFile 覆盖 unit 的 Environment=（实测 systemd 255），故在此文件把
  # program bin + wrapper bin 前置到 PATH，gateway 重启后 agent exec 才能解析 skill wrapper。
  # - program bin = openclaw 启动器所在（XIAOBEI_BIN_DIR 或 PROJECT_ROOT/bin）。
  # - wrapper bin = ~/.openclaw/bin，skill-wrappers.sh 把每个技能顶层 wrapper 软链到这里，
  #   agent exec 调裸技能名（如 `aigc-video-gen`）靠 PATH 解析这些软链。gateway 不 source
  #   shell rc，故 wrapper bin 必须显式进 daemon.env PATH，否则技能脚本软链找不到。
  # 幂等：仅补缺失项，不动既有 PATH 行其余内容。
  _XIAOBEI_BIN="${XIAOBEI_BIN_DIR:-$PROJECT_ROOT/bin}"
  _WRAPPER_BIN="$OPENCLAW_HOME/bin"
  if [ "$(uname -s)" = "Darwin" ]; then
    _GW_ENV="$OPENCLAW_HOME/service-env/ai.openclaw.gateway.env"
  else
    _GW_ENV="$OPENCLAW_HOME/daemon.env"
  fi
  if [ -f "$_GW_ENV" ]; then
    python3 - "$_GW_ENV" "$_XIAOBEI_BIN" "$_WRAPPER_BIN" <<'PY'
import re, sys
path = sys.argv[1]
bins = [b for b in sys.argv[2:] if b]
with open(path) as f:
    lines = f.readlines()
out = []
touched = False
seen = False
for ln in lines:
    m = re.match(r'^export PATH=(["\'])(.*)\1\s*$', ln) or re.match(r'^PATH=(\S*)\s*$', ln)
    if m and (ln.startswith('export PATH=') or ln.startswith('PATH=')):
        val = m.group(2) if ln.startswith('export PATH=') else m.group(1)
        seen = True
        parts = val.split(':')
        prepend = [b for b in bins if b not in parts]
        if prepend:
            newval = ':'.join(prepend) + (':' + val if val else '')
            if ln.startswith('export PATH='):
                ln = f"export PATH={m.group(1)}{newval}{m.group(1)}\n"
            else:
                ln = f"PATH={newval}\n"
            touched = True
    out.append(ln)
if not seen:
    print(f"    ⚠️  no PATH line in {path}; skip")
elif touched:
    with open(path, 'w') as f:
        f.writelines(out)
    print(f"    ✅ prepended missing bin(s) to PATH in {path}")
else:
    print(f"    ✅ program + wrapper bin already on PATH in {path}")
PY
  else
    # 首装时 gateway env 文件由后续 install_gateway_and_env 创建，此刻不存在是预期，静默跳过。
    :
  fi
  unset _GW_ENV _XIAOBEI_BIN _WRAPPER_BIN
else
  echo "  ⚠️  openclaw.json not found at $CONFIG_PATH"
  echo "     Will be created on first start (dev.sh / reinstall-daemon.sh)"
fi

# ─── 5. 写入 OFB_ENV.md（仅 it-engineer） ──────────────────────
# 源码部署：路径随机器可变，记录成文件供 IT engineer AGENTS.md 读取。
# Docker 部署：路径固定（/opt/xiaobei + /root/.openclaw），但仍然生成
#   OFB_ENV.md——降低 agent 判断出错概率，让 it-engineer 读文件而非推断。
# main agent 不持有此文件：环境变量运维归 IT engineer，main 需加变量时 spawn it-engineer。
generate_ofb_env_md() {
  local workspace_dir="$1"
  local agent_label="$2"

  if [ -d "$workspace_dir" ]; then
    # 技能密钥统一进 state-dir dotenv（~/.openclaw/.env），所有 openclaw 进程都加载；
    # 服务 EnvironmentFile 仅放 gateway 运维变量（PATH 等），不放技能密钥。
    # ── 检测部署环境 ──
    # 三重检测，任一命中即判定 Docker 部署：
    #   1. WISEFLOW_DOCKER=1 环境变量（docker-bootstrap.sh 显式设置，最可靠）
    #   2. /.dockerenv 文件存在（docker run 的容器有，但 build stage 基础镜像可能没有）
    #   3. OPENCLAW_HOME=/root/.openclaw 特征（Docker 镜像内的固定路径）
    local _is_docker=false
    if [ "${WISEFLOW_DOCKER:-0}" = "1" ] || [ -f /.dockerenv ] || [ "${OPENCLAW_HOME:-}" = "/root/.openclaw" ]; then
      _is_docker=true
    fi

    if [ "$_is_docker" = "true" ]; then
      # ── Docker 部署：固定路径 ──
      _PROJECT_ROOT="/opt/xiaobei"
      _OPENCLAW_HOME="/root/.openclaw"
      _CONFIG_PATH="$_OPENCLAW_HOME/openclaw.json"
      _ENV_FILE_PATH="$_OPENCLAW_HOME/.env"
      _ENV_FILE_FORMAT="KEY=value"
      _ENV_FILE_FORMAT_DESC="dotenv 格式，一行一个（Docker entrypoint source 加载）"
      _ENV_FILE_QUOTE_NOTE=""
      _SVC_ENV_FILE="$_OPENCLAW_HOME/daemon.env"
      _RESTART_CMD="docker restart <容器名>"
      _RESTART_NOTE="编辑 .env 后需 \`docker restart\` 生效（gateway 启动时加载 .env，运行中改不会热生效）"
    elif [ "$(uname -s)" = "Darwin" ]; then
      # ── macOS 源码部署 ──
      _PROJECT_ROOT="$PROJECT_ROOT"
      _OPENCLAW_HOME="$OPENCLAW_HOME"
      _CONFIG_PATH="$_OPENCLAW_HOME/openclaw.json"
      _ENV_FILE_PATH="$_OPENCLAW_HOME/.env"
      _ENV_FILE_FORMAT="KEY=value"
      _ENV_FILE_FORMAT_DESC="dotenv 格式，一行一个"
      _ENV_FILE_QUOTE_NOTE=""
      _SVC_ENV_FILE="$HOME/.openclaw/service-env/ai.openclaw.gateway.env"
      _RESTART_CMD="launchctl kickstart -k gui/\$(id -u)/ai.openclaw.gateway"
      _RESTART_NOTE="编辑 .env 后需重启 gateway 服务"
    else
      # ── Linux 源码部署 ──
      _PROJECT_ROOT="$PROJECT_ROOT"
      _OPENCLAW_HOME="$OPENCLAW_HOME"
      _CONFIG_PATH="$_OPENCLAW_HOME/openclaw.json"
      _ENV_FILE_PATH="$_OPENCLAW_HOME/.env"
      _ENV_FILE_FORMAT="KEY=value"
      _ENV_FILE_FORMAT_DESC="dotenv 格式，一行一个"
      _ENV_FILE_QUOTE_NOTE=""
      _SVC_ENV_FILE="$HOME/.openclaw/daemon.env"
      _RESTART_CMD="systemctl --user restart openclaw-gateway.service"
      _RESTART_NOTE="编辑 .env 后需 \`systemctl --user restart openclaw-gateway.service\` 生效"
    fi

    cat > "$workspace_dir/OFB_ENV.md" << ENVEOF
# wiseflow 环境信息（由 setup-crew.sh 自动生成，勿手动编辑）

- **部署环境**：$([ "$_is_docker" = "true" ] && echo "Docker 容器" || echo "源码部署（$(uname -s)）")
- **程序目录**（引擎 + 模板 + 脚本 + 工具 + wrapper，升级只换这里）：$_PROJECT_ROOT
- **运行数据目录**（openclaw.json + daemon.env + workspace-* + sessions，用户数据不动）：$_OPENCLAW_HOME
- **wiseflow 项目路径**：$_PROJECT_ROOT
- **openclaw 子目录**：$_PROJECT_ROOT/openclaw
- **配置文件**：$_CONFIG_PATH
- **默认 Gateway 主日志**：$_OPENCLAW_HOME/logs/gateway.log（实际位置以配置中的 logging.file 为准）

## 环境变量文件

### 是什么

技能运行时需要的密钥 / 参数（API Key、超时配置等），不能硬编码在代码或 openclaw.json 里，必须放环境变量文件。openclaw 在启动时把该文件加载进 process.env，注入到所有 Agent 的运行时环境。

### 文件位置

\`$_ENV_FILE_PATH\`（当前 state-dir dotenv）

> ⚠️ **技能密钥一律写这个文件，不要写 daemon.env / service-env。** 此文件被**每个 openclaw 进程**加载（gateway、bare CLI、self-spawned subagent、cron isolated-agent），密钥能到达所有调用路径。daemon.env（Linux）/ service-env（macOS）是服务管理器的 EnvironmentFile，**只有托管 gateway 进程**继承；subagent / cron / 裸 CLI 子进程不继承，把只被 subagent 调用的技能密钥放那里会报"未配置"。

### 写入格式

\`KEY=value\`，一行一个（dotenv 格式，Linux / macOS 通用）。值含空格 / 特殊字符时用双引号包裹：\`KEY="value with spaces"\`。

### 何时编辑

当你需要为某个技能添加新的环境变量时（如新的 API Key、新的超时配置）。典型场景：

- 用户要求启用某个需要 API Key 的技能（如 email-ops 需要 SMTP 变量、pexels-footage 需要 PEXELS_API_KEY、viral-chaser 需要 VOLC_ASR_*）
- 新增 Crew 模板依赖了新的外部服务

> gateway 运维变量（PATH 注入、监听端口等必须在本进程启动前就位的值）仍写服务 EnvironmentFile（\`$_SVC_ENV_FILE\`），不放 \`.env\`。IT engineer 加技能密钥的常见场景只需动 \`.env\`。

### 注意事项

1. **写入前先检查**：grep 确认该 key 是否已存在，避免重复写入
2. **写入后必须重启**：$_RESTART_NOTE
3. **禁止内联**：不要在 exec 调用中写 \`KEY=value python3 script.py\`，这会导致 allowlist miss

## 常用操作命令

\`\`\`bash
# 开发模式启动（源码部署）
cd $_PROJECT_ROOT && ./scripts/dev.sh gateway

# 重新同步 crew 配置（幂等）
cd $_PROJECT_ROOT && ./scripts/setup-crew.sh

# 重新应用 addons
cd $_PROJECT_ROOT && ./scripts/apply-addons.sh

# 升级 wiseflow 系统（须确认系统空闲）
cd $_PROJECT_ROOT && ./scripts/install.sh

# 仅重装后台服务（不更新代码）
cd $_PROJECT_ROOT && ./scripts/install.sh --skip-crew

# 重启 gateway（生效 daemon.env 改动）
$_RESTART_CMD

# 已构建 CLI（不触发源码构建）
openclaw <subcommand>

# 最近 20 行日志（只读，不跟随）
openclaw logs --limit 20

# 有界排障窗口（只读）
openclaw logs --limit 200 --plain

# 用户交互跟随日志（自动巡检不用）
openclaw logs --follow
\`\`\`

上面的 openclaw 指已安装入口，不保证在终端 PATH。预构建安装可用 \`"$_PROJECT_ROOT/bin/openclaw" logs --limit 20\`；源码部署可用 \`node "$_PROJECT_ROOT/openclaw/dist/index.js" logs --limit 20\`。Windows PowerShell 使用安装目录中的 bin/openclaw.cmd；完整平台例子见项目 docs/install-troubleshooting.md 的「运行日志」，入口速查在 AGENTS.md 的 Tools 节。

生产运行中优先使用可用且获授权的原生管理工具。终端使用已安装的 openclaw CLI 或已构建 dist/index.js；不要用可能重建共享 dist 的 pnpm openclaw / 源码开发入口。构建前先通过原服务管理器停止 Gateway，不绕过运行中产物保护。

本机路径、环境变量名称和工具别名写在 AGENTS.md 的 Tools 节，不新建 TOOLS.md；技能操作手册保留在 SKILL.md。
ENVEOF
    echo "  ✅ OFB_ENV.md updated in $agent_label workspace ($([ "$_is_docker" = "true" ] && echo "Docker" || echo "source"))"
  fi
}

# OFB_ENV.md 仅写入 it-engineer workspace：环境变量 / 路径运维是 IT engineer 职责，
# main agent 不直接编辑 daemon.env，需要加环境变量时 spawn it-engineer 执行。
generate_ofb_env_md "$OPENCLAW_HOME/workspace-it-engineer" "it-engineer"

# ─── 5b. Docker 部署时往 it-engineer AGENTS.md 注入容器环境提示 ──────
# 子 agent 只自动注入 AGENTS.md，容器运维约束不能留在 MEMORY.md。
inject_docker_env_hint() {
  local agents_md="$OPENCLAW_HOME/workspace-it-engineer/AGENTS.md"
  [ -f "$agents_md" ] || return 0

  # 幂等：已有标记则跳过
  if grep -q '<!-- WISEFLOW_DOCKER_ENV_HINT -->' "$agents_md" 2>/dev/null; then
    return 0
  fi

  # 在首个标题后插入提示块，保留其他正文。
  local hint_block='
<!-- WISEFLOW_DOCKER_ENV_HINT -->
## ⚠️ 容器环境提示（Docker 部署）

**本系统运行于 Docker 容器中**，以下命令在容器内**不适用**，需替换为容器等价命令：

| ❌ 容器内不适用 | ✅ Docker 等价命令 |
|----------------|-------------------|
| `systemctl --user restart openclaw` | `docker restart <容器名>`（宿主机执行） |
| `systemctl --user start openclaw` | `docker start <容器名>` |
| `systemctl --user status openclaw` | `docker ps` / `docker logs <容器名>` |
| `launchctl kickstart ... ai.openclaw.gateway` | `docker restart <容器名>`（macOS 宿主机） |

**关键差异**：
1. **容器内无 systemd / launchd**：任何 `systemctl` / `launchctl` 命令都会失败
2. **重启走宿主机**：`docker restart <容器名>` 在宿主机执行，不是容器内
3. **gateway 启动**：容器 entrypoint 自动启动 gateway，无需手动 `systemctl start`
4. **配置热加载**：改 `.env` / `daemon.env` 后需 `docker restart` 生效（gateway 启动时加载）

**运维位置**：
- 宿主机看日志：`docker logs -f <容器名>`；进容器调试：`docker exec -it <容器名> bash`
- 容器内看 Gateway 状态：使用已安装的 `openclaw health`
- `docker logs`、`docker exec`、`docker restart` 都在宿主机执行，不在容器内调用
<!-- /WISEFLOW_DOCKER_ENV_HINT -->
'

  # perl 避免 macOS / Linux 的 sed -i 参数差异。
  perl -e '
    my ($file, $hint) = @ARGV;
    local $/; open my $fh, "<", $file or die $!; my $c = <$fh>; close $fh;
    $c =~ s/^(# .*\n)/$1$hint/;  # 在首个 "# 标题行" 后插入
    open my $out, ">", $file or die $!; print $out $c; close $out;
  ' "$agents_md" "$hint_block"

  echo "  ✅ Docker env hint injected into it-engineer AGENTS.md"
}

# 仅 Docker 部署时注入；源码部署使用 OFB_ENV.md 记录的服务管理器。
if [ "${WISEFLOW_DOCKER:-0}" = "1" ] || [ -f /.dockerenv ] || [ "${OPENCLAW_HOME:-}" = "/root/.openclaw" ]; then
  inject_docker_env_hint
fi

# ─── 6. 完成 ──────────────────────────────────────────────────────
echo ""
echo "✅ Agent System installed!"
echo ""
echo "Installed locations:"
echo "  Workspaces:          $OPENCLAW_HOME/workspace-<crew-id>/ (one per crews/*, _template 除外)"
echo "  Config:              $CONFIG_PATH"
