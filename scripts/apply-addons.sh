#!/bin/bash
# apply-addons.sh - wiseflow 基础能力安装 + 补丁应用 + 配置同步
#
# Phase 7 续精简（2026-07-04）：删除原 addons/ 扫描循环（D8 扁平化后死代码）。
# 本脚本现仅负责：
#   1. 恢复 openclaw/ 到干净状态
#   2. 应用基础补丁（patches/*.patch）+ 依赖覆盖（patches/overrides.sh）
#   3. 安装默认全局 skills（项目根目录 skills/ → ~/.openclaw/skills/）
#   4. 注入 awada 扩展路径 + 同步 openclaw.json skills 节点
#   5. 合并全仓 npm / pip 依赖到 ~/.openclaw/node_modules + ~/.openclaw/lib/python
#   6. 编译 dist + 重启 gateway service
# Crew 模板安装由 setup-crew.sh 单独负责（扫顶层 crews/）。
#
# 技能两级体系：
#   - 公共 skills: skills/ (项目根目录) → ~/.openclaw/skills/ (managed dir, 所有 Agent 可见)
#   - Agent 专属 skills: crews/<template>/skills/ → 由 setup-crew.sh 安装到 workspace
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CREWS_DIR="$PROJECT_ROOT/crews"
OPENCLAW_DIR="$PROJECT_ROOT/openclaw"
OPENCLAW_HOME="$HOME/.openclaw"
CONFIG_PATH="$OPENCLAW_HOME/openclaw.json"
GLOBAL_SHARED_SKILLS_FILE="$OPENCLAW_HOME/GLOBAL_SHARED_SKILLS"
FORCE=false
SKIP_CREW=false
NO_BUILD=false
NO_RESTART=false

while [ $# -gt 0 ]; do
  case "$1" in
    --force)
      FORCE=true
      shift
      ;;
    --skip-crew)
      SKIP_CREW=true
      shift
      ;;
    --no-build)
      NO_BUILD=true
      shift
      ;;
    --no-restart)
      NO_RESTART=true
      shift
      ;;
    *)
      echo "❌ Unknown option: $1"
      echo "Usage: $0 [--force] [--skip-crew] [--no-build] [--no-restart]"
      exit 1
      ;;
  esac
done

source "$PROJECT_ROOT/scripts/lib/crew-workspaces.sh"

GLOBAL_SHARED_SKILLS_RAW=""
append_global_shared_skill() {
  local skill_name="$1"
  [ -n "$skill_name" ] || return 0
  GLOBAL_SHARED_SKILLS_RAW="${GLOBAL_SHARED_SKILLS_RAW}
$skill_name"
}

NEEDS_INSTALL=false

# ─── 恢复上游到干净状态 ──────────────────────────────────────────
cd "$OPENCLAW_DIR"
git reset --hard HEAD 2>/dev/null || true
# 清理 patches 创建的新文件（reset --hard 不删除 untracked 文件）
git clean -fd -- src/ extensions/ 2>/dev/null || true
cd "$PROJECT_ROOT"

# ─── 应用基础依赖覆盖（patches/overrides.sh） ─────────────────────
if [ -f "$PROJECT_ROOT/patches/overrides.sh" ]; then
  echo "🔧 Applying base overrides..."
  ADDON_DIR="$PROJECT_ROOT/patches" OPENCLAW_DIR="$OPENCLAW_DIR" bash "$PROJECT_ROOT/patches/overrides.sh"
  NEEDS_INSTALL=true
fi

