#!/bin/bash
# install.sh - wiseflow 一键首装脚本（预构建 tarball 路线）
#
# 用法：
#   curl -fsSL https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.sh | bash
#
# 与 update.sh 区别：
#   - install.sh = 首装路线（拉预构建 tarball → pnpm install --prod → onboard，全程无需用户预装 Node/git/pnpm）
#   - update.sh  = 已装用户的升级路线（拉新 tarball → pnpm install --prod → daemon reload）
#
# 执行流程：
#   1. 检测 OS + arch → 选 tarball asset（linux-x64 / mac-arm64 / mac-x64 / win-x64）
#   2. bootstrap gum UI（TTY 才有，非 TTY 静默跳过）
#   3. 解析最新 release tag（GitHub API，或 XIAOBEI_MIRROR env 指向自建镜像）
#   4. 下载 xiaobei-{ver}-{plat}.tar.zst → 临时文件
#   5. 解压到 WISEFLOW_ROOT（默认 ~/.openclaw）：openclaw/ + tools/node + tools/pnpm + bin/openclaw + crews/ + skills/ + scripts/ + camoufox-cli/
#   6. pnpm install --prod --frozen-lockfile（用 ship 的 portable node + pnpm，在 openclaw/ 下；只拉依赖不编译，无 OOM，native 自动按平台）
#   7. pip install --user（skills 的 python deps，扫 requirements.txt）
#   8. 放置 config-templates/openclaw.json → ~/.openclaw/openclaw.json + 预填微信 channel binding
#   9. setup-crew.sh（裸跑，无 --force；--force 只用户手动修复用）
#   10. camoufox-cli：npm install -g 本地 fork（ship 的 portable node）+ camoufox-cli install 下 Firefox
#   11. openclaw onboard --skip-channels --skip-skills --skip-bootstrap --skip-health --skip-ui --install-daemon
#       此步交互问用户：模型供应商 + API key（唯一人工输入点）
#   12. 打印访问指引
#
# tarball 由 .github/workflows/build-dist.yml 在 CI 预构建（方案 B）：CI 只 build 一次，
# ship dist+lockfile（不 ship node_modules）+ pnpm + portable Node，用户侧 pnpm install --prod 重建 node_modules。
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════
WISEFLOW_REPO="${XIAOBEI_REPO:-TeamWiseFlow/xiaobei}"
WISEFLOW_ROOT_DEFAULT="$HOME/.openclaw"
# XIAOBEI_MIRROR 可指向自建镜像站根（国内加速），形如 https://mirror.example.com/xiaobei
# 资产 URL 构造为 $XIAOBEI_MIRROR/releases/download/{tag}/xiaobei-{ver}-{plat}.tar.zst
XIAOBEI_MIRROR="${XIAOBEI_MIRROR:-}"
# tarball 内 ship 的 portable Node / pnpm 入口（相对 WISEFLOW_ROOT）
PORTABLE_NODE="tools/node/bin/node"
PORTABLE_PNPM="tools/pnpm/bin/pnpm.mjs"

# ═══════════════════════════════════════════════════════════════════
# 色彩 / UI（fork 自上游 install.sh）
# ═══════════════════════════════════════════════════════════════════
BOLD='\033[1m'
ACCENT='\033[38;2;255;77;77m'
INFO='\033[38;2;136;146;176m'
SUCCESS='\033[38;2;0;229;204m'
WARN='\033[38;2;255;176;32m'
ERROR='\033[38;2;230;57;70m'
MUTED='\033[38;2;90;100;128m'
NC='\033[0m'

DEFAULT_TAGLINE="All your chats, one wiseflow."

ORIGINAL_PATH="${PATH:-}"

TMPFILES=()
cleanup_tmpfiles() {
    local f
    for f in "${TMPFILES[@]:-}"; do
        rm -rf "$f" 2>/dev/null || true
    done
}
trap cleanup_tmpfiles EXIT

mktempfile() {
    local f
    f="$(mktemp)"
    TMPFILES+=("$f")
    echo "$f"
}

# ═══════════════════════════════════════════════════════════════════
# gum UI（TTY 才 bootstrap，非 TTY 静默跳过）
# ═══════════════════════════════════════════════════════════════════
GUM_VERSION="${OPENCLAW_GUM_VERSION:-0.17.0}"
GUM=""
GUM_STATUS="skipped"
GUM_REASON=""

is_non_interactive_shell() {
    if [[ "${NO_PROMPT:-0}" == "1" ]]; then
        return 0
    fi
    if [[ ! -t 0 || ! -t 1 ]]; then
        return 0
    fi
    return 1
}

has_controlling_tty() {
    if [[ ! -r /dev/tty || ! -w /dev/tty ]]; then
        return 1
    fi
    if ! { : </dev/tty; } 2>/dev/null; then
        return 1
    fi
    return 0
}

gum_is_tty() {
    if [[ -n "${NO_COLOR:-}" ]]; then
        return 1
    fi
    if [[ "${TERM:-dumb}" == "dumb" ]]; then
        return 1
    fi
    if [[ -t 2 || -t 1 ]]; then
        return 0
    fi
    if has_controlling_tty; then
        return 0
    fi
    return 1
}

gum_detect_os() {
    case "$(uname -s 2>/dev/null || true)" in
        Darwin) echo "Darwin" ;;
        Linux) echo "Linux" ;;
        *) echo "unsupported" ;;
    esac
}

gum_detect_arch() {
    case "$(uname -m 2>/dev/null || true)" in
        x86_64|amd64) echo "x86_64" ;;
        arm64|aarch64) echo "arm64" ;;
        i386|i686) echo "i386" ;;
        armv7l|armv7) echo "armv7" ;;
        armv6l|armv6) echo "armv6" ;;
        *) echo "unknown" ;;
    esac
}

