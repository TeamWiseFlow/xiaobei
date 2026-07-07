#!/bin/bash
# exec-tiers.sh - T0~T3 命令分级 → exec-approvals / tools.exec 映射
#
# 读取 SOUL.md 中的 command-tier 声明 + ALLOWED_COMMANDS 微调，
# 生成 openclaw 原生 exec 权限配置（tools.exec + exec-approvals.json）。
#
# 被 setup-crew.sh source 使用。

# ── 各 Tier 基线命令 ──────────────────────────────────
# T0: 无命令（deny）
# T1: 只读型系统命令
TIER_T1_COMMANDS="cat ls grep find xargs ps date echo pwd env which head tail wc sort uniq diff curl stat basename dirname realpath readlink tr printf whoami uname du df file ffprobe fc-list fc-match sed mkdir true false"
# T2: T1 + 开发工具链
# 注意：不再列入 bash/sh。openclaw exec 审批对 shell wrapper（bash/sh/zsh 等）调用
# 要求 argPattern 绑定脚本（`bash script.sh`、`bash -c '...'` 都触发 requiresBoundArgPattern），
# 裸 `/usr/bin/bash` 条目匹配不上这类调用，属于死条目。crew 脚本统一走 shebang 直接执行
# 或 `python3 /abs/script.py`；`bash -c '...'` 由 inlineChain 拆开按内联命令逐段匹配白名单。
TIER_T2_EXTRA="git npm npx pnpm bun node python python3 pip pip3 ffmpeg perl cp mv mkdir rmdir rm touch chmod sleep test"
# T3: full access（无需白名单）

# ── 便携 readlink -f ──────────────────────────────────
# macOS 自带 BSD readlink 不支持 -f（静默失败），GNU readlink 才支持。
# 优先 readlink -f；失败则用 python3 os.path.realpath 兜底（python3 是 openclaw 硬依赖）；
# 再失败原样返回，由调用方决定是否接受非 realpath。
_resolve_realpath() {
  local p="$1" r
  r="$(readlink -f "$p" 2>/dev/null || true)"
  if [ -n "$r" ]; then echo "$r"; return; fi
  r="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$p" 2>/dev/null || true)"
  echo "${r:-$p}"
}

# ── 从 SOUL.md 解析 command-tier ──────────────────────
resolve_command_tier() {
  local soul_file="$1"
  if [ ! -f "$soul_file" ]; then
    echo "T0"
    return
  fi
  local tier
  tier="$(grep -i 'command-tier:' "$soul_file" 2>/dev/null \
    | head -1 \
    | sed 's/.*command-tier:[[:space:]]*//' \
    | tr -d '[:space:]' \
    | tr '[:lower:]' '[:upper:]')"
  case "$tier" in
    T0|T1|T2|T3) echo "$tier" ;;
    *) echo "T0" ;;
  esac
}

# ── 从 SOUL.md 解析 crew-type（internal/external）──────
# 注意：resolve_crew_type 由 agent-skills.sh 提供（唯一权威实现）
# setup-crew.sh 先 source agent-skills.sh 再 source 本文件，无需重复定义。

# ── 从 ALLOWED_COMMANDS 解析 +/- 微调 ────────────────
# 输出格式: "added1 added2|removed1 removed2"
parse_allowed_commands() {
  local file="$1"
  local added=""
  local removed=""

  if [ ! -f "$file" ]; then
    echo "|"
    return
  fi

  while IFS= read -r line; do
    line="$(printf '%s' "$line" | sed 's/#.*//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -n "$line" ] || continue
    case "$line" in
      +*) added="$added ${line#+}" ;;
      -*) removed="$removed ${line#-}" ;;
    esac
  done < "$file"

  echo "${added}|${removed}"
}

# ── 计算某 agent 的最终命令列表 ──────────────────────
# 返回: 空格分隔的命令名列表, 或 "__FULL__"（T3）, 或空（T0）
resolve_tier_commands() {
  local tier="$1"
  local allowed_commands_file="$2"

  # 解析微调
  local adjustments
  adjustments="$(parse_allowed_commands "$allowed_commands_file")"
  local added="${adjustments%%|*}"
  local removed="${adjustments##*|}"

  local base_commands=""
  case "$tier" in
    # T0 默认 deny；若显式声明 +command，则升级为 allowlist（仍是最小权限）
    T0) base_commands="$added" ;;
    T1) base_commands="$TIER_T1_COMMANDS $added" ;;
    T2) base_commands="$TIER_T1_COMMANDS $TIER_T2_EXTRA $added" ;;
    T3) echo "__FULL__"; return ;;
    *) base_commands="$added" ;;
  esac

  local all_commands="$base_commands"

  # 过滤被移除的命令
  local final=""
  for cmd in $all_commands; do
    local skip=false
    for r in $removed; do
      [ "$cmd" = "$r" ] && { skip=true; break; }
    done
    [ "$skip" = "false" ] && final="$final $cmd"
  done

  echo "$final"
}

