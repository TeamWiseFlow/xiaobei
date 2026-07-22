#!/bin/bash
# update.sh - wiseflow 升级脚本（已 git clone 用户用）
#
# 与 scripts/install.sh 区别：
#   - install.sh = curl 首装路线（从零开始，clone 仓 → build → onboard）
#   - update.sh  = 已 git clone 用户的升级路线（fetch + reset → checkout openclaw → build → daemon reload）
#
# 适用场景：用户已通过 install.sh 装好 wiseflow，后续要拉新版本用此脚本。
# 升级前请确保系统空闲（无 agent 会话正在处理任务）。
#
# 执行流程：
#   1. 验证 wiseflow 项目目录合法性
#   2. 验证 / 重置 git remote（如未初始化或被改）
#   3. git fetch + reset --hard 拉取最新 wiseflow 代码
#   4. 读取 openclaw.version，按锚定版本检出 openclaw 子目录
#      - 若已是目标 commit，跳过耗时的 install
#   5. apply-addons.sh（patches + skills + crew 模板，内含 setup-crew.sh）
#   6. pnpm build（编译 openclaw dist）
#   7. daemon 升级（已装只 reload + restart 不卸装，避免掐断正在跑的会话）
#   8. 微信 channel 插件同步 + meta 回正
set -e

OFB_REPO_DEFAULT="https://github.com/TeamWiseFlow/xiaobei.git"
OFB_REPO_ATOMGIT="https://atomgit.com/wiseflow/xiaobei.git"
# 默认 GitHub；--atomgit 切到 atomgit 国内镜像（git remote 可匿名 fetch/clone，实测可用）
OFB_REPO="$OFB_REPO_DEFAULT"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OPENCLAW_DIR="$PROJECT_ROOT/openclaw"
VERSION_FILE="$PROJECT_ROOT/openclaw.version"
OPENCLAW_HOME="$HOME/.openclaw"
OPENCLAW_CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-$OPENCLAW_HOME/openclaw.json}"
SYSTEMD_ENV_FILE="$OPENCLAW_HOME/daemon.env"
MACOS_GATEWAY_ENV="$OPENCLAW_HOME/service-env/ai.openclaw.gateway.env"
FORCE=false
SKIP_CREW=false
SKIP_WEIXIN=false

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
    --skip-weixin)
      SKIP_WEIXIN=true
      shift
      ;;
    --atomgit)
      # 切到 atomgit 国内镜像 git remote（匿名 fetch 可用，release 资产走 GitCode CDN）
      OFB_REPO="$OFB_REPO_ATOMGIT"
      shift
      ;;
    --github)
      # 显式切回 GitHub（默认即是，保留向后兼容）
      OFB_REPO="$OFB_REPO_DEFAULT"
      shift
      ;;
    *)
      echo "❌ Unknown option: $1"
      echo "Usage: $0 [--force] [--skip-crew] [--skip-weixin] [--atomgit] [--github]"
      echo "  --force        Overwrite existing workspace files (including MEMORY.md)"
      echo "  --skip-crew   Skip setup-crew.sh (only sync addons, no workspace updates)"
      echo "  --skip-weixin Skip bundled/online openclaw-weixin plugin installation"
      echo "  --atomgit     Use atomgit 国内镜像 git remote (default: GitHub)"
      echo "  --github      Use GitHub git remote (default)"
      exit 1
      ;;
  esac
done

cd "$PROJECT_ROOT"

echo "🔧 wiseflow — Install / Upgrade"
echo "   Project root: $PROJECT_ROOT"
echo ""

# ─── 1. 验证当前目录是 wiseflow 项目 ──────────────────────────────────
if [ ! -f "$PROJECT_ROOT/scripts/apply-addons.sh" ] || [ ! -d "$OPENCLAW_DIR" ]; then
  echo "❌ This does not look like a wiseflow project directory."
  echo "   Expected: scripts/apply-addons.sh and openclaw/ subdirectory"
  exit 1
fi

