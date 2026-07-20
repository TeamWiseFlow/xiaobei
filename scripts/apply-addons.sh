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
source "$PROJECT_ROOT/scripts/lib/skill-wrappers.sh"

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

# ─── 补丁应用 helper（两遍：先纯 --3way，失败回退容错 flags） ──────────
# 纯 --3way 对 freshly-generated 补丁最稳，且能正确处理 deleted-file 条目
# （--ignore-whitespace --whitespace=fix 会静默跳过删除）。
# 仅当纯 --3way 失败（如上游 whitespace 漂移）才回退到容错 flags。
apply_patch() {
  local patch="$1"
  echo "  → $(basename "$patch")"
  if git apply --3way "$patch" 2>/dev/null; then
    return 0
  fi
  git apply --3way --ignore-whitespace --whitespace=fix "$patch" 2>/dev/null || {
    echo "  ❌ Failed to apply $(basename "$patch")"
    echo "     Hint: 上游代码可能已变更，需重新生成此补丁"
    exit 1
  }
}

# ─── 应用基础补丁（patches/*.patch，按序号顺序） ─────────────────
PATCHES_DIR="$PROJECT_ROOT/patches"
if ls "$PATCHES_DIR"/*.patch 1>/dev/null 2>&1; then
  # 先数总数，循环里打 [n/N] 进度，避免长时间静默让用户以为死机
  PATCH_TOTAL=$(ls "$PATCHES_DIR"/*.patch 2>/dev/null | wc -l | tr -d ' ')
  echo "🩹 Applying base patches (${PATCH_TOTAL} files)..."
  cd "$OPENCLAW_DIR"
  PATCH_IDX=0
  for patch in $(ls "$PATCHES_DIR"/*.patch | sort); do
    PATCH_IDX=$((PATCH_IDX + 1))
    printf "  [%d/%d] %s\n" "$PATCH_IDX" "$PATCH_TOTAL" "$(basename "$patch")"
    apply_patch "$patch"
  done
  cd "$PROJECT_ROOT"
  NEEDS_INSTALL=true
fi

# ─── 应用浏览器转向 per-file 补丁（patches/browser-camoufox-pivot/patches/）──
# 原 001 monolith（35 文件）按「一个 patch 只改一个上游文件」拆成 35 个单文件
# patch，降低上游漂移时的失效面：一个文件漂只挂一个 patch，其余照常应用。
# 按文件名 sort 顺序应用（各 patch 改不同文件，彼此独立，顺序不影正确性）。
PIVOT_PATCH_DIR="$PROJECT_ROOT/patches/browser-camoufox-pivot/patches"
if ls "$PIVOT_PATCH_DIR"/*.patch 1>/dev/null 2>&1; then
  PIVOT_TOTAL=$(ls "$PIVOT_PATCH_DIR"/*.patch 2>/dev/null | wc -l | tr -d ' ')
  echo "🩹 Applying browser-camoufox-pivot per-file patches (${PIVOT_TOTAL} files)..."
  cd "$OPENCLAW_DIR"
  PIVOT_IDX=0
  for patch in $(ls "$PIVOT_PATCH_DIR"/*.patch | sort); do
    PIVOT_IDX=$((PIVOT_IDX + 1))
    printf "  [%d/%d] %s\n" "$PIVOT_IDX" "$PIVOT_TOTAL" "$(basename "$patch")"
    apply_patch "$patch"
  done
  cd "$PROJECT_ROOT"
  NEEDS_INSTALL=true
fi

# ─── 拷入浏览器转向新文件（patches/browser-camoufox-pivot/files/）──
# per-file patch 只改现有文件；新增的 adapter + 测试以整文件形式 ship 在
# patches/ 下，这里 cp 进 openclaw（git clean 已先跑，所以目标一定是干净上游
# 状态）。spec §12.3 线 1 后端。
PIVOT_FILES_DIR="$PROJECT_ROOT/patches/browser-camoufox-pivot/files"
if [ -d "$PIVOT_FILES_DIR" ]; then
  echo "🌐 Copying browser-camoufox-pivot new files into openclaw..."
  for f in "$PIVOT_FILES_DIR"/*.ts; do
    [ -f "$f" ] || continue
    cp "$f" "$OPENCLAW_DIR/extensions/browser/src/"
    echo "  → extensions/browser/src/$(basename "$f")"
  done
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

# ─── 安装 awada 插件依赖（ws + zod）─────────────────────────────
# awada 走 relay 网关 HTTP/WS 传输，运行时依赖 ws + zod（见 awada/package.json）。
# awada 自己的 node_modules 解析这些依赖，不走 ~/.openclaw/node_modules，
# 故必须装在 awada/ 局部。内容哈希守卫避免重复 install。
AWADA_PKG_HASH_FILE="$OPENCLAW_HOME/.awada-pkg-hash"
if [ -d "$AWADA_EXT" ] && [ -f "$AWADA_EXT/package.json" ]; then
  awada_hash="$(_md5 < "$AWADA_EXT/package.json")"
  awada_stored="$(cat "$AWADA_PKG_HASH_FILE" 2>/dev/null || echo '')"
  if [ "$awada_hash" != "$awada_stored" ] || [ ! -d "$AWADA_EXT/node_modules" ]; then
    echo "📦 Installing awada plugin dependencies (ws + zod)..."
    (cd "$AWADA_EXT" && npm install --omit=dev --no-audit --no-fund --loglevel=warn --registry=https://registry.npmmirror.com) \
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
    if [ -f "${skill_dir}SKILL.md" ]; then
      skill_name="$(basename "$skill_dir")"
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
# 内容哈希守卫：仅当任一 skill 的 package.json 发生变化时才重装。
SKILL_PKG_HASH_FILE="$OPENCLAW_HOME/.skill-pkg-hash"

# 收集所有含 package.json + SKILL.md 的 skill 目录（skills/ + crews/*/skills/）
skill_pkg_dirs=()
while IFS= read -r line; do
  [ -n "$line" ] && skill_pkg_dirs+=("$line")