verify_sha256sum_file() {
    local checksums="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum --ignore-missing -C "$checksums" >/dev/null 2>&1
        return $?
    fi
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 --ignore-missing -C "$checksums" >/dev/null 2>&1
        return $?
    fi
    return 1
}

bootstrap_gum_temp() {
    GUM=""
    GUM_STATUS="skipped"
    GUM_REASON=""

    if is_non_interactive_shell; then
        GUM_REASON="non-interactive shell (auto-disabled)"
        return 1
    fi

    if ! gum_is_tty; then
        GUM_REASON="terminal does not support gum UI"
        return 1
    fi

    if command -v gum >/dev/null 2>&1; then
        GUM="gum"
        GUM_STATUS="found"
        GUM_REASON="already installed"
        return 0
    fi

    if ! command -v tar >/dev/null 2>&1; then
        GUM_REASON="tar not found"
        return 1
    fi

    local os arch asset base gum_tmpdir gum_path
    os="$(gum_detect_os)"
    arch="$(gum_detect_arch)"
    if [[ "$os" == "unsupported" || "$arch" == "unknown" ]]; then
        GUM_REASON="unsupported os/arch ($os/$arch)"
        return 1
    fi

    asset="gum_${GUM_VERSION}_${os}_${arch}.tar.gz"
    base="https://github.com/charmbracelet/gum/releases/download/v${GUM_VERSION}"

    gum_tmpdir="$(mktemp -d)"
    TMPFILES+=("$gum_tmpdir")

    ui_info "Preparing spinner support"
    if ! download_file "${base}/${asset}" "$gum_tmpdir/$asset"; then
        GUM_REASON="download failed"
        return 1
    fi

    ui_info "Verifying spinner support download"
    if ! download_file "${base}/checksums.txt" "$gum_tmpdir/checksums.txt"; then
        GUM_REASON="checksum unavailable or failed"
        return 1
    fi

    if ! (cd "$gum_tmpdir" && verify_sha256sum_file "checksums.txt"); then
        GUM_REASON="checksum unavailable or failed"
        return 1
    fi

    if ! tar -xzf "$gum_tmpdir/$asset" -C "$gum_tmpdir" >/dev/null 2>&1; then
        GUM_REASON="extract failed"
        return 1
    fi

    gum_path="$(find "$gum_tmpdir" -type f -name gum 2>/dev/null | head -n1 || true)"
    if [[ -z "$gum_path" ]]; then
        GUM_REASON="gum binary missing after extract"
        return 1
    fi

    chmod +x "$gum_path" >/dev/null 2>&1 || true
    if [[ ! -x "$gum_path" ]]; then
        GUM_REASON="gum binary is not executable"
        return 1
    fi

    GUM="$gum_path"
    GUM_STATUS="installed"
    GUM_REASON="temp, verified"
    return 0
}

print_gum_status() {
    case "$GUM_STATUS" in
        found)
            ui_success "gum available (${GUM_REASON})"
            ;;
        installed)
            ui_success "gum bootstrapped (${GUM_REASON}, v${GUM_VERSION})"
            ;;
        *)
            if [[ -n "$GUM_REASON" && "$GUM_REASON" != "non-interactive shell (auto-disabled)" ]]; then
                ui_info "gum skipped (${GUM_REASON})"
            fi
            ;;
    esac
}

print_installer_banner() {
    if [[ -n "$GUM" ]]; then
        local title tagline hint card
        title="$("$GUM" style --foreground "#ff4d4d" --bold "🦞 wiseflow Installer")"
        tagline="$("$GUM" style --foreground "#8892b0" "$TAGLINE")"
        hint="$("$GUM" style --foreground "#5a6480" "modern installer mode")"
        card="$(printf '%s\n%s\n%s' "$title" "$tagline" "$hint")"
        "$GUM" style --border rounded --border-foreground "#ff4d4d" --padding "1 2" "$card"
        echo ""
        return
    fi

    echo -e "${ACCENT}${BOLD}"
    echo "  🦞 wiseflow Installer"
    echo -e "${NC}${INFO}  ${TAGLINE}${NC}"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════
# OS / downloader
# ═══════════════════════════════════════════════════════════════════
detect_os_or_die() {
    OS="unknown"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    elif [[ "$OSTYPE" == "linux"* ]] || [[ -n "${WSL_DISTRO_NAME:-}" ]]; then
        OS="linux"
    fi

    if [[ "$OS" == "unknown" ]]; then
        ui_error "Unsupported operating system"
        echo "This installer supports macOS and Linux (including WSL)."
        exit 1
    fi

    ui_success "Detected: $OS"
}

DOWNLOADER=""
detect_downloader() {
    if command -v curl &> /dev/null; then
        DOWNLOADER="curl"
        return 0
    fi
    if command -v wget &> /dev/null; then
        DOWNLOADER="wget"
        return 0
    fi
    ui_error "Missing downloader (curl or wget required)"
    exit 1
}

download_file() {
    local url="$1"
    local output="$2"
    if [[ -z "$DOWNLOADER" ]]; then
        detect_downloader
    fi
    if [[ "$DOWNLOADER" == "curl" ]]; then
        curl -fsSL --proto '=https' --tlsv1.2 --retry 3 --retry-delay 1 --retry-connrefused -o "$output" "$url"
        return
    fi
    wget -q --https-only --secure-protocol=TLSv1_2 --tries=3 --timeout=20 -O "$output" "$url"
}

# ═══════════════════════════════════════════════════════════════════
# 平台 → tarball asset 名
# ═══════════════════════════════════════════════════════════════════
detect_platform_asset() {
    local arch=""
    case "$(uname -m)" in
        x86_64|amd64) arch="x64" ;;
        arm64|aarch64) arch="arm64" ;;
        *) ui_error "Unsupported arch: $(uname -m)"; exit 1 ;;
    esac
    if [[ "$OS" == "macos" ]]; then
        PLAT="mac-$arch"
    elif [[ "$OS" == "linux" ]]; then
        [[ "$arch" == "arm64" ]] && { ui_error "linux-arm64 tarball 暂未构建，仅 linux-x64"; exit 1; }
        PLAT="linux-$arch"
    fi
    ui_success "Platform asset: $PLAT"
}