# ─── 应用基础补丁（patches/*.patch，按序号顺序） ─────────────────
PATCHES_DIR="$PROJECT_ROOT/patches"
if ls "$PATCHES_DIR"/*.patch 1>/dev/null 2>&1; then
  echo "🩹 Applying base patches..."
  cd "$OPENCLAW_DIR"
  for patch in $(ls "$PATCHES_DIR"/*.patch | sort); do
    echo "  → $(basename "$patch")"
    git apply --3way --ignore-whitespace --whitespace=fix "$patch" || {
      echo "  ❌ Failed to apply $(basename "$patch")"
      echo "     Hint: 上游代码可能已变更，需重新生成此补丁"
      exit 1
    }
  done
  cd "$PROJECT_ROOT"
  NEEDS_INSTALL=true
fi

# ─── 同步 skills 禁用配置（从 config-templates 到运行配置）──────
if [ -f "$CONFIG_PATH" ] && [ -f "$PROJECT_ROOT/config-templates/openclaw.json" ]; then
  node -e "
    const fs = require('fs');
    const running = JSON.parse(fs.readFileSync('$CONFIG_PATH', 'utf8'));
    const template = JSON.parse(fs.readFileSync('$PROJECT_ROOT/config-templates/openclaw.json', 'utf8'));
    const clone = (value) => {
      if (value && typeof value === 'object') return JSON.parse(JSON.stringify(value));
      return value;
    };
    let changed = false;

    // 同步 skills.entries：
    //   enabled: true  → 强制覆写（wiseflow 功能依赖，必须保证开启）
    //   enabled: false → 仅在运行配置中尚无该条目时写��（首次初始化语义，
    //                    保留用户已主动开启的配置，不回退）
    if (template.skills?.entries) {
      if (!running.skills) running.skills = {};
      if (!running.skills.entries) running.skills.entries = {};
      for (const [name, entry] of Object.entries(template.skills.entries)) {
        if (entry && entry.enabled === true) {
          // 强制写入：确保 wiseflow 依赖的技能始终开启
          running.skills.entries[name] = entry;
          changed = true;
        } else if (!(name in running.skills.entries)) {
          // 首次写入：用户从未配置过此条目才写默认值
          running.skills.entries[name] = entry;
          changed = true;
        }
      }
    }

    // 同步 tools.exec 配置（避免 WSL/Linux 下 sandbox 默认导致 exec 失败）
    if (template.tools?.exec) {
      if (!running.tools) running.tools = {};
      if (!running.tools.exec) running.tools.exec = {};
      for (const [key, value] of Object.entries(template.tools.exec)) {
        running.tools.exec[key] = value;
        changed = true;
      }
    }

    // 同步 session.dmScope 默认值（外部 crew 需要 per-channel-peer 隔离）
    if (template.session?.dmScope) {
      if (!running.session) running.session = {};
      if (running.session.dmScope !== template.session.dmScope) {
        running.session.dmScope = template.session.dmScope;
        changed = true;
      }
    }

    // 同步 hooks.internal.entries 配置（确保 boot-md 等 hook 开关与模板一致）
    if (template.hooks?.internal?.entries) {
      if (!running.hooks) running.hooks = {};
      if (!running.hooks.internal) running.hooks.internal = {};
      if (!running.hooks.internal.entries) running.hooks.internal.entries = {};
      for (const [name, entry] of Object.entries(template.hooks.internal.entries)) {
        running.hooks.internal.entries[name] = entry;
        changed = true;
      }
    }

    // 规范 Feishu 多账号配置：将顶层 single-account 字段下沉到 accounts.*
    // 避免启动时触发 Doctor 迁移提示：
    // \"Moved channels.feishu single-account top-level values into channels.feishu.accounts.default.\"
    const feishu = running.channels?.feishu;
    if (feishu && typeof feishu === 'object' && !Array.isArray(feishu)) {
      const accounts = feishu.accounts;
      if (accounts && typeof accounts === 'object' && !Array.isArray(accounts)) {
        const accountEntries = Object.entries(accounts);
        if (accountEntries.length > 0) {
          const keysToMove = ['dmPolicy', 'allowFrom', 'groupPolicy', 'groupAllowFrom', 'defaultTo'];
          const topLevelValues = {};
          for (const key of keysToMove) {
            if (feishu[key] !== undefined) topLevelValues[key] = feishu[key];
          }
          if (Object.keys(topLevelValues).length > 0) {
            const nextAccounts = {};
            for (const [accountId, rawAccount] of accountEntries) {
              const account =
                rawAccount && typeof rawAccount === 'object' && !Array.isArray(rawAccount)
                  ? { ...rawAccount }
                  : {};
              for (const [key, value] of Object.entries(topLevelValues)) {
                if (account[key] === undefined) account[key] = clone(value);
              }
              nextAccounts[accountId] = account;
            }
            for (const key of Object.keys(topLevelValues)) {
              delete feishu[key];
            }
            feishu.accounts = nextAccounts;
            changed = true;
          }
        }
      }
    }

    if (changed) {
      fs.writeFileSync('$CONFIG_PATH', JSON.stringify(running, null, 2) + '\n');
    }
  "
  echo "📝 Skills configuration synchronized"
fi

# ─── 注入 awada 扩展路径（绝对路径，避免 CWD 依赖）──────────────
AWADA_EXT="$PROJECT_ROOT/awada"
if [ -d "$AWADA_EXT" ] && [ -f "$AWADA_EXT/openclaw.plugin.json" ]; then
  if [ -f "$CONFIG_PATH" ]; then
    node -e "
      const fs = require('fs');
      const config = JSON.parse(fs.readFileSync('$CONFIG_PATH', 'utf8'));
      if (!config.plugins) config.plugins = {};
      if (!config.plugins.load) config.plugins.load = {};
      if (!Array.isArray(config.plugins.load.paths)) config.plugins.load.paths = [];
      const awadaPath = '$AWADA_EXT';
      // 先移除所有结尾匹配 awada/awada-extension 的旧路径（跨机器迁移时清理残留）
      config.plugins.load.paths = config.plugins.load.paths.filter(
        p => !p.endsWith('awada/awada-extension') && !p.endsWith('/awada')
      );
      config.plugins.load.paths.push(awadaPath);
      if (!config.plugins.entries) config.plugins.entries = {};
      if (!config.plugins.entries.awada) {
        config.plugins.entries.awada = { enabled: false };
      }
      fs.writeFileSync('$CONFIG_PATH', JSON.stringify(config, null, 2) + '\n');
    "
    echo "📝 Awada extension path injected"
  fi
fi


# ─── 安装全局共享技能（项目根目录 skills/） ──────────────────────
GLOBAL_SKILL_COUNT=0
if [ -d "$PROJECT_ROOT/skills" ]; then
  mkdir -p "$OPENCLAW_HOME/skills"
  for skill_dir in "$PROJECT_ROOT"/skills/*/; do
    if [ -f "${skill_dir}SKILL.md" ]; then
      skill_name="$(basename "$skill_dir")"
      rm -rf "$OPENCLAW_HOME/skills/$skill_name"
      cp -r "${skill_dir%/}" "$OPENCLAW_HOME/skills/$skill_name"
      GLOBAL_SKILL_COUNT=$((GLOBAL_SKILL_COUNT + 1))
      append_global_shared_skill "$skill_name"
    fi
  done