# ── 解析命令名 → 二进制绝对路径 ──────────────────────
# $1: 命令名或脚本路径
# $2: (可选) 基准目录，用于解析 ./ 相对路径（默认为 CWD）
resolve_binary_path() {
  local cmd="$1"
  local base_dir="${2:-}"
  # 脚本路径（./scripts/... 或绝对路径）→ 转绝对路径
  # 注意：不使用 cd 来解析路径（若目录不存在会导致路径被静默丢弃），
  # 直接做字符串拼接，确保私有技能条目即使尚未安装也能正确写入 exec-approvals.json
  case "$cmd" in
    ./*|../*)
      local abs
      if [ -n "$base_dir" ]; then
        # 将 base_dir + cmd 拼接后规范化（去掉多余的 ./ ../）
        abs="$(printf '%s/%s' "$base_dir" "$cmd" | sed 's|/\./|/|g; s|/[^/]*/\.\./|/|g; s|/$||')"
      else
        abs="$(printf '%s' "$cmd" | sed 's|^./||')"
      fi
      [ -n "$abs" ] && echo "$abs"
      return
      ;;
    /*)
      # OpenClaw matchAllowlist 用 resolvedRealPath（readlink -f）匹配 pattern，
      # 因此 allowlist 条目必须用 realpath 而非 symlink 路径，
      # 否则 /usr/bin/python3 → /usr/bin/python3.12 的 symlink 会导致 allowlist miss。
      local real
      real="$(_resolve_realpath "$cmd")"
      echo "${real:-$cmd}"
      return
      ;;
  esac
  # command -v 可能返回 shell builtin 名（无 /），此时尝试 which 或常见路径
  local resolved
  resolved="$(command -v "$cmd" 2>/dev/null || true)"
  case "$resolved" in
    /*)
      local real
      real="$(_resolve_realpath "$resolved")"
      echo "${real:-$resolved}"
      return
      ;;
  esac
  # 尝试 which（跳过 builtins）
  resolved="$(which "$cmd" 2>/dev/null || true)"
  case "$resolved" in
    /*)
      local real
      real="$(_resolve_realpath "$resolved")"
      echo "${real:-$resolved}"
      return
      ;;
  esac
  # 兜底：检查常见系统目录
  local dir
  for dir in /usr/bin /bin /usr/local/bin; do
    if [ -x "$dir/$cmd" ]; then
      local real
      real="$(_resolve_realpath "$dir/$cmd")"
      echo "${real:-$dir/$cmd}"
      return
    fi
  done
}

# ── 为 agent 生成 allowlist JSON 数组 ────────────────
# $1: 空格分隔的命令列表
# $2: (可选) agent workspace 目录，用于解析 ./ 相对路��
# 输出: JSON 数组字符串
build_exec_allowlist_json() {
  local commands="$1"
  local base_dir="${2:-}"

  if [ -z "$commands" ] || [ "$commands" = "__FULL__" ]; then
    echo "[]"
    return
  fi

  local entries=""
  local first=true
  for cmd in $commands; do
    local bin_path
    bin_path="$(resolve_binary_path "$cmd" "$base_dir")"
    [ -n "$bin_path" ] || continue

    if [ "$first" = "true" ]; then
      first=false
    else
      entries="${entries},"
    fi
    # 转义 JSON 中的特殊字符（路径一般没有，但以防万一）
    local escaped
    escaped="$(printf '%s' "$bin_path" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    entries="${entries}{\"pattern\":\"${escaped}\"}"
  done

  echo "[${entries}]"
}

# ── Tier → tools.exec JSON 对象 ──────────────────────
tier_to_tools_exec_json() {
  local tier="$1"
  case "$tier" in
    T0) echo '{"host":"gateway","security":"deny","ask":"off"}' ;;
    T1) echo '{"host":"gateway","security":"allowlist","ask":"off"}' ;;
    T2) echo '{"host":"gateway","security":"allowlist","ask":"off"}' ;;
    T3) echo '{"host":"gateway","security":"full","ask":"off"}' ;;
    *)  echo '{"host":"gateway","security":"deny","ask":"off"}' ;;
  esac
}

# ── 生成/更新 exec-approvals.json ────────────────────
# 参数: exec_approvals_path agent_configs_json
#   agent_configs_json 格式: {"agentId":{"security":"..","ask":"..","allowlist":[...]}}
#
# 策略：
#   - 保留已有的 socket 配置（path + token）
#   - 设置全局 defaults（deny + off）
#   - 合并内置 crew 的 agent 条目（覆盖已有的内置 crew 配置）
#   - 保留非内置 crew 的 agent 条目不动
generate_exec_approvals() {
  local exec_approvals_path="$1"
  local agent_configs_json="$2"

  EXEC_APPROVALS_PATH="$exec_approvals_path" \
  AGENT_CONFIGS="$agent_configs_json" \
  node -e '
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const filePath = process.env.EXEC_APPROVALS_PATH;
const agentConfigs = JSON.parse(process.env.AGENT_CONFIGS);

// 读取已有文件（保留 socket 等）
let existing = { version: 1 };
try {
  if (fs.existsSync(filePath)) {
    existing = JSON.parse(fs.readFileSync(filePath, "utf8"));
  }
} catch { /* 损坏时重建 */ }