# 解析最新 release tag + 版本号（GitHub API，失败回退 gh CLI）
resolve_latest_version() {
    if [[ -n "${XIAOBEI_TAG:-}" ]]; then
        XIAOBEI_VER="${XIAOBEI_TAG#v}"
        ui_success "Using pinned tag: $XIAOBEI_TAG"
        return 0
    fi
    local api="https://api.github.com/repos/$WISEFLOW_REPO/releases/latest"
    local resp
    resp="$(curl -fsSL "$api" 2>/dev/null || true)"
    XIAOBEI_TAG="$(printf '%s' "$resp" | grep -oE '"tag_name"[[:space:]]*:[[:space:]]*"v[^"]+"' | head -1 | sed -E 's/.*"v([^"]+)".*/v\1/')"
    if [[ -z "$XIAOBEI_TAG" ]]; then
        # 回退 gh CLI
        XIAOBEI_TAG="$(gh release view -R "$WISEFLOW_REPO" --json tagName -q .tagName 2>/dev/null || true)"
    fi
    if [[ -z "$XIAOBEI_TAG" ]]; then
        ui_error "无法解析最新 release tag（GitHub API + gh CLI 都失败）"
        echo "指定版本：export XIAOBEI_TAG=v5.5.0 后重跑"
        exit 1
    fi
    XIAOBEI_VER="${XIAOBEI_TAG#v}"
    ui_success "Latest release: $XIAOBEI_TAG"
}

# 构造 tarball 下载 URL（XIAOBEI_MIRROR 优先）
tarball_url() {
    local asset="xiaobei-${XIAOBEI_TAG}-${PLAT}.tar.zst"
    if [[ -n "$XIAOBEI_MIRROR" ]]; then
        echo "$XIAOBEI_MIRROR/releases/download/$XIAOBEI_TAG/$asset"
    else
        echo "https://github.com/$WISEFLOW_REPO/releases/download/$XIAOBEI_TAG/$asset"
    fi
}

download_and_extract_tarball() {
    local url; url="$(tarball_url)"
    local asset="xiaobei-${XIAOBEI_TAG}-${PLAT}.tar.zst"
    ui_kv "Asset" "$asset"
    ui_kv "URL" "$url"
    local tmp; tmp="$(mktempfile)"
    ui_info "Downloading $asset (~120MB)..."
    download_file "$url" "$tmp"
    ui_success "Downloaded"

    mkdir -p "$WISEFLOW_ROOT"
    ui_info "Extracting to $WISEFLOW_ROOT ..."
    tar --zstd -xf "$tmp" -C "$WISEFLOW_ROOT"
    ui_success "Extracted"

    # 校验关键入口
    [[ -x "$WISEFLOW_ROOT/$PORTABLE_NODE" ]] || { ui_error "portable node 缺失：$WISEFLOW_ROOT/$PORTABLE_NODE"; exit 1; }
    [[ -f "$WISEFLOW_ROOT/$PORTABLE_PNPM" ]] || { ui_error "bundled pnpm 缺失：$WISEFLOW_ROOT/$PORTABLE_PNPM"; exit 1; }
    [[ -f "$WISEFLOW_ROOT/openclaw/openclaw.mjs" ]] || { ui_error "openclaw.mjs 缺失"; exit 1; }
}

# 用户侧装依赖：pnpm install --prod --frozen-lockfile（只拉依赖不编译，无 OOM）
pnpm_install_prod() {
    local openclaw_dir="$WISEFLOW_ROOT/openclaw"
    local node="$WISEFLOW_ROOT/$PORTABLE_NODE"
    local pnpm="$WISEFLOW_ROOT/$PORTABLE_PNPM"
    ui_info "pnpm install --prod --frozen-lockfile（拉依赖 + native prebuilt，~30s-2min）"
    run_required_step "pnpm install --prod" \
        env NODE_OPTIONS="--max-old-space-size=4096" \
        "$node" "$pnpm" -C "$openclaw_dir" install --prod --frozen-lockfile \
        --registry=https://registry.npmmirror.com --fetch-retries=5 --fetch-timeout=600000 --network-concurrency=8
    ui_success "Dependencies installed"
}

# skills 的 python 依赖（扫仓内 requirements.txt，pip install --user）
install_python_deps() {
    local root="$WISEFLOW_ROOT"
    local merged=""
    local f
    while IFS= read -r -d '' f; do
        merged+="$(cat "$f" 2>/dev/null)"$'\n'
    done < <(find "$root/skills" "$root/crews" "$root" -maxdepth 4 -name requirements.txt -print0 2>/dev/null)
    [[ -z "$merged" ]] && { ui_info "No requirements.txt found; skip python deps"; return 0; }
    local PIP_CMD=""
    if command -v pip &>/dev/null; then PIP_CMD="pip"
    elif command -v pip3 &>/dev/null; then PIP_CMD="pip3"
    elif python3 -m pip --version &>/dev/null; then PIP_CMD="python3 -m pip"; fi
    if [[ -z "$PIP_CMD" ]]; then
        ui_warn "pip 未安装，跳过 python 依赖（skills 用到时再装）"
        return 0
    fi
    ui_info "Installing python skill deps (--user)"
    printf '%s' "$merged" | sort -u | grep -vE '^\s*#|^\s*$' | \
        "$PIP_CMD" install --user -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r /dev/stdin || \
        ui_warn "pip install 部分失败，可稍后手动补"
    ui_success "Python deps done"
}

run_remote_bash() {
    local url="$1"
    local tmp
    tmp="$(mktempfile)"
    download_file "$url" "$tmp"
    /bin/bash "$tmp"
}

