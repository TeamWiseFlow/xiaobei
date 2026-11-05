#!/bin/bash
# apply-addons.sh - wiseflow 基础能力安装 + 补丁应用 + 配置同步
#
# Phase 7 续精简（2026-07-04）：删除原 addons/ 扫描循环（D8 扁平化后死代码）。
# 本脚本现仅负责：
#   1. 恢复 openclaw/ 到干净状态
#   2. 应用基础补丁（patches/*.patch）+ 依赖覆盖（patches/overrides.sh）
#   3. 安装默认全局 skills（项目根目录 skills/ → ~/.openclaw/skills/）
#   4. 注入 awada 扩展路径 + 同步 openclaw.json skills 节点
#   5. 安装依赖：Node per-skill（node_modules 落仓内技能目录）/ Python 统一安装到小贝自管 venv
#   6. 编译 dist + 重启 gateway service
# Crew 模板安装由 setup-crew.sh 单独负责（扫顶层 crews/）。
#
# 技能两级体系：
#   - 公共 skills: skills/ (项目根目录) → ~/.openclaw/skills/ (managed dir, 所有 Agent 可见)
#   - Agent 专属 skills: crews/<template>/skills/ → 由 setup-crew.sh 安装到 workspace
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$PROJECT_ROOT/scripts/lib/download-network.sh"
xiaobei_configure_download_network "$PROJECT_ROOT"
CREWS_DIR="$PROJECT_ROOT/crews"
OPENCLAW_DIR="$PROJECT_ROOT/openclaw"
OPENCLAW_HOME="$HOME/.openclaw"
CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-$OPENCLAW_HOME/openclaw.json}"
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
source "$PROJECT_ROOT/scripts/lib/skill-wrappers.sh"
node "$PROJECT_ROOT/scripts/python-runtime.mjs" install --root "$PROJECT_ROOT"
source "$PROJECT_ROOT/scripts/lib/python-runtime.sh"
xiaobei_use_python_runtime "$PROJECT_ROOT"
if [ -f "$CONFIG_PATH" ]; then
  node "$PROJECT_ROOT/scripts/python-runtime.mjs" configure --root "$PROJECT_ROOT" --config "$CONFIG_PATH"
fi

# 便携 md5：读 stdin 输出裸 hash。
# Linux md5sum / macOS md5 命令名不同，且 macOS 无 md5sum（set -e 下会 abort）。
# python3 是 openclaw 硬依赖，hashlib 跨平台最稳。
_md5() {
  python3 -c 'import hashlib,sys; print(hashlib.md5(sys.stdin.buffer.read()).hexdigest())'
}

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

# Source-only patch entry also supports local upgrade validation.
bash "$PROJECT_ROOT/patches/apply.sh"
NEEDS_INSTALL=true