done < <(node -e "
  const fs = require('fs');
  const path = require('path');
  const roots = ['$PROJECT_ROOT/skills', '$CREWS_DIR'];
  const out = [];
  function scan(dir) {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === 'node_modules' || entry.name === '.git') continue;
      if (!entry.isDirectory()) continue;
      const full = path.join(dir, entry.name);
      if (fs.existsSync(path.join(full, 'SKILL.md')) && fs.existsSync(path.join(full, 'package.json'))) {
        out.push(full);
      }
      scan(full);
    }
  }
  for (const r of roots) scan(r);
  console.log(out.join('\n'));
" 2>/dev/null)

# 哈希所有 skill package.json 内容，作为重装判据
current_pkg_hash=""
for d in "${skill_pkg_dirs[@]}"; do
  current_pkg_hash="$current_pkg_hash$(_md5 < "$d/package.json")"
done
current_pkg_hash="$(printf '%s' "$current_pkg_hash" | _md5)"
stored_pkg_hash="$(cat "$SKILL_PKG_HASH_FILE" 2>/dev/null || echo '')"

if [ "$current_pkg_hash" != "$stored_pkg_hash" ]; then
  if [ ${#skill_pkg_dirs[@]} -gt 0 ]; then
    SKILL_PKG_TOTAL=${#skill_pkg_dirs[@]}
    echo "📦 Installing per-skill Node.js dependencies (${SKILL_PKG_TOTAL} skills)..."
    SKILL_PKG_IDX=0
    for d in "${skill_pkg_dirs[@]}"; do
      SKILL_PKG_IDX=$((SKILL_PKG_IDX + 1))
      printf "  [%d/%d] %s\n" "$SKILL_PKG_IDX" "$SKILL_PKG_TOTAL" "${d#$PROJECT_ROOT/}"
      (cd "$d" && npm install --omit=dev --no-audit --no-fund --loglevel=warn --registry=https://registry.npmmirror.com) \
        || echo "  ⚠️  npm install failed in $d" >&2
    done
    echo "$current_pkg_hash" > "$SKILL_PKG_HASH_FILE"
    echo "✅ Skill dependencies installed (hash: ${current_pkg_hash:0:8})"
  else
    echo "✅ No skill package.json found"
  fi
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
  scan('$CREWS_DIR');
  // 仓根 requirements.txt（全仓统一声明，CLAUDE.md 规范）
  const rootReq = path.join('$PROJECT_ROOT', 'requirements.txt');
  if (fs.existsSync(rootReq)) {
    try {
      fs.readFileSync(rootReq, 'utf8').split(/\\r?\\n/).forEach(line => {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith('#')) lines.add(trimmed);
      });
    } catch {}
  }
  console.log(Array.from(lines).sort().join('\\n'));
" 2>/dev/null || echo '')"

current_pip_hash="$(printf '%s' "$merged_pip_deps" | _md5)"
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
  # pnpm 在算包 hash digest 时（TypedArrayPrototypeJoin → crypto::Hash::OneShotDigest）对大包
  # 一次性 join 整个文件当 TypedArray digest，单 isolate OOM。曾试过 fetch 预拉绕开 digest，
  # 但 pnpm fetch 无脑下所有 optionalDependencies + 平台包（@github/copilot 104MB /
  # @openai/codex 91MB / @zed-industries/codex-acp 65MB），这些 wiseflow 根本不用，fetch 自己就炸。
  # 真根治走 patches 008/009/010/013 把 copilot/codex/acpx/codex-supervisor 四个 extension 的
  # dependencies 段置空 + patches 011/012 删 pnpm-workspace.yaml 的 patchedDependencies + mra-exclude 段——
  # pnpm 解析依赖树时这四个 extension 还是 workspace package 但依赖空，transitive 大包一个都不拉，
  # 根本不触发 digest 段。
  # 不能加 --no-optional：跟 pnpm-lock.yaml 的 optionalDependencies 平台包声明冲突炸
  # ERR_PNPM_LOCKFILE_MISSING_DEPENDENCY（@lydell/node-pty-darwin-arm64 那条）。平台包自己
  # 按 arch 选一个下，体积小不触发 OOM，留着不动。
  # 必须先删 pnpm-lock.yaml：lockfile 里冻结着 patches 改前四个 extension 的完整 dependencies 段，
  # pnpm 跑时会按 lockfile 下 copilot/codex/zed 大包到 store（即使 link 段被 patches 截了），仍触发 OOM。
  # 删了让 pnpm 重新解析依赖树，按当前（已被 patches 改空的）dependencies 段生成新 lockfile。
  # --strict-peer-dependencies=false 容忍 peer 漂移。阿里云镜像 + timeout 10min + 5 重试 + 并发 8 + NODE_OPTIONS 抬 heap 8GB（双保险）
  if [ -f "pnpm-lock.yaml" ]; then
    echo "  → removing stale pnpm-lock.yaml (forces re-resolve, skips frozen copilot/codex/zed entries)"
    rm -f pnpm-lock.yaml
  fi
  NODE_OPTIONS="--max-old-space-size=8192" \
    pnpm install --no-frozen-lockfile --strict-peer-dependencies=false \
      --registry=https://registry.npmmirror.com \
      --fetch-retries=5 --fetch-timeout=600000 --network-concurrency=8
  cd "$PROJECT_ROOT"
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

# ─── camoufox-cli 浏览器二进制（反指纹 Firefox，browser-guide 主推） ──────
# camoufox-cli install 自带幂等：已装版本 === 当前版本时打印 "already up to date" 并返回
# （camoufox-cli/dist/install.js:118）。首次下载 ~557MB；仅当 camoufox-cli npm 包升级
# 导致版本漂移时才重下。用户电脑已有则无害跳过。
if command -v camoufox-cli >/dev/null 2>&1; then
  echo "🌐 Ensuring camoufox browser binary (idempotent)..."
  camoufox-cli install || echo "  ⚠️  camoufox-cli install failed (可后续手动 camoufox-cli install)"
else
  echo "  ⚠️  camoufox-cli not on PATH; skip browser binary. 全局装: npm i -g camoufox-cli"
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