ensure_openclaw_config() {
  if [ ! -f "$OPENCLAW_CONFIG_PATH" ]; then
    mkdir -p "$(dirname "$OPENCLAW_CONFIG_PATH")"
    echo "📝 Creating default config from template..."
    if [ -f "$PROJECT_ROOT/config-templates/openclaw.json" ]; then
      cp "$PROJECT_ROOT/config-templates/openclaw.json" "$OPENCLAW_CONFIG_PATH"
    else
      echo "{}" > "$OPENCLAW_CONFIG_PATH"
    fi
  fi

  # WSL2 环境：注入 noSandbox = true
  if grep -qi microsoft /proc/version 2>/dev/null; then
    node -e '
      const fs = require("fs");
      const p = process.argv[1];
      const c = JSON.parse(fs.readFileSync(p, "utf8"));
      if (!c.browser) c.browser = {};
      if (!c.browser.noSandbox) {
        c.browser.noSandbox = true;
        fs.writeFileSync(p, JSON.stringify(c, null, 2) + "\n");
        console.log("  WSL2 detected: browser.noSandbox = true");
      }
    ' "$OPENCLAW_CONFIG_PATH"
  fi
}

install_weixin_channel() {
  if [ "$SKIP_WEIXIN" = "true" ] || [ "${WISEFLOW_SKIP_WEIXIN_INSTALL:-}" = "true" ]; then
    echo "⏭️  Skipping openclaw-weixin plugin installation"
    return 0
  fi

  echo "💬 Ensuring WeChat channel plugin (openclaw-weixin)..."
  local pin_file="$PROJECT_ROOT/openclaw-weixin.version.json"
  local plugin_pkg="@tencent-weixin/openclaw-weixin"
  local cli_pkg="@tencent-weixin/openclaw-weixin-cli"
  local plugin_version=""
  local cli_version=""
  local plugin_integrity=""
  local vendor_dir="$PROJECT_ROOT/vendor/openclaw-plugins"
  local plugin_tgz=""

  if [ -f "$pin_file" ]; then
    pin_values="$(node -e '
      const fs = require("fs");
      const p = process.argv[1];
      const c = JSON.parse(fs.readFileSync(p, "utf8"));
      const plugin = c["openclaw-weixin"] || {};
      const cli = c["openclaw-weixin-cli"] || {};
      const validPackage = /^@[a-z0-9._-]+\/[a-z0-9._-]+$/;
      const validVersion = /^\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9._-]+)?$/;
      const validIntegrity = /^sha512-[A-Za-z0-9+/]+={0,2}$/;
      for (const [label, entry] of [["plugin", plugin], ["cli", cli]]) {
        if (!validPackage.test(entry.package || "")) throw new Error(`${label}.package invalid`);
        if (!validVersion.test(entry.version || "")) throw new Error(`${label}.version invalid`);
        if (!validIntegrity.test(entry.integrity || "")) throw new Error(`${label}.integrity invalid`);
      }
      console.log([plugin.package, plugin.version, plugin.integrity, cli.package, cli.version].join("\t"));
    ' "$pin_file")" || { echo "❌ Invalid openclaw-weixin.version.json"; exit 1; }
    IFS=$'\t' read -r plugin_pkg plugin_version plugin_integrity cli_pkg cli_version <<< "$pin_values"
  fi

  if [ -n "$plugin_version" ] && [ -d "$vendor_dir" ]; then
    plugin_tgz="$(find "$vendor_dir" -maxdepth 1 -type f \( -name "openclaw-weixin-${plugin_version}.tgz" -o -name "tencent-weixin-openclaw-weixin-${plugin_version}.tgz" \) -print -quit 2>/dev/null || true)"
  fi

  if [ -n "$plugin_tgz" ]; then
    if [ -n "$plugin_integrity" ]; then
      node -e '
        const fs = require("fs");
        const crypto = require("crypto");
        const file = process.argv[1];
        const expected = process.argv[2];
        const actual = "sha512-" + crypto.createHash("sha512").update(fs.readFileSync(file)).digest("base64");
        if (actual !== expected) {
          console.error(`integrity mismatch for ${file}`);
          process.exit(1);
        }
      ' "$plugin_tgz" "$plugin_integrity"
    fi
    if (cd "$OPENCLAW_DIR" && pnpm openclaw plugins install "$plugin_tgz"); then
      echo "  ✅ bundled openclaw-weixin installed"
    else
      echo "❌ Bundled openclaw-weixin install failed"
      echo "   Re-run with --skip-weixin only if you intentionally want to configure the onboarding channel later."
      exit 1
    fi
  elif [ -n "$cli_version" ]; then
    # weixin-cli 内部调用 `openclaw` 命令，需要确保它在 PATH 上
    # 创建临时 wrapper 指向本机 openclaw（pnpm openclaw = node scripts/run-node.mjs）
    _openclaw_wrapper_dir="$(mktemp -d)"
    cat > "$_openclaw_wrapper_dir/openclaw" <<WRAPPER