// 保留已有 socket 配置，没有则生成
const socket = existing.socket || {};
if (!socket.path) socket.path = "~/.openclaw/exec-approvals.sock";
if (!socket.token) socket.token = crypto.randomBytes(24).toString("base64url");

// wiseflow 全局默认：deny + off（飞书无审批 UI）
const defaults = {
  security: "deny",
  ask: "off",
  askFallback: "deny",
  autoAllowSkills: false,
};

// 合并 agents 配置
const agents = existing.agents || {};
for (const [agentId, config] of Object.entries(agentConfigs)) {
  const prev = agents[agentId] || {};
  // 为 allowlist 条目补 id
  const allowlist = (config.allowlist || []).map((entry) => ({
    id: crypto.randomUUID(),
    ...entry,
  }));
  agents[agentId] = {
    security: config.security,
    ask: config.ask || "off",
    askFallback: config.askFallback || "deny",
    ...(allowlist.length > 0 ? { allowlist } : {}),
  };
}

const result = {
  version: 1,
  socket,
  defaults,
  agents,
};

// 确保目录存在
fs.mkdirSync(path.dirname(filePath), { recursive: true });
fs.writeFileSync(filePath, JSON.stringify(result, null, 2) + "\n", { mode: 0o600 });
'
}

# ── 高层接口：为一组 agents 计算并写入 exec 配置 ─────
# 参数: config_path exec_approvals_path crews_dir project_root
# 读取每个已注册 crew 的 tier，生成 tools.exec + exec-approvals
apply_exec_tiers() {
  local config_path="$1"
  local exec_approvals_path="$2"
  local crews_dir="$3"
  local project_root="$4"

  # 收集所有已注册 crew 的 exec 配置
  local agent_configs="{}"
  local tools_exec_patches="{}"

  local agent_entries=""
  agent_entries="$(CONFIG_PATH="$config_path" node -e '
const fs = require("fs");
const home = process.env.HOME || "";
const c = JSON.parse(fs.readFileSync(process.env.CONFIG_PATH, "utf8"));
for (const a of (c.agents?.list || [])) {
  if (!a || typeof a.id !== "string" || !a.id.trim()) continue;
  const id = a.id.trim();
  const wsRaw = typeof a.workspace === "string" && a.workspace.trim()
    ? a.workspace.trim()
    : ("~/.openclaw/workspace-" + id);
  const ws = wsRaw.replace(/^~(?=\/|$)/, home);
  console.log(id + "\t" + ws);
}
')"

  while IFS=$'\t' read -r agent_id workspace_dir; do
    [ -n "$agent_id" ] || continue
    [ -n "$workspace_dir" ] || workspace_dir="$HOME/.openclaw/workspace-$agent_id"
    local soul_file="$workspace_dir/SOUL.md"
    local crew_type
    crew_type="$(resolve_crew_type "$soul_file")"

    # 优先读取实例 workspace 的 ALLOWED_COMMANDS；缺失时回退模板目录
    local allowed_cmds_file="$workspace_dir/ALLOWED_COMMANDS"
    if [ ! -f "$allowed_cmds_file" ] && [ -f "$crews_dir/$agent_id/ALLOWED_COMMANDS" ]; then
      allowed_cmds_file="$crews_dir/$agent_id/ALLOWED_COMMANDS"
    fi

    # 解析 tier
    local tier
    tier="$(resolve_command_tier "$soul_file")"

    # 解析最终命令列表
    local commands
    commands="$(resolve_tier_commands "$tier" "$allowed_cmds_file")"

    # 生成 allowlist JSON（./ 路径相对于 agent workspace 解析）
    local allowlist_json
    allowlist_json="$(build_exec_allowlist_json "$commands" "$workspace_dir")"

    local t0_has_allowlist="false"
    if [ "$tier" = "T0" ] && [ -n "$(printf '%s' "$commands" | tr -d '[:space:]')" ]; then
      t0_has_allowlist="true"
    fi

    # 生成 tools.exec JSON
    local tools_exec_json
    if [ "$t0_has_allowlist" = "true" ]; then
      tools_exec_json='{"host":"gateway","security":"allowlist","ask":"off"}'
    else
      tools_exec_json="$(tier_to_tools_exec_json "$tier")"
    fi

    # 生成 exec-approvals agent 配置
    local agent_security agent_ask
    case "$tier" in
      T0)
        if [ "$t0_has_allowlist" = "true" ]; then
          agent_security="allowlist"
        else
          agent_security="deny"
        fi
        agent_ask="off"
        ;;
      T1|T2) agent_security="allowlist"; agent_ask="off" ;;
      T3) agent_security="full"; agent_ask="off" ;;
      *) agent_security="deny"; agent_ask="off" ;;
    esac

    local cmd_count
    if [ "$commands" = "__FULL__" ]; then
      cmd_count="full"
    elif [ -z "$allowlist_json" ] || [ "$allowlist_json" = "[]" ]; then
      cmd_count="0"
    else
      # 统计实际生成的 allowlist 条目数（已解析为绝对路径的）
      cmd_count="$(printf '%s' "$allowlist_json" | node -e '
        const j = JSON.parse(require("fs").readFileSync(0,"utf8"));
        console.log(j.length);
      ')"
    fi

    echo "  🔒 $agent_id [$crew_type] → $tier (security=$agent_security, commands=$cmd_count)"

    # 累加到 JSON 对象
    agent_configs="$(PREV="$agent_configs" AID="$agent_id" SEC="$agent_security" ASK="$agent_ask" AL="$allowlist_json" \
      node -e '