# ═══════════════════════════════════════════════════════════════════
# UI helpers
# ═══════════════════════════════════════════════════════════════════
ui_info() {
    local msg="$*"
    if [[ -n "$GUM" ]]; then
        "$GUM" log --level info "$msg"
    else
        echo -e "${MUTED}·${NC} ${msg}"
    fi
}

ui_warn() {
    local msg="$*"
    if [[ -n "$GUM" ]]; then
        "$GUM" log --level warn "$msg"
    else
        echo -e "${WARN}!${NC} ${msg}"
    fi
}

ui_success() {
    local msg="$*"
    if [[ -n "$GUM" ]]; then
        local mark
        mark="$("$GUM" style --foreground "#00e5cc" --bold "✓")"
        echo "${mark} ${msg}"
    else
        echo -e "${SUCCESS}✓${NC} ${msg}"
    fi
}

ui_error() {
    local msg="$*"
    if [[ -n "$GUM" ]]; then
        "$GUM" log --level error "$msg"
    else
        echo -e "${ERROR}✗${NC} ${msg}"
    fi
}

INSTALL_STAGE_TOTAL=7
INSTALL_STAGE_CURRENT=0

ui_section() {
    local title="$1"
    if [[ -n "$GUM" ]]; then
        "$GUM" style --bold --foreground "#ff4d4d" --padding "1 0" "$title"
    else
        echo ""
        echo -e "${ACCENT}${BOLD}${title}${NC}"
    fi
}

ui_stage() {
    local title="$1"
    INSTALL_STAGE_CURRENT=$((INSTALL_STAGE_CURRENT + 1))
    ui_section "[${INSTALL_STAGE_CURRENT}/${INSTALL_STAGE_TOTAL}] ${title}"
}

ui_kv() {
    local key="$1"
    local value="$2"
    if [[ -n "$GUM" ]]; then
        local key_part value_part
        key_part="$("$GUM" style --foreground "#5a6480" --width 20 "$key")"
        value_part="$("$GUM" style --bold "$value")"
        "$GUM" join --horizontal "$key_part" "$value_part"
    else
        echo -e "${MUTED}${key}:${NC} ${value}"
    fi
}

ui_celebrate() {
    local msg="$1"
    if [[ -n "$GUM" ]]; then
        "$GUM" style --bold --foreground "#00e5cc" "$msg"
    else
        echo -e "${SUCCESS}${BOLD}${msg}${NC}"
    fi
}

is_shell_function() {
    local name="${1:-}"
    [[ -n "$name" ]] && declare -F "$name" >/dev/null 2>&1
}

is_gum_raw_mode_failure() {
    local err_log="$1"
    [[ -s "$err_log" ]] || return 1
    grep -Eiq 'setrawmode|inappropriate ioctl' "$err_log"
}

run_with_spinner() {
    local title="$1"
    shift

    if [[ -n "$GUM" ]] && gum_is_tty && ! is_shell_function "${1:-}"; then
        local gum_err gum_out
        gum_err="$(mktempfile)"
        gum_out="$(mktempfile)"
        if "$GUM" spin --spinner dot --title "$title" -- "$@" >"$gum_out" 2>"$gum_err"; then
            if is_gum_raw_mode_failure "$gum_out" || is_gum_raw_mode_failure "$gum_err"; then
                GUM=""
                GUM_STATUS="skipped"
                GUM_REASON="gum raw mode unavailable"
                ui_warn "Spinner unavailable in this terminal; continuing without spinner"
                "$@"
                return $?
            fi
            if [[ -s "$gum_out" ]]; then
                cat "$gum_out"
            fi
            return 0
        fi
        local gum_status=$?
        if is_gum_raw_mode_failure "$gum_err" || is_gum_raw_mode_failure "$gum_out"; then
            GUM=""
            GUM_STATUS="skipped"
            GUM_REASON="gum raw mode unavailable"
            ui_warn "Spinner unavailable in this terminal; continuing without spinner"
            "$@"
            return $?
        fi
        if [[ -s "$gum_err" ]]; then
            cat "$gum_err" >&2
        fi
        return "$gum_status"
    fi

    "$@"
}

run_quiet_step() {
    local title="$1"
    shift

    if [[ "$VERBOSE" == "1" ]]; then
        run_with_spinner "$title" "$@"
        return $?
    fi

    local log
    log="$(mktempfile)"
    local showed_progress=false

    if [[ -n "$GUM" ]] && gum_is_tty && ! is_shell_function "${1:-}"; then
        local cmd_quoted=""
        local log_quoted=""
        printf -v cmd_quoted '%q ' "$@"
        printf -v log_quoted '%q' "$log"
        if run_with_spinner "$title" bash -c "${cmd_quoted}>${log_quoted} 2>&1"; then
            return 0
        fi
        showed_progress=true
    else
        ui_info "${title}"
        showed_progress=true
        if "$@" >"$log" 2>&1; then
            return 0
        fi
    fi

    if [[ "$showed_progress" == "false" ]]; then
        ui_info "${title}"
    fi

    ui_error "${title} failed — re-run with --verbose for details"
    if [[ -s "$log" ]]; then
        tail -n 80 "$log" >&2 || true
    fi
    return 1
}

run_required_step() {
    local title="$1"
    shift
    if run_quiet_step "$title" "$@"; then
        return 0
    fi
    exit 1
}

refresh_shell_command_cache() {
    hash -r 2>/dev/null || true
}

is_promptable() {
    if [[ "$NO_PROMPT" == "1" ]]; then
        return 1
    fi
    if has_controlling_tty; then
        return 0
    fi
    return 1
}

is_root() {
    [[ "$(id -u 2>/dev/null || echo 1)" -eq 0 ]]
}