fi
if [ "$GLOBAL_SKILL_COUNT" -gt 0 ]; then
  echo "📦 Global skills installed ($GLOBAL_SKILL_COUNT)"
fi


# ─── 安装全仓统一 Node.js 依赖到 ~/.openclaw/node_modules ──────────
# 扫描 skills/ 和 addons/ 下所有 package.json，合并 dependencies。
# 内容哈希守卫：仅当依赖集发生变化（或 node_modules 不存在）时才执行 npm install。
# Node.js 从 ~/.openclaw/skills/**  或 ~/.openclaw/workspace-**/skills/** 运行脚本时，
# 向上解析模块会自然命中 ~/.openclaw/node_modules，无需 NODE_PATH 也无需改脚本。
SKILL_PKG_HASH_FILE="$OPENCLAW_HOME/.skill-pkg-hash"

merged_deps_json="$(node -e "
  const fs = require('fs');
  const path = require('path');
  const deps = {};
  function scan(dir) {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === 'node_modules' || entry.name === '.git') continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        scan(full);
      } else if (entry.name === 'package.json') {
        try {
          const pkg = JSON.parse(fs.readFileSync(full, 'utf8'));
          Object.assign(deps, pkg.dependencies || {});
        } catch {}
      }
    }
  }
  scan('$PROJECT_ROOT/skills');
  scan('$ADDONS_DIR');
  const sorted = Object.fromEntries(Object.entries(deps).sort());
  console.log(JSON.stringify(sorted));
" 2>/dev/null || echo '{}')"