#!/bin/sh
cd "$OPENCLAW_DIR" && node scripts/run-node.mjs "\$@"
WRAPPER
    chmod +x "$_openclaw_wrapper_dir/openclaw"
    if ! PATH="$_openclaw_wrapper_dir:$PATH" npx -y "${cli_pkg}@${cli_version}" install; then
      rm -rf "$_openclaw_wrapper_dir"
      echo "❌ openclaw-weixin online install failed"
      echo "   Fix network/npm access or re-run with --skip-weixin to configure the onboarding channel later."
      exit 1
    fi
    rm -rf "$_openclaw_wrapper_dir"
  else
    echo "❌ openclaw-weixin CLI version is missing; refusing unpinned online install"
    exit 1
  fi

  node -e '
    const fs = require("fs");
    const p = process.argv[1];
    const c = JSON.parse(fs.readFileSync(p, "utf8"));
    c.plugins = c.plugins || {};
    c.plugins.entries = c.plugins.entries || {};
    c.plugins.entries["openclaw-weixin"] = { ...(c.plugins.entries["openclaw-weixin"] || {}), enabled: true };
    c.channels = c.channels || {};
    c.channels["openclaw-weixin"] = { ...(c.channels["openclaw-weixin"] || {}), enabled: true };
    c.session = { ...(c.session || {}), dmScope: "per-channel-peer" };
    if (!Array.isArray(c.bindings)) c.bindings = [];
    const hasMainWeixin = c.bindings.some((binding) => binding?.agentId === "main" && binding?.match?.channel === "openclaw-weixin");
    if (!hasMainWeixin) {
      c.bindings.push({ agentId: "main", comment: "openclaw-weixin -> Main Agent onboarding entry", match: { channel: "openclaw-weixin" } });
    }
    fs.writeFileSync(p, JSON.stringify(c, null, 2) + "\n");
  ' "$OPENCLAW_CONFIG_PATH"

  echo "  ℹ️  After Gateway starts, login with: openclaw channels login --channel openclaw-weixin"
  echo "  ℹ️  Then approve the sender with: openclaw pairing list openclaw-weixin && openclaw pairing approve openclaw-weixin <id>"
}

# ─── 2. 配置 git remote ────────────────────────────────────────
if [ ! -d "$PROJECT_ROOT/.git" ]; then
  echo "📦 Initializing git repository..."
  git init
  git remote add origin "$OFB_REPO"
  echo "  ✅ git initialized, remote set to $OFB_REPO"
else
  CURRENT_REMOTE="$(git remote get-url origin 2>/dev/null || echo "")"
  if [ -z "$CURRENT_REMOTE" ]; then
    git remote add origin "$OFB_REPO"
    echo "  ✅ Remote 'origin' added: $OFB_REPO"
  elif [ "$CURRENT_REMOTE" != "$OFB_REPO" ]; then
    echo "  ℹ️  Current remote: $CURRENT_REMOTE"
    echo "  ℹ️  Official wiseflow repo: $OFB_REPO"
    echo ""
    echo "  Remote is not the official wiseflow repo. Continue anyway? [y/N]"
    read -r reply
    case "$reply" in
      y|Y) echo "  Continuing with existing remote..." ;;
      *) echo "  Aborted."; exit 0 ;;
    esac
  fi
fi