require_sudo() {
    if is_root; then
        return 0
    fi
    if ! command -v sudo >/dev/null 2>&1; then
        ui_error "sudo required but not available"
        exit 1
    fi
}

# ═══════════════════════════════════════════════════════════════════
# Homebrew（mac 才用）
# ═══════════════════════════════════════════════════════════════════
is_macos_admin_user() {
    local groups
    groups="$(id -Gn 2>/dev/null || true)"
    if [[ "$groups" == *"admin"* ]]; then
        return 0
    fi
    return 1
}

print_homebrew_admin_fix() {
    ui_error "Homebrew install requires an admin user"
    echo "Add your user to the 'admin' group or run as admin: sudo dscl . -append /Users/$(id -un) GroupMembership admin"
}

install_homebrew() {
    if [[ "$OS" == "macos" ]]; then
        if ! command -v brew &> /dev/null; then
            if ! is_macos_admin_user; then
                print_homebrew_admin_fix
                exit 1
            fi
            ui_info "Homebrew not found, installing"
            run_quiet_step "Installing Homebrew" run_remote_bash "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"

            # Add Homebrew to PATH for this session
            if [[ -f "/opt/homebrew/bin/brew" ]]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [[ -f "/usr/local/bin/brew" ]]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
            ui_success "Homebrew installed"
        else
            ui_success "Homebrew already installed"
        fi
    fi
}

# ═══════════════════════════════════════════════════════════════════
# Node.js
# ═══════════════════════════════════════════════════════════════════
parse_node_version_components_for_binary() {
    local node_bin="${1:-node}"
    if ! command -v "$node_bin" &> /dev/null && [[ ! -x "$node_bin" ]]; then
        return 1
    fi
    local version major minor
    version="$("$node_bin" -v 2>/dev/null || true)"
    major="${version#v}"
    major="${major%%.*}"
    minor="${version#v}"
    minor="${minor#*.}"
    minor="${minor%%.*}"

    if [[ ! "$major" =~ ^[0-9]+$ ]]; then
        return 1
    fi
    if [[ ! "$minor" =~ ^[0-9]+$ ]]; then
        return 1
    fi
    echo "${major} ${minor}"
    return 0
}

parse_node_version_components() {
    if ! command -v node &> /dev/null; then
        return 1
    fi
    parse_node_version_components_for_binary node
}

node_major_version() {
    local version_components major minor
    version_components="$(parse_node_version_components || true)"
    read -r major minor <<< "$version_components"
    if [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ ]]; then
        echo "$major"
        return 0
    fi
    return 1
}

node_is_at_least_required() {
    local version_components major minor
    version_components="$(parse_node_version_components || true)"
    read -r major minor <<< "$version_components"
    if [[ ! "$major" =~ ^[0-9]+$ || ! "$minor" =~ ^[0-9]+$ ]]; then
        return 1
    fi
    if [[ "$major" -gt "$NODE_MIN_MAJOR" ]]; then
        return 0
    fi
    if [[ "$major" -eq "$NODE_MIN_MAJOR" && "$minor" -ge "$NODE_MIN_MINOR" ]]; then
        return 0
    fi
    return 1
}

prepend_path_dir() {
    local dir="${1%/}"
    if [[ -z "$dir" || ! -d "$dir" ]]; then
        return 1
    fi
    local current=":${PATH:-}:"
    current="${current//:${dir}:/:}"
    current="${current#:}"
    current="${current%:}"
    if [[ -n "$current" ]]; then
        export PATH="${dir}:${current}"
    else
        export PATH="${dir}"
    fi
    refresh_shell_command_cache
}

check_node() {
    if command -v node &> /dev/null; then
        NODE_VERSION="$(node_major_version || true)"
        if node_is_at_least_required; then
            ui_success "Node.js v$(node -v | cut -d'v' -f2) found"
            return 0
        else
            if [[ -n "$NODE_VERSION" ]]; then
                ui_info "Node.js $(node -v) found, upgrading to v${NODE_MIN_VERSION}+"
            else
                ui_info "Node.js found but version could not be parsed; reinstalling v${NODE_MIN_VERSION}+"
            fi
            return 1
        fi
    else
        ui_info "Node.js not found, installing it now"
        return 1
    fi
}

install_node() {
    if [[ "$OS" == "macos" ]]; then
        ui_info "Installing Node.js via Homebrew"
        if ! run_quiet_step "Installing node@${NODE_DEFAULT_MAJOR}" brew install "node@${NODE_DEFAULT_MAJOR}"; then
            echo "Re-run with --verbose or run 'brew install node@${NODE_DEFAULT_MAJOR}' directly, then rerun the installer."
            exit 1
        fi
        brew link "node@${NODE_DEFAULT_MAJOR}" --overwrite --force 2>/dev/null || true
        ui_success "Node.js installed"
    elif [[ "$OS" == "linux" ]]; then
        require_sudo
        ui_info "Installing Node.js on Linux"
        # 走 NodeSource 官方安装脚本（稳定跨发行版）
        if ! run_quiet_step "Installing Node.js ${NODE_DEFAULT_MAJOR}.x via NodeSource" \
            run_remote_bash "https://deb.nodesource.com/setup_${NODE_DEFAULT_MAJOR}.x"; then
            ui_error "NodeSource setup script failed"
            exit 1
        fi
        if command -v apt-get &> /dev/null; then
            run_required_step "Installing nodejs" apt-get install -y nodejs
        elif command -v dnf &> /dev/null; then
            run_required_step "Installing nodejs" dnf install -y nodejs
        elif command -v yum &> /dev/null; then
            run_required_step "Installing nodejs" yum install -y nodejs
        else
            ui_error "Unsupported Linux distribution for Node.js auto-install"
            echo "Install Node.js ${NODE_DEFAULT_MAJOR} manually then rerun."
            exit 1
        fi
        ui_success "Node.js installed"
    else
        ui_error "Unsupported OS for Node.js install: $OS"
        exit 1
    fi

    if ! node_is_at_least_required; then
        local active_path active_version
        active_path="$(command -v node 2>/dev/null || echo "not found")"
        active_version="$(node -v 2>/dev/null || echo "missing")"
        ui_error "Installed Node.js must be v${NODE_MIN_VERSION}+ but this shell is using ${active_version} (${active_path})"
        exit 1
    fi
    ui_success "Node.js v$(node -v | cut -d'v' -f2) ready"
}