current_pkg_hash="$(echo "$merged_deps_json" | md5sum | cut -d' ' -f1)"
stored_pkg_hash="$(cat "$SKILL_PKG_HASH_FILE" 2>/dev/null || echo '')"

if [ "$current_pkg_hash" != "$stored_pkg_hash" ] || [ ! -d "$OPENCLAW_HOME/node_modules" ]; then
  echo "📦 Installing skill Node.js dependencies to ~/.openclaw/..."
  MERGED_DEPS="$merged_deps_json" SKILL_OPENCLAW_HOME="$OPENCLAW_HOME" node -e "
    const deps = JSON.parse(process.env.MERGED_DEPS);
    const pkg = { name: 'openclaw-skills', version: '1.0.0', private: true, dependencies: deps };
    require('fs').writeFileSync(
      require('path').join(process.env.SKILL_OPENCLAW_HOME, 'package.json'),
      JSON.stringify(pkg, null, 2) + '\n'
    );
  "
  npm install --prefix "$OPENCLAW_HOME" --no-audit --no-fund --loglevel=warn
  echo "$current_pkg_hash" > "$SKILL_PKG_HASH_FILE"
  echo "✅ Skill dependencies installed (hash: ${current_pkg_hash:0:8})"
else
  echo "✅ Skill dependencies up to date (hash: ${current_pkg_hash:0:8})"
fi

# ─── 安装全仓统一 Python 依赖（pip --user）──────────────────────
# 扫描 skills/、addons/、crews/ 下所有 requirements.txt，合并去重。
# 内容哈希守卫：仅当依赖集发生变化时才执行 pip install。
# 优先使用 pip install --user；若不可用则回退 --break-system-packages。
PIP_HASH_FILE="$OPENCLAW_HOME/.skill-pip-hash"

merged_pip_deps="$(node -e "
  const fs = require('fs');
  const path = require('path');
  const lines = new Set();
  function scan(dir) {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === 'node_modules' || entry.name === '.git') continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        scan(full);
      } else if (entry.name === 'requirements.txt') {
        try {
          const content = fs.readFileSync(full, 'utf8');
          content.split(/\\r?\\n/).forEach(line => {
            const trimmed = line.trim();
            if (trimmed && !trimmed.startsWith('#')) lines.add(trimmed);
          });
        } catch {}
      }
    }
  }
  scan('$PROJECT_ROOT/skills');
  scan('$ADDONS_DIR');
  scan('$CREWS_DIR');
  console.log(Array.from(lines).sort().join('\\n'));
" 2>/dev/null || echo '')"

current_pip_hash="$(echo "$merged_pip_deps" | md5sum | cut -d' ' -f1)"
stored_pip_hash="$(cat "$PIP_HASH_FILE" 2>/dev/null || echo '')"

if [ -n "$merged_pip_deps" ] && { [ "$current_pip_hash" != "$stored_pip_hash" ] || [ ! -f "$PIP_HASH_FILE" ]; }; then
  # 查找可用的 pip 命令：pip → pip3 → python3 -m pip
  PIP_CMD=""
  if command -v pip &>/dev/null; then
    PIP_CMD="pip"
  elif command -v pip3 &>/dev/null; then
    PIP_CMD="pip3"
  elif python3 -m pip --version &>/dev/null; then
    PIP_CMD="python3 -m pip"
  fi

  if [ -z "$PIP_CMD" ]; then
    echo "  ⚠️  pip not found. Attempting to bootstrap pip via get-pip.py..." >&2
    if curl -fsSL https://mirrors.aliyun.com/pypi/simple/pip/ &>/dev/null; then
      curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py && \
      python3 /tmp/get-pip.py --user -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com && \
      rm -f /tmp/get-pip.py
      # 重新检测
      if command -v pip &>/dev/null; then
        PIP_CMD="pip"
      elif command -v pip3 &>/dev/null; then
        PIP_CMD="pip3"
      elif python3 -m pip --version &>/dev/null; then
        PIP_CMD="python3 -m pip"
      fi
    fi
  fi

  if [ -z "$PIP_CMD" ]; then
    echo "  ❌ pip not available. Install it with: sudo apt install python3-pip" >&2
  else
    echo "🐍 Installing skill Python dependencies ($PIP_CMD --user)..."
    # 写入合并后的 requirements 文件
    pip_req_tmp="$OPENCLAW_HOME/.skill-requirements.txt"
    echo "$merged_pip_deps" > "$pip_req_tmp"

    pip_install_flags="--user --quiet --no-warn-script-location -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com"
    if ! $PIP_CMD install $pip_install_flags -r "$pip_req_tmp" 2>/dev/null; then
      echo "  ⚠️  pip --user failed, retrying with --break-system-packages..."
      pip_install_flags="--break-system-packages --user --quiet --no-warn-script-location -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com"
      if ! $PIP_CMD install $pip_install_flags -r "$pip_req_tmp"; then
        echo "  ❌ pip install failed" >&2
      else
        echo "$current_pip_hash" > "$PIP_HASH_FILE"
        echo "✅ Python dependencies installed (hash: ${current_pip_hash:0:8})"
      fi
    else
      echo "$current_pip_hash" > "$PIP_HASH_FILE"
      echo "✅ Python dependencies installed (hash: ${current_pip_hash:0:8})"
    fi
    rm -f "$pip_req_tmp"
  fi