# ─── 3. 拉取最新 wiseflow 代码 ────────────────────────────────────────
echo "📥 Fetching latest wiseflow code..."
if git fetch origin master; then
  COMMITS_BEHIND="$(git rev-list HEAD..origin/master --count 2>/dev/null || echo "?")"
  if [ "$COMMITS_BEHIND" = "0" ]; then
    echo "  ✅ wiseflow code is already up to date."
  elif [ "$COMMITS_BEHIND" = "?" ]; then
    echo "  ⚠️  Unable to compare with origin/master, continuing with local wiseflow code."
  else
    echo "  📊 $COMMITS_BEHIND new commit(s) available"
    if git reset --hard origin/master; then
      echo "  ✅ wiseflow code updated"
    else
      echo "  ⚠️  Failed to reset to origin/master, continuing with local wiseflow code."
    fi
  fi
else
  echo "  ⚠️  Failed to fetch latest wiseflow code from origin/master."
  echo "  ⚠️  Continuing with local wiseflow code."
fi
echo ""

# ─── 4. 按锚定版本更新 openclaw 引擎 ────────────────────────────
if [ ! -f "$VERSION_FILE" ]; then
  echo "❌ openclaw.version not found at $VERSION_FILE"
  exit 1
fi

# shellcheck source=../openclaw.version
. "$VERSION_FILE"

if [ -z "$OPENCLAW_COMMIT" ]; then
  echo "❌ OPENCLAW_COMMIT not set in openclaw.version"
  exit 1
fi

echo "🔍 openclaw target: $OPENCLAW_VERSION ($OPENCLAW_COMMIT)"

CURRENT_COMMIT="$(git -C "$OPENCLAW_DIR" rev-parse HEAD 2>/dev/null || echo "")"
if [ "$CURRENT_COMMIT" = "$OPENCLAW_COMMIT" ]; then
  echo "  ✅ openclaw is already at target commit."
  OPENCLAW_UPDATED=false
else
  echo "  Current commit: ${CURRENT_COMMIT:-"(unknown)"}"
  echo "  Checking out target commit..."
  git -C "$OPENCLAW_DIR" reset --hard HEAD 2>/dev/null || true
  if ! git -C "$OPENCLAW_DIR" cat-file -e "${OPENCLAW_COMMIT}^{tree}" 2>/dev/null; then
    echo "  📥 Fetching openclaw target commit..."
    git -C "$OPENCLAW_DIR" fetch origin --tags || \
      echo "  ⚠️  Failed to fetch openclaw tags from origin."
  fi
  if ! git -C "$OPENCLAW_DIR" cat-file -e "${OPENCLAW_COMMIT}^{tree}" 2>/dev/null; then
    echo "  ⚠️  Target commit not found locally; trying shallow-clone recovery..."
    git -C "$OPENCLAW_DIR" fetch --unshallow origin 2>/dev/null || \
      git -C "$OPENCLAW_DIR" fetch --deepen=200 origin || \
      echo "  ⚠️  Failed to deepen openclaw history from origin."
  fi
  if ! git -C "$OPENCLAW_DIR" cat-file -e "${OPENCLAW_COMMIT}^{tree}" 2>/dev/null; then
    echo "❌ Local openclaw commit (${CURRENT_COMMIT:-unknown}) does not match required openclaw.version ($OPENCLAW_COMMIT)."
    echo "   Network update failed or target commit is not available locally; aborting install."
    exit 1
  fi
  if ! git -C "$OPENCLAW_DIR" checkout "$OPENCLAW_COMMIT"; then
    echo "❌ Unable to checkout required openclaw commit from openclaw.version: $OPENCLAW_COMMIT"
    exit 1
  fi
  echo "  ✅ openclaw checked out at $OPENCLAW_VERSION"

  echo "  📦 Installing dependencies..."
  (cd "$OPENCLAW_DIR" && pnpm install)
  OPENCLAW_UPDATED=true
fi
echo ""

# ─── 5. 初始化配置文件 ───────────────────────────────────────────
# Crew workspace bootstrap 由步骤 6 apply-addons → setup-crew.sh 统一负责
# （含模板拷贝 + skill npm 依赖 + guide 注入）。此处不预先建 workspace，
# 否则 setup-crew.sh 会因目录已存在跳过 skill 依赖安装。
ensure_openclaw_config
echo ""

# ─── 6. 应用 addons（patches + skills + crew 模板）──────────────
# apply-addons 不 build、不 restart（由本脚本统一处理）
echo "🔄 Applying addons..."
ADDON_ARGS=(--no-build --no-restart)
[ "$FORCE" = "true" ] && ADDON_ARGS+=(--force)
[ "$SKIP_CREW" = "true" ] && ADDON_ARGS+=(--skip-crew)
"$PROJECT_ROOT/scripts/apply-addons.sh" "${ADDON_ARGS[@]}"
echo ""