# ═══════════════════════════════════════════════════════════════════
# Git
# ═══════════════════════════════════════════════════════════════════
check_git() {
    if command -v git &> /dev/null; then
        ui_success "Git already installed"
        return 0
    fi
    return 1
}

install_git() {
    if [[ "$OS" == "macos" ]]; then
        install_homebrew
        run_quiet_step "Installing Git" brew install git
    elif [[ "$OS" == "linux" ]]; then
        require_sudo
        if command -v apt-get &> /dev/null; then
            run_required_step "Installing git" apt-get install -y git
        elif command -v dnf &> /dev/null; then
            run_required_step "Installing git" dnf install -y git
        elif command -v yum &> /dev/null; then
            run_required_step "Installing git" yum install -y git
        elif command -v apk &> /dev/null; then
            run_required_step "Installing git" apk add --no-cache git
        else
            ui_error "Unsupported Linux distribution for git auto-install"
            exit 1
        fi
    fi
    ui_success "Git installed"
}

# ═══════════════════════════════════════════════════════════════════
# pnpm
# ═══════════════════════════════════════════════════════════════════
install_pnpm() {
    if command -v pnpm >/dev/null 2>&1; then
        ui_success "pnpm already installed ($(pnpm --version 2>/dev/null || echo unknown))"
        return 0
    fi
    ui_info "Installing pnpm@${PNPM_VERSION} globally"
    # 用 corepack 路线（与 openclaw 仓 packageManager 对齐，最稳）
    if command -v corepack >/dev/null 2>&1; then
        run_required_step "Enabling corepack" corepack enable
        run_required_step "Preparing pnpm@${PNPM_VERSION}" corepack prepare "pnpm@${PNPM_VERSION}" --activate
    else
        # corepack 不可用回退 npm 全局装（走阿里云镜像，国内用户裸跑 npm registry 慢得离谱）
        run_required_step "Installing pnpm via npm" npm install -g "pnpm@${PNPM_VERSION}" --registry=https://registry.npmmirror.com
    fi
    if ! command -v pnpm >/dev/null 2>&1; then
        ui_error "pnpm install failed"
        exit 1
    fi
    ui_success "pnpm ready ($(pnpm --version))"
}

# ═══════════════════════════════════════════════════════════════════
# wiseflow clone + checkout openclaw
# ═══════════════════════════════════════════════════════════════════
# 三个分支：
#   1. --use-local + WISEFLOW_ROOT 已是 wiseflow 仓 → 直接复用，跳 clone/fetch（保本地改动）
#   2. WISEFLOW_ROOT 已是 wiseflow 仓但未开 --use-local → fetch + reset --hard origin/master（覆盖本地改动）
#   3. WISEFLOW_ROOT 不存在 → git clone
clone_wiseflow() {
    local target="$WISEFLOW_ROOT"

    # 分支 1：本地复用
    if [[ "$USE_LOCAL" == "true" && -d "$target/.git" ]]; then
        ui_success "Using local wiseflow checkout at $target (--use-local, skipping clone/fetch)"
        # 验下基本结构，免得跑下去 apply-addons 段才炸
        if [[ ! -f "$target/scripts/apply-addons.sh" || ! -d "$target/openclaw" ]]; then
            ui_error "$target is a git checkout but missing scripts/apply-addons.sh or openclaw/ subdir"
            exit 1
        fi
        return 0
    fi

    # 分支 2：已是仓但没开 --use-local，fetch + reset 走升级路线
    if [[ -d "$target/.git" ]]; then
        ui_warn "wiseflow already cloned at $target"
        if [[ "$USE_LOCAL" != "true" ]]; then
            ui_warn "Fetching + resetting to origin/master — THIS WILL DISCARD LOCAL CHANGES"
            ui_warn "Pass --use-local to preserve local working tree"
            run_quiet_step "Fetching latest wiseflow" git -C "$target" fetch origin master
            run_required_step "Resetting to origin/master" git -C "$target" reset --hard origin/master
        fi
        return 0
    fi

    # 分支 3：全新 clone
    if [[ -d "$target" ]]; then
        ui_error "$target exists but is not a git checkout; refusing to overwrite"
        echo "Move or remove it, then rerun."
        exit 1
    fi
    run_required_step "Cloning wiseflow repo" git clone "$WISEFLOW_REPO" "$target"
    ui_success "wiseflow cloned to $target"
}

checkout_openclaw_at_pin() {
    local target="$WISEFLOW_ROOT"
    local version_file="$target/openclaw.version"
    local openclaw_dir="$target/openclaw"

    if [[ ! -f "$version_file" ]]; then
        ui_error "openclaw.version missing in cloned wiseflow repo"
        exit 1
    fi

    # shellcheck source=/dev/null
    source "$version_file"
    if [[ -z "$OPENCLAW_COMMIT" ]]; then
        ui_error "OPENCLAW_COMMIT not set in openclaw.version"
        exit 1
    fi

    ui_info "openclaw target: ${OPENCLAW_VERSION:-unknown} (${OPENCLAW_COMMIT})"

    if [[ ! -d "$openclaw_dir/.git" ]]; then
        run_required_step "Cloning openclaw upstream" git clone https://github.com/openclaw/openclaw.git "$openclaw_dir"
    fi

    local current_commit
    current_commit="$(git -C "$openclaw_dir" rev-parse HEAD 2>/dev/null || echo "")"
    if [[ "$current_commit" = "$OPENCLAW_COMMIT" ]]; then
        ui_success "openclaw already at target commit"
        return 0
    fi

    # reset 上游到干净状态（之前可能 apply 过 patches）
    git -C "$openclaw_dir" reset --hard HEAD 2>/dev/null || true
    git -C "$openclaw_dir" clean -fd 2>/dev/null || true

    if ! git -C "$openclaw_dir" cat-file -e "${OPENCLAW_COMMIT}^{tree}" 2>/dev/null; then
        ui_info "Fetching openclaw target commit"
        run_required_step "Fetching openclaw commit" git -C "$openclaw_dir" fetch origin "$OPENCLAW_COMMIT"
    fi
    run_required_step "Checking out openclaw@pin" git -C "$openclaw_dir" checkout "$OPENCLAW_COMMIT"
    ui_success "openclaw checked out at ${OPENCLAW_VERSION:-unknown}"
}