else
  if [ -n "$merged_pip_deps" ]; then
    echo "✅ Python dependencies up to date (hash: ${current_pip_hash:0:8})"
  fi
fi

# 有 overrides 或 patches 时才需要同步依赖
if [ "$NEEDS_INSTALL" = "true" ]; then
  echo "📦 Syncing dependencies..."
  cd "$OPENCLAW_DIR"
  pnpm install --frozen-lockfile=false
  cd "$PROJECT_ROOT"
fi

if [ "$ADDON_COUNT" -gt 0 ]; then
  echo "✅ All addons applied ($ADDON_COUNT loaded)"
else
  echo "📦 No addons found"
fi

# ─── 写入全局共享 skills 清单（供 skills allowlist 计算使用） ──────
mkdir -p "$OPENCLAW_HOME"
printf '%s\n' "$GLOBAL_SHARED_SKILLS_RAW" \
  | awk 'NF && !seen[$0]++' \
  | sort > "$GLOBAL_SHARED_SKILLS_FILE"
GLOBAL_SHARED_COUNT="$(wc -l < "$GLOBAL_SHARED_SKILLS_FILE" | tr -d ' ')"
echo "🧾 Global shared skills catalog updated ($GLOBAL_SHARED_COUNT)"

# ─── 重新同步 agents.list[].skills（纳入最新全局 skills）──────────
if [ "$SKIP_CREW" = "true" ]; then
  echo "⏭️  Skipping setup-crew.sh (--skip-crew)"
elif [ -f "$CONFIG_PATH" ] && [ -x "$PROJECT_ROOT/scripts/setup-crew.sh" ]; then
  if [ "$FORCE" = "true" ]; then
    CALLED_FROM_APPLY_ADDONS=true "$PROJECT_ROOT/scripts/setup-crew.sh" --force
  else
    CALLED_FROM_APPLY_ADDONS=true "$PROJECT_ROOT/scripts/setup-crew.sh"
  fi
fi

# ─── 编译 dist（patches 改的是源码，需要 build 才能生效） ──────────
if [ "$NO_BUILD" = "true" ]; then
  echo "⏭️  Skipping pnpm build (--no-build)"
elif [ "$NEEDS_INSTALL" = "true" ]; then
  echo "🔨 Building openclaw (patches applied, dist needs refresh)..."
  cd "$OPENCLAW_DIR"
  pnpm build
  cd "$PROJECT_ROOT"
  echo "✅ Build complete"
fi

# ─── 重启 gateway service（如果正在运行） ─────────────────────────
if [ "$NO_RESTART" = "true" ]; then
  echo "⏭️  Skipping gateway restart (--no-restart)"
elif [ "$(uname -s)" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
  SERVICE_NAME="openclaw-gateway"
  if systemctl --user is-active "$SERVICE_NAME.service" >/dev/null 2>&1; then
    echo "🔄 Restarting $SERVICE_NAME.service..."
    systemctl --user restart "$SERVICE_NAME.service"
    echo "✅ Gateway restarted"
  fi
fi