# ─── 7. 编译 openclaw dist ──────────────────────────────────────
echo "🔨 Building openclaw..."
(cd "$OPENCLAW_DIR" && pnpm build)
echo "  ✅ Build complete"

echo "🎨 Building Control UI assets..."
(cd "$OPENCLAW_DIR" && pnpm ui:build)
echo "  ✅ UI build complete"
echo ""

# ─── 8. 环境变量收集 + daemon 安装 ─────────────────────────

# 需要询问用户的 API Key（若已在目标文件中存在则跳过）
# 5.5.3 起主力 + 视觉 + 替补统一走 AWK（火山方舟 Coding Plan），不再收集 SILICONFLOW_API_KEY
_USER_PROMPT_KEYS="AWK_API_KEY"

# 固定默认值（硬编码，不询问，已存在则跳过）
_HARDCODED_DEFAULTS="OPENCLAW_BROWSER_TIMEOUT_MS=90000 OPENCLAW_DISABLE_BONJOUR=true"

prompt_env_value() {
  local key="$1" default_value="$2" default_source="$3" value="" reuse="" skip_empty=""
  if [ -n "$default_value" ]; then
    read -r -p "Use existing ${default_source} value for ${key}? [Y/n] " reuse
    if [[ ! "$reuse" =~ ^[Nn]$ ]]; then printf "%s" "$default_value"; return 0; fi
  fi
  while true; do
    read -r -s -p "Enter value for ${key}: " value; echo ""
    value="${value//$'\r'/}"; value="${value//$'\n'/}"
    if [ -n "$value" ]; then printf "%s" "$value"; return 0; fi
    read -r -p "Value is empty, skip ${key}? [y/N] " skip_empty
    if [[ "$skip_empty" =~ ^[Yy]$ ]]; then printf ""; return 0; fi
  done
}

# 向 env 文件写入缺失的询问 key + 硬编码默认值
# $1: env 文件路径   $2: 格式 kv（KEY=VALUE）或 export（export KEY='value'）
_write_missing_env() {
  local env_file="$1" format="$2" _key="" _val="" _entry="" _sv="" _missing=""

  # 先扫描缺失的 key，如有则提前展示
  for _key in $_USER_PROMPT_KEYS; do
    if [ "$format" = "export" ]; then
      grep -qE "^export ${_key}=" "$env_file" 2>/dev/null && continue
    else
      grep -qE "^${_key}=" "$env_file" 2>/dev/null && continue
    fi
    _missing="${_missing}  ${_key}"
  done
  if [ -n "$_missing" ]; then
    echo "🔐 以下 API Key 未在 $(basename "$env_file") 中找到，需要输入："
    echo "$_missing"
    echo ""
  fi

  # 询问 key（已存在则跳过）
  for _key in $_USER_PROMPT_KEYS; do
    if [ "$format" = "export" ]; then
      grep -qE "^export ${_key}=" "$env_file" 2>/dev/null && continue
    else
      grep -qE "^${_key}=" "$env_file" 2>/dev/null && continue
    fi
    _sv="${!_key-}"
    if [ -t 0 ]; then
      _val="$(prompt_env_value "$_key" "${_sv:-}" "${_sv:+shell}")"
    else
      _val="${_sv:-}"
      [ -z "$_val" ] && echo "⚠️  Missing ${_key} in non-interactive mode; leaving it unset."
    fi
    # 清洗：去除所有空白字符。API key 是不透明 token，绝不含空白；
    # 防止粘贴/环境变量带入前导换行或空格导致 daemon.env 出现 `KEY=\nvalue` 错行。
    _val="$(printf '%s' "$_val" | tr -d '[:space:]')"
    if [ -n "$_val" ]; then
      if [ "$format" = "export" ]; then
        printf "export %s='%s'\n" "$_key" "${_val//\'/\'\\\'\'}" >> "$env_file"
      else
        printf "%s=%s\n" "$_key" "$_val" >> "$env_file"
      fi
    fi
  done

  # 硬编码默认值（已存在则跳过）
  for _entry in $_HARDCODED_DEFAULTS; do
    _key="${_entry%%=*}"
    _val="${_entry#*=}"
    if [ "$format" = "export" ]; then
      grep -qE "^export ${_key}=" "$env_file" 2>/dev/null && continue
      printf "export %s='%s'\n" "$_key" "$_val" >> "$env_file"
    else
      grep -qE "^${_key}=" "$env_file" 2>/dev/null && continue
      printf "%s=%s\n" "$_key" "$_val" >> "$env_file"
    fi
  done
}