const prev = JSON.parse(process.env.PREV);
prev[process.env.AID] = {
  security: process.env.SEC,
  ask: process.env.ASK,
  askFallback: "deny",
  allowlist: JSON.parse(process.env.AL),
};
console.log(JSON.stringify(prev));
')"

    tools_exec_patches="$(PREV="$tools_exec_patches" AID="$agent_id" TEJ="$tools_exec_json" \
      node -e '
const prev = JSON.parse(process.env.PREV);
prev[process.env.AID] = JSON.parse(process.env.TEJ);
console.log(JSON.stringify(prev));
')"
  done <<< "$agent_entries"

  # 写入 exec-approvals.json
  generate_exec_approvals "$exec_approvals_path" "$agent_configs"
  echo "  ✅ exec-approvals.json updated"

  # 写入 agents.list[].tools.exec 到 openclaw.json
  TOOLS_EXEC_PATCHES="$tools_exec_patches" node -e '
const fs = require("fs");
const patches = JSON.parse(process.env.TOOLS_EXEC_PATCHES);
const c = JSON.parse(fs.readFileSync("'"$config_path"'", "utf8"));
const list = c.agents?.list || [];
for (const [agentId, execConfig] of Object.entries(patches)) {
  const idx = list.findIndex((a) => a.id === agentId);
  if (idx >= 0) {
    list[idx] = {
      ...list[idx],
      tools: {
        ...(list[idx].tools || {}),
        exec: execConfig,
      },
    };
  }
}
fs.writeFileSync("'"$config_path"'", JSON.stringify(c, null, 2) + "\n");
'
  echo "  ✅ agents.list[].tools.exec updated"
}