# ═══════════════════════════════════════════════════════════════════
# camoufox-cli（Firefox 反指纹浏览器）
# ═══════════════════════════════════════════════════════════════════
install_camoufox_cli() {
    local node="$WISEFLOW_ROOT/$PORTABLE_NODE"
    local npm_bin; npm_bin="$(dirname "$node")/npm"
    local fork_dir="$WISEFLOW_ROOT/camoufox-cli"
    # portable node 的 npm 全局前缀指向 ~/.openclaw，让 camoufox-cli 进 PATH
    export PATH="$(dirname "$node"):$PATH"
    export npm_config_prefix="$WISEFLOW_ROOT"
    if command -v camoufox-cli >/dev/null 2>&1; then
        ui_success "camoufox-cli already installed"
    else
        [[ -d "$fork_dir" ]] || { ui_warn "camoufox-cli fork 不在 tarball 内：$fork_dir；跳过"; return 0; }
        run_required_step "Installing camoufox-cli fork (local)" "$npm_bin" install -g "$fork_dir" --registry=https://registry.npmmirror.com
    fi
    ui_info "Ensuring camoufox Firefox binary (idempotent, ~557MB first run)"
    if ! camoufox-cli install; then
        ui_warn "camoufox-cli install failed; you can run it manually later: camoufox-cli install"
    fi
    ui_success "camoufox-cli ready"
}

# 放置 config template → ~/.openclaw/openclaw.json（onboard 会 merge provider 进来，不清 agents/list）
place_config_template() {
    local openclaw_home="${OPENCLAW_HOME:-$HOME/.openclaw}"
    local config_path="${OPENCLAW_CONFIG_PATH:-$openclaw_home/openclaw.json}"
    local tmpl="$WISEFLOW_ROOT/config-templates/openclaw.json"
    mkdir -p "$openclaw_home"
    if [[ ! -f "$config_path" ]]; then
        [[ -f "$tmpl" ]] && cp "$tmpl" "$config_path"
        ui_success "Placed openclaw.json template"
    else
        ui_info "openclaw.json 已存在，保留（onboard 会 merge）"
    fi
}

# ═══════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════
WISEFLOW_ROOT="${WISEFLOW_ROOT:-$WISEFLOW_ROOT_DEFAULT}"
VERBOSE=0
NO_PROMPT=0
USE_LOCAL=false
TAGLINE="$DEFAULT_TAGLINE"

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --verbose)
                VERBOSE=1
                shift
                ;;
            --no-prompt)
                NO_PROMPT=1
                shift
                ;;
            --use-local)
                # 复用 WISEFLOW_ROOT 已有的本地 wiseflow checkout，跳 clone/fetch，保本地改动
                # 主要给开发/调试场景：在仓内跑 install.sh 验流程，不想被 fetch+reset 盖掉改动
                USE_LOCAL=true
                shift
                ;;
            --root)
                if [[ $# -lt 2 || "${2:-}" == --* ]]; then
                    ui_error "Missing value for $1"
                    exit 2
                fi
                WISEFLOW_ROOT="$2"
                shift 2
                ;;
            --help|-h)
                cat <<EOF
wiseflow installer (macOS + Linux) — 预构建 tarball 路线

Usage:
  curl -fsSL https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.sh | bash
  curl -fsSL https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.sh | bash -s -- [options]

Options:
  --root <dir>       Install directory (default: ~/.openclaw)
  --verbose          Print debug output
  --no-prompt        Disable prompts (CI/automation)
  --help, -h         Show this help

Env:
  XIAOBEI_REPO       GitHub 仓（owner/repo，默认 TeamWiseFlow/xiaobei；测试可指 bigbrother666sh/wiseflow）
  XIAOBEI_MIRROR     自建镜像站根（国内加速），形如 https://mirror.example.com/xiaobei
  XIAOBEI_TAG        指定版本 tag（默认拉最新 release）
EOF
                exit 0
                ;;
            *)
                ui_error "Unknown option: $1"
                exit 2
                ;;
        esac
    done
}

configure_verbose() {
    if [[ "$VERBOSE" != "1" ]]; then
        return 0
    fi
    set -x
}