# --- 8a. Linux: 写入 daemon.env（在 daemon install 之前）---
if [ "$(uname -s)" = "Linux" ]; then
  mkdir -p "$(dirname "$SYSTEMD_ENV_FILE")"
  [ -f "$SYSTEMD_ENV_FILE" ] || touch "$SYSTEMD_ENV_FILE"
  chmod 600 "$SYSTEMD_ENV_FILE"
  _write_missing_env "$SYSTEMD_ENV_FILE" kv

  # --- 注入 node 路径到 daemon.env ---
  _node_bin="$(command -v node 2>/dev/null || true)"
  if [ -n "$_node_bin" ]; then
    _node_dir="$(dirname "$_node_bin")"
    {
      grep -v "^PATH=" "$SYSTEMD_ENV_FILE" 2>/dev/null || true
      printf 'PATH=%s:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n' "$_node_dir"
    } > "${SYSTEMD_ENV_FILE}.new"
    mv "${SYSTEMD_ENV_FILE}.new" "$SYSTEMD_ENV_FILE"
    chmod 600 "$SYSTEMD_ENV_FILE"
  fi

  # --- WSL2 环境：注入 GUI 显示变量 ---
  if grep -qi microsoft /proc/version 2>/dev/null; then
    {
      grep -vE "^(DISPLAY|WAYLAND_DISPLAY|XDG_RUNTIME_DIR)=" "$SYSTEMD_ENV_FILE" 2>/dev/null || true
      printf 'DISPLAY=:0\nWAYLAND_DISPLAY=wayland-0\nXDG_RUNTIME_DIR=/mnt/wslg/runtime-dir\n'
    } > "${SYSTEMD_ENV_FILE}.new"
    mv "${SYSTEMD_ENV_FILE}.new" "$SYSTEMD_ENV_FILE"
    chmod 600 "$SYSTEMD_ENV_FILE"
  fi
fi