# ─── 同步 skills / plugins 默认配置（从 config-templates 到运行配置）──────
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

    // 补齐模板中默认禁用的插件；保留用户已有的启用状态和插件配置。
    if (template.plugins?.entries) {
      if (!running.plugins) running.plugins = {};
      if (!running.plugins.entries) running.plugins.entries = {};
      for (const [name, entry] of Object.entries(template.plugins.entries)) {
        if (entry?.enabled === false && !(name in running.plugins.entries)) {
          running.plugins.entries[name] = clone(entry);
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

    // 补齐原生搜索开关，替代旧环境变量补丁；保留用户显式设置。
    const searchEnabled = template.tools?.web?.search?.enabled;
    if (typeof searchEnabled === 'boolean' && running.tools?.web?.search?.enabled === undefined) {
      running.tools ??= {};
      running.tools.web ??= {};
      running.tools.web.search ??= {};
      running.tools.web.search.enabled = searchEnabled;
      changed = true;
    }

    // 补齐运行日志默认值；保留用户已有的级别、路径和轮转大小。
    for (const [key, value] of Object.entries(template.logging ?? {})) {
      running.logging ??= {};
      if (running.logging[key] === undefined) {
        running.logging[key] = clone(value);
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
  echo "📝 Skills and plugin defaults synchronized"
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

# ─── 安装 awada 插件依赖（silk-wasm + typebox + ws + zod）─────────────────────────────
# awada 走 relay 网关 HTTP/WS 传输，运行时依赖 silk-wasm + typebox + ws + zod（见 awada/package.json）。
# awada 自己的 node_modules 解析这些依赖，不走 ~/.openclaw/node_modules，
# 故必须装在 awada/ 局部。内容哈希守卫避免重复 install。
AWADA_PKG_HASH_FILE="$OPENCLAW_HOME/.awada-pkg-hash"
if [ -d "$AWADA_EXT" ] && [ -f "$AWADA_EXT/package.json" ]; then
  awada_hash="$(_md5 < "$AWADA_EXT/package.json")"
  awada_stored="$(cat "$AWADA_PKG_HASH_FILE" 2>/dev/null || echo '')"
  if [ "$awada_hash" != "$awada_stored" ] || [ ! -d "$AWADA_EXT/node_modules" ]; then
    echo "📦 Installing awada plugin dependencies (silk-wasm + typebox + ws + zod)..."
    # 裸机/本地走 npmmirror 国内镜像；镜像构建时 ENV NPM_REGISTRY 写死 npmjs（海外构建机不跨境）
    npm_reg="${NPM_REGISTRY:-https://registry.npmmirror.com}"
    (cd "$AWADA_EXT" && npm install --omit=dev --no-audit --no-fund --loglevel=warn --registry="$npm_reg") \
      && echo "$awada_hash" > "$AWADA_PKG_HASH_FILE" \
      && echo "✅ awada dependencies installed" \
      || echo "  ⚠️  awada npm install failed (可后续手动 cd $AWADA_EXT && pnpm install --prod)" >&2
  else
    echo "✅ awada dependencies up to date"
  fi
fi


# ─── 安装全局共享技能（项目根目录 skills/） ──────────────────────
# 软链而非拷贝：skill 在仓里改完即生效，运行实例无需重跑 setup。
# openclaw skill loader 跟随软链（local-loader.ts readdirSync isDirectory + realpathSync）。
GLOBAL_SKILL_COUNT=0
if [ -d "$PROJECT_ROOT/skills" ]; then
  mkdir -p "$OPENCLAW_HOME/skills"
  for skill_dir in "$PROJECT_ROOT"/skills/*/; do
    [ -d "$skill_dir" ] || continue
    skill_name="$(basename "$skill_dir")"
    # 公共共享库随技能一起部署，不作为可调用 skill 加入 allowlist。
    if [ "$skill_name" = "_shared" ]; then
      rm -rf "$OPENCLAW_HOME/skills/$skill_name"
      ln -s "${skill_dir%/}" "$OPENCLAW_HOME/skills/$skill_name"
      continue
    fi
    if [ -f "${skill_dir}SKILL.md" ]; then
      rm -rf "$OPENCLAW_HOME/skills/$skill_name"
      ln -s "${skill_dir%/}" "$OPENCLAW_HOME/skills/$skill_name"
      GLOBAL_SKILL_COUNT=$((GLOBAL_SKILL_COUNT + 1))
      append_global_shared_skill "$skill_name"
    fi
  done
fi
if [ "$GLOBAL_SKILL_COUNT" -gt 0 ]; then
  echo "📦 Global skills installed ($GLOBAL_SKILL_COUNT)"
fi

# ─── 暴露公共 skill 顶层 wrapper → ~/.openclaw/bin/（PATH 友好） ───
# D21 wrapper 覆盖：每个含 <skill>/<skill>.sh 的 skill 建一条 symlink 到
# ~/.openclaw/bin/<skill>，agent 调 `<skill> <cmd>` 零路径拼接。
# 同时把 ~/.openclaw/bin 注入 shell rc 的 PATH（幂等）。
expose_skill_wrappers "$PROJECT_ROOT/skills"
ensure_openclaw_bin_in_path


# ─── 安装各 skill 的 Node.js 依赖（per-skill，写进仓内 skill 目录）─────
# skill 走软链部署后，Node 从脚本 realpath（仓内 skill 目录）向上解析模块，
# 命中 skill 自己的 node_modules。故对每个含 package.json 的 skill 单独
# npm install --omit=dev，node_modules 落在仓内 skill 目录（.gitignore 已覆盖
# node_modules/ 与 package-lock.json），不污染 ~/.openclaw。
# 内容哈希 + 本地依赖存在性检查；任何安装失败都不写成功哈希。
node "$PROJECT_ROOT/scripts/install-skill-deps.mjs" \
  --root "$PROJECT_ROOT" --state-dir "$OPENCLAW_HOME"

# Python dependencies were installed in the managed venv before workspace setup.

# 有 overrides 或 patches 时才需要同步依赖
if [ "$NEEDS_INSTALL" = "true" ]; then
  echo "📦 Syncing dependencies..."
  cd "$OPENCLAW_DIR"
  # Preserve the upstream dependency graph and lockfile.
  NODE_OPTIONS="--max-old-space-size=8192" pnpm install --frozen-lockfile
  cd "$PROJECT_ROOT"
fi

# ─── 写入全局共享 skills 清单（供 skills allowlist 计算使用） ──────
mkdir -p "$OPENCLAW_HOME"
printf '%s\n' "$GLOBAL_SHARED_SKILLS_RAW" \
  | awk 'NF && !seen[$0]++' \
  | sort > "$GLOBAL_SHARED_SKILLS_FILE"
GLOBAL_SHARED_COUNT="$(wc -l < "$GLOBAL_SHARED_SKILLS_FILE" | tr -d ' ')"
echo "🧾 Global shared skills catalog updated ($GLOBAL_SHARED_COUNT)"

# ─── 重新同步 agents.entries.<id>.skills（纳入最新全局 skills）──────────
if [ "$SKIP_CREW" = "true" ]; then
  echo "⏭️  Skipping setup-crew.sh (--skip-crew)"
elif [ -f "$CONFIG_PATH" ] && [ -x "$PROJECT_ROOT/scripts/setup-crew.sh" ]; then
  if [ "$FORCE" = "true" ]; then
    XIAOBEI_DEFER_EXEC_APPROVALS=1 CALLED_FROM_APPLY_ADDONS=true "$PROJECT_ROOT/scripts/setup-crew.sh" --force
  else
    XIAOBEI_DEFER_EXEC_APPROVALS=1 CALLED_FROM_APPLY_ADDONS=true "$PROJECT_ROOT/scripts/setup-crew.sh"
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

# ─── Build the product browser; installation/cutover belongs to the installer ───
npm ci --ignore-scripts --prefix "$PROJECT_ROOT/browser"
npm run build --prefix "$PROJECT_ROOT/browser"

# The custom plugin owns the tool and cross-command browser lifecycle.
node "$PROJECT_ROOT/scripts/configure-browser-plugin.mjs" --root "$PROJECT_ROOT" --config "$CONFIG_PATH" --write

# 纯构建/打包环境没有运行配置，不初始化用户状态。
if [ -f "$CONFIG_PATH" ]; then
  # Migrate with the newly built host, validate, then stamp meta only after success.
  node "$PROJECT_ROOT/scripts/migrate-openclaw-config.mjs" --config "$CONFIG_PATH" --write

  # Explicit offline schema/state repair. The upstream update guard blocks runtime/service repair.
  OPENCLAW_UPDATE_IN_PROGRESS=1 OPENCLAW_CONFIG_PATH="$CONFIG_PATH" \
    node "$OPENCLAW_DIR/dist/index.js" doctor --fix --non-interactive --no-workspace-suggestions

  # 只让完成构建和状态迁移的新引擎更新宿主审批；不再生成 legacy JSON。
  if [ "$SKIP_CREW" != "true" ]; then
    source "$PROJECT_ROOT/scripts/lib/agent-skills.sh"
    source "$PROJECT_ROOT/scripts/lib/exec-tiers.sh"
    apply_exec_tiers "$CONFIG_PATH" "$PROJECT_ROOT/crews" "$PROJECT_ROOT"
  fi
fi

# ─── 重启 gateway service（如果正在运行） ─────────────────────────
if [ "$NO_RESTART" = "true" ]; then
  echo "⏭️  Skipping gateway restart (--no-restart)"
elif [ "$(uname -s)" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
  SERVICE_NAME="openclaw-gateway"
  # 2026.10.x 已退役安装时版本戳；不能继续给 Description 写版本号。
  UNIT_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/${SERVICE_NAME}.service"
  if [ -f "$UNIT_FILE" ]; then
    node "$PROJECT_ROOT/scripts/refresh-gateway-service-metadata.mjs" "$UNIT_FILE"
    systemctl --user daemon-reload 2>/dev/null || true
  fi
  if systemctl --user is-active "$SERVICE_NAME.service" >/dev/null 2>&1; then
    echo "🔄 Restarting $SERVICE_NAME.service..."
    systemctl --user restart "$SERVICE_NAME.service"
    echo "✅ Gateway restarted"
  fi
fi