main() {
    parse_args "$@"
    configure_verbose

    echo -e "${INFO}Preparing installer interface...${NC}"
    bootstrap_gum_temp || true
    print_installer_banner
    print_gum_status
    detect_os_or_die

    if [[ "$OS" == "linux" ]]; then
        export DEBIAN_FRONTEND="${DEBIAN_FRONTEND:-noninteractive}"
        export NEEDRESTART_MODE="${NEEDRESTART_MODE:-a}"
    fi

    ui_kv "OS" "$OS"
    ui_kv "Install root" "$WISEFLOW_ROOT"
    ui_kv "Repo" "$WISEFLOW_REPO"
    [[ -n "$XIAOBEI_MIRROR" ]] && ui_kv "Mirror" "$XIAOBEI_MIRROR"
    echo ""

    # ─── Step 1: 平台 + 版本 ────────────────────────────────
    ui_stage "Detecting platform"
    detect_platform_asset
    ui_stage "Resolving latest release"
    resolve_latest_version

    # ─── Step 2: 下载 + 解压 tarball ─────────────────────────
    ui_stage "Downloading pre-built tarball"
    download_and_extract_tarball

    # ─── Step 3: pnpm install --prod（拉依赖，无 OOM）────────
    ui_stage "Installing dependencies (pnpm install --prod)"
    pnpm_install_prod

    # ─── Step 4: python skill deps ───────────────────────────
    ui_stage "Installing python skill deps"
    install_python_deps

    # ─── Step 5: 放 config template + 预填微信 binding ───────
    ui_stage "Placing config template"
    place_config_template
    ui_stage "Pre-filling WeChat channel config"
    prefill_weixin_channel

    # ─── Step 6: setup-crew（裸跑，无 --force）──────────────
    ui_stage "Setting up crew templates"
    if [[ -f "$WISEFLOW_ROOT/scripts/setup-crew.sh" ]]; then
        bash "$WISEFLOW_ROOT/scripts/setup-crew.sh" || ui_warn "setup-crew.sh 非零退出（可后续手动 --force 修复）"
    else
        ui_warn "setup-crew.sh 不在 tarball 内，跳过"
    fi

    # ─── Step 7: camoufox-cli + Firefox binary ───────────────
    ui_stage "Installing camoufox-cli browser"
    install_camoufox_cli

    # ─── Step 8: Onboard (interactive: model provider + key) ─
    ui_stage "Running openclaw onboard"
    run_onboard

    # ─── 完成 ────────────────────────────────────────────────
    echo ""
    ui_celebrate "🦞 wiseflow installed successfully!"
    echo ""
    ui_section "Next steps"
    echo "  把 $WISEFLOW_ROOT/bin 加到 PATH 即可用 openclaw 命令："
    echo "    export PATH=\"$WISEFLOW_ROOT/bin:\$PATH\""
    echo ""
    echo "  1. Bind your WeChat channel:"
    echo "     openclaw channels login --channel openclaw-weixin"
    echo "     openclaw pairing list openclaw-weixin"
    echo "     openclaw pairing approve openclaw-weixin <id>"
    echo ""
    echo "  2. Open the dashboard: http://127.0.0.1:18789"
    echo ""
    echo "  3. Update later with: bash $WISEFLOW_ROOT/scripts/update.sh"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════
# 预填微信 channel config（fork 自 update.sh install_weixin_channel 末尾段）
# 不装插件（update.sh 里装的，因为已 git clone；这里首次 onboard 后插件由 onboard 装
# 或后续 manually）——只预填 openclaw.json 的 bindings + channels.entries
# ═══════════════════════════════════════════════════════════════════
prefill_weixin_channel() {
    local openclaw_home="${OPENCLAW_HOME:-$HOME/.openclaw}"
    local config_path="${OPENCLAW_CONFIG_PATH:-$openclaw_home/openclaw.json}"
    if [[ ! -f "$config_path" ]]; then
        ui_warn "openclaw.json not present yet ($config_path); skip channel prefill"
        return 0
    fi
    "$WISEFLOW_ROOT/$PORTABLE_NODE" -e '
        const fs = require("fs");
        const p = process.argv[1];
        const c = JSON.parse(fs.readFileSync(p, "utf8"));
        c.channels = c.channels || {};
        c.channels["openclaw-weixin"] = { ...(c.channels["openclaw-weixin"] || {}), enabled: true };
        c.session = { ...(c.session || {}), dmScope: "per-channel-peer" };
        if (!Array.isArray(c.bindings)) c.bindings = [];
        const hasMainWeixin = c.bindings.some((b) => b?.agentId === "main" && b?.match?.channel === "openclaw-weixin");
        if (!hasMainWeixin) {
            c.bindings.push({ agentId: "main", comment: "openclaw-weixin -> Main Agent onboarding entry", match: { channel: "openclaw-weixin" } });
        }
        fs.writeFileSync(p, JSON.stringify(c, null, 2) + "\n");
    ' "$config_path"
    ui_success "WeChat channel pre-bound to Main Agent in openclaw.json"
}

# ═══════════════════════════════════════════════════════════════════
# 调 openclaw onboard
# 跳：channels / skills / bootstrap / health / ui
# 保留：search（让用户配供应商 + key）/ auth-choice（模型供应商）/ daemon install
# ═══════════════════════════════════════════════════════════════════
run_onboard() {
    # 走 tarball 内 wrapper（portable node + openclaw.mjs）
    local claw_cmd="$WISEFLOW_ROOT/bin/openclaw"

    if ! is_promptable; then
        ui_warn "No TTY; cannot run interactive onboard"
        ui_info "After install, run: $claw_cmd onboard --skip-channels --skip-skills --skip-bootstrap --skip-health --skip-ui --install-daemon"
        return 0
    fi

    ui_info "Starting openclaw onboard (interactive: model provider + API key)"
    ui_info "Skipping: channels / skills / bootstrap / health / ui (pre-filled by wiseflow)"
    echo ""

    # redirect stdin from /dev/tty so the interactive prompter works under curl|bash
    exec </dev/tty
    "$claw_cmd" onboard \
        --skip-channels \
        --skip-skills \
        --skip-bootstrap \
        --skip-health \
        --skip-ui \
        --install-daemon || {
        ui_error "Onboarding failed"
        echo "Re-run manually: $claw_cmd onboard --skip-channels --skip-skills --skip-bootstrap --skip-health --skip-ui --install-daemon"
        exit 1
    }
    ui_success "Onboarding complete"
}

if [[ "${WISEFLOW_INSTALL_SH_NO_RUN:-0}" != "1" ]]; then
    main "$@"
fi