# ─── 8.5 Linux: 提前创建 systemd drop-in 引用 daemon.env ─────
# 必须在 daemon install 之前，否则 gateway 首次启动时读不到 API keys，
# 连续失败 5 次后触发 StartLimitBurst，后续 restart 也无效
if [ "$(uname -s)" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
  if systemctl --user show-environment >/dev/null 2>&1; then
    _SERVICE_NAME="openclaw-gateway"
    _user_systemd_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    _dropin_dir="${_user_systemd_dir}/${_SERVICE_NAME}.service.d"
    mkdir -p "$_dropin_dir"
    cat > "${_dropin_dir}/10-env-file.conf" <<EOF
[Service]
EnvironmentFile=-${SYSTEMD_ENV_FILE}
EOF
    # daemon-reload 在 daemon install 之后统一做一次
    echo "  ✅ systemd drop-in created (will reload after daemon install)"
  fi
fi

# ─── 9. 安装 / 升级 daemon ──────────────────────────────────
# 升级路径：daemon 已装则只 reload + restart，不 uninstall + install，
# 避免卸装瞬间掐断正在跑的 agent 会话（self-spawned subagent / channel reply）。
# 仅首次安装（service 文件不存在）才走完整 daemon install。
cd "$OPENCLAW_DIR"

_daemon_is_installed() {
  if [ "$(uname -s)" = "Darwin" ]; then
    [ -f "$HOME/Library/LaunchAgents/ai.openclaw.gateway.plist" ]
  elif [ "$(uname -s)" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
    systemctl --user list-unit-files 2>/dev/null | grep -q '^openclaw-gateway\.service'
  else
    return 1
  fi
}

if _daemon_is_installed; then
  echo "🔁 daemon already installed — reloading + restarting (no uninstall to preserve running sessions)"
  if [ "$(uname -s)" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload 2>/dev/null || true
  fi
  # 让 daemon 自升级 runtime（openclaw 引擎刚被重 build，需 daemon 重启后加载新 dist）
  pnpm openclaw daemon restart 2>/dev/null || true
else
  echo "📦 daemon first-time install"
  pnpm openclaw daemon install
  if [ "$(uname -s)" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload 2>/dev/null || true
  fi
fi

# ─── 9.4 让外部 CLI 解析 openclaw 时拿到本地构建 ──────────────
# node_modules/openclaw 原本是 npm 发布的自包（滞后版本，如 2026.5.28）：
# openclaw 根包是 pnpm workspace 的 self-package，channel 插件声明 dep "openclaw"
# 时 pnpm 不会把根链给自己，转而从 npm 拉已发布版进 node_modules/openclaw。
# 构建期已用完（pnpm build 在前），运行期 gateway 跑 dist/index.js 不 import 它。
# 此处将其指向本地根包，避免 weixin-cli 用 require.resolve('openclaw') spawn 旧版
# CLI、把 openclaw.json 的 meta.lastTouchedVersion 写成滞后版本。
NESTED_OC_VER_PRE="$(node -e 'try{console.log(require(process.argv[1]+"/package.json").version)}catch(e){}' "$OPENCLAW_DIR/node_modules/openclaw" 2>/dev/null || true)"
if [ -n "$NESTED_OC_VER_PRE" ] && [ "$NESTED_OC_VER_PRE" != "$OPENCLAW_VERSION" ]; then
  echo "  ℹ️  nested openclaw@$NESTED_OC_VER_PRE (published) lags local $OPENCLAW_VERSION — redirecting to local build"
fi
if [ -e "$OPENCLAW_DIR/node_modules/openclaw" ] && [ ! -L "$OPENCLAW_DIR/node_modules/openclaw" ]; then
  rm -rf "$OPENCLAW_DIR/node_modules/openclaw"
  ln -s "$OPENCLAW_DIR" "$OPENCLAW_DIR/node_modules/openclaw"
  echo "  🔗 redirected node_modules/openclaw -> local build ($OPENCLAW_VERSION)"
fi

# ─── 9.5 安装微信渠道插件（需要 openclaw CLI 已就绪）────────
install_weixin_channel

# weixin-cli 若仍绕过 symlink 写脏 meta，强制回正为本次安装版本（保险）
node -e '
  const fs=require("fs"),p=process.argv[1],v=process.argv[2];
  const c=JSON.parse(fs.readFileSync(p,"utf8"));
  c.meta=c.meta||{}; c.meta.lastTouchedVersion=v; c.meta.lastTouchedAt=new Date().toISOString();
  fs.writeFileSync(p,JSON.stringify(c,null,2)+"\n");
' "$OPENCLAW_CONFIG_PATH" "$OPENCLAW_VERSION"
echo ""

# ─── 10. 平台特定的 post-install ─────────────────────────
if [ "$(uname -s)" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
  # drop-in 已在 8.5 创建，此处只需 reset + restart
  if systemctl --user show-environment >/dev/null 2>&1; then
    systemctl --user reset-failed "openclaw-gateway.service" 2>/dev/null || true
    systemctl --user restart "openclaw-gateway.service"
    echo "✅ Restarted gateway with daemon.env"
  fi
elif [ "$(uname -s)" = "Darwin" ]; then
  # --- 追加 env 到 launchd gateway.env（在 daemon install 之后）---
  if [ -f "$MACOS_GATEWAY_ENV" ]; then
    _write_missing_env "$MACOS_GATEWAY_ENV" export
    chmod 600 "$MACOS_GATEWAY_ENV"

    # 重启 gateway 使新环境变量生效
    cd "$OPENCLAW_DIR"
    pnpm openclaw gateway restart 2>/dev/null || true
  else
    echo "⚠️  macOS gateway env file not found at $MACOS_GATEWAY_ENV"
    echo "   Skipping env injection. Ensure gateway is installed: openclaw daemon install"
  fi
fi

echo ""
echo "✅ Installation complete!"
echo "   Access: http://127.0.0.1:18789"
