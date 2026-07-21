#!/bin/bash
# install.sh - wiseflow 一键首装脚本（预构建 tarball 路线）
#
# 用法：
#   curl -fsSL https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.sh | bash
#
# 与 update.sh 区别：
#   - install.sh = 首装路线（拉预构建 tarball → pnpm install --prod → 交互收 AWK_API_KEY + daemon install，全程无需用户预装 Node/git/pnpm）
#   - update.sh  = 已装用户的升级路线（拉新 tarball → pnpm install --prod → daemon reload）
#
# 执行流程：
#   1. 检测 OS + arch → 选 tarball asset（linux-x64 / mac-arm64 / mac-x64 / win-x64）
#   2. bootstrap gum UI（TTY 才有，非 TTY 静默跳过）
#   3. 解析最新 release tag（GitHub API，或 XIAOBEI_MIRROR env 指向自建镜像）
#   4. 下载 xiaobei-{ver}-{plat}.{tar.zst|tar.gz} → 临时文件（linux 用 zst，mac/win 用 gzip，bsdtar 原生支持）
#   5. 解压到 WISEFLOW_ROOT（默认 ~/xiaobei，程序目录）：openclaw/ + tools/node + tools/pnpm + bin/openclaw + crews/ + skills/ + scripts/ + camoufox-cli/ + awada/
#   6. pnpm install --prod --frozen-lockfile（用 ship 的 portable node + pnpm，在 openclaw/ 下；只拉依赖不编译，无 OOM，native 自动按平台）
#   7. pip install --user（skills 的 python deps，扫 requirements.txt）
#   8. 放置 config-templates/openclaw.json → ~/.openclaw/openclaw.json（运行数据目录 OPENCLAW_HOME）+ 预填微信 channel binding
#   9. setup-crew.sh（裸跑，无 --force；--force 只用户手动修复用；crew 模板来自 WISEFLOW_ROOT/crews，workspace 落 OPENCLAW_HOME）
#   10. camoufox-cli：npm install -g 本地 fork（ship 的 portable node）+ camoufox-cli install 下 Firefox
#   11. openclaw-weixin 插件：openclaw plugins install @tencent-weixin/openclaw-weixin@<pin> --pin（npmmirror）
#   12. 交互问 AWK_API_KEY → 写 gateway env（Linux daemon.env / Darwin service-env/ai.openclaw.gateway.env，均落 OPENCLAW_HOME）
#       → openclaw daemon install + restart（唯一人工输入点；不走 onboard，小白友好）
#   13. 打印访问指引
#
# 目录职责：WISEFLOW_ROOT（~/xiaobei）= 程序（引擎+模板+脚本+工具+wrapper）；OPENCLAW_HOME（~/.openclaw）= 运行数据（config+env+workspace+logs）。
# 已装机器重跑 = 更新（只换 program + rebuild deps + restart，不碰运行数据）；--force 强覆盖运行数据。
#
# tarball 由 .github/workflows/build-dist.yml 在 CI 预构建（方案 B）：CI 只 build 一次，
# ship dist+lockfile（不 ship node_modules）+ pnpm + portable Node，用户侧 pnpm install --prod 重建 node_modules。
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════
WISEFLOW_REPO="${XIAOBEI_REPO:-TeamWiseFlow/xiaobei}"
# 程序目录（引擎源码 + crew 模板 + 脚本 + portable node/pnpm + camoufox-cli fork + bin wrapper）
# 与运行数据目录 OPENCLAW_HOME（~/.openclaw：openclaw.json + daemon.env + workspace-*）分离。
# 不隐藏：用户能直接 ls 看到，符合"小白友好"。
WISEFLOW_ROOT_DEFAULT="${XIAOBEI_HOME:-$HOME/xiaobei}"
# 默认走 atomgit 国内镜像（仓根），--github 或 XIAOBEI_SOURCE=github 切回 GitHub。
# 资产 URL 构造为 $XIAOBEI_MIRROR/releases/download/{tag}/xiaobei-{tag}-{plat}.{tar.zst|tar.gz}
XIAOBEI_ATOMGIT_MIRROR="https://atomgit.com/wiseflow/xiaobei"
if [[ "${XIAOBEI_SOURCE:-}" == "github" ]]; then
    XIAOBEI_MIRROR="${XIAOBEI_MIRROR:-}"
else
    XIAOBEI_MIRROR="${XIAOBEI_MIRROR:-$XIAOBEI_ATOMGIT_MIRROR}"
fi
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
        # macOS bsdtar 不带 zstd filter、小白机也无 zstd 二进制，用 gzip（bsdtar 原生支持）
        TAR_EXT="tar.gz"
    elif [[ "$OS" == "linux" ]]; then
        [[ "$arch" == "arm64" ]] && { ui_error "linux-arm64 tarball 暂未构建，仅 linux-x64"; exit 1; }
        PLAT="linux-$arch"
        # Linux tar 普遍带 --zstd，压缩率更好
        TAR_EXT="tar.zst"
    fi
    ui_success "Platform asset: $PLAT"
}

# 解析最新 release tag + 版本号
# atomgit（Gitea）每晚自动同步上游 tag + release，走其 /api/v1/repos/<o>/<r>/releases/latest
# 全程不访问 api.github.com；--github 或自定义镜像回退 GitHub API
resolve_latest_version() {
    if [[ -n "${XIAOBEI_TAG:-}" ]]; then
        XIAOBEI_VER="${XIAOBEI_TAG#v}"
        ui_success "Using pinned tag: $XIAOBEI_TAG"
        return 0
    fi
    # atomgit / 自建 Gitea 镜像：从 mirror URL 推导 Gitea API（host + owner/repo）
    if [[ -n "${XIAOBEI_MIRROR:-}" ]]; then
        local m="${XIAOBEI_MIRROR%/}"
        m="${m#https://}"; m="${m#http://}"
        local host="${m%%/*}"
        local repo_path="${m#*/}"
        if [[ -n "$host" && -n "$repo_path" ]]; then
            local api="https://$host/api/v1/repos/$repo_path/releases/latest"
            local resp
            resp="$(curl -fsSL "$api" 2>/dev/null || true)"
            XIAOBEI_TAG="$(printf '%s' "$resp" | grep -oE '"tag_name"[[:space:]]*:[[:space:]]*"v[^"]+"' | head -1 | sed -E 's/.*"v([^"]+)".*/v\1/')"
            if [[ -n "$XIAOBEI_TAG" ]]; then
                XIAOBEI_VER="${XIAOBEI_TAG#v}"
                ui_success "Latest release (via $host): $XIAOBEI_TAG"
                return 0
            fi
            ui_warn "镜像 Gitea API 未取到 tag，回退 GitHub API"
        fi
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
    local asset="xiaobei-${XIAOBEI_TAG}-${PLAT}.${TAR_EXT}"
    if [[ -n "$XIAOBEI_MIRROR" ]]; then
        echo "$XIAOBEI_MIRROR/releases/download/$XIAOBEI_TAG/$asset"
    else
        echo "https://github.com/$WISEFLOW_REPO/releases/download/$XIAOBEI_TAG/$asset"
    fi
}

download_and_extract_tarball() {
    local url; url="$(tarball_url)"
    local asset="xiaobei-${XIAOBEI_TAG}-${PLAT}.${TAR_EXT}"
    local tmp
    if [[ -n "${XIAOBEI_TARBALL:-}" && -f "${XIAOBEI_TARBALL:-}" ]]; then
        ui_kv "Asset" "$asset (local)"
        ui_kv "File" "$XIAOBEI_TARBALL"
        tmp="$XIAOBEI_TARBALL"
    else
        ui_kv "Asset" "$asset"
        ui_kv "URL" "$url"
        tmp="$(mktempfile)"
        ui_info "Downloading $asset (~120MB)..."
        download_file "$url" "$tmp"
        ui_success "Downloaded"
    fi

    mkdir -p "$WISEFLOW_ROOT"
    ui_info "Extracting to $WISEFLOW_ROOT ..."
    if [[ "$TAR_EXT" == "tar.zst" ]]; then
        tar --zstd -xf "$tmp" -C "$WISEFLOW_ROOT"
    else
        tar -xzf "$tmp" -C "$WISEFLOW_ROOT"
    fi
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
    if [[ "$SKIP_BROWSER" == "true" ]]; then
        ui_info "跳过 camoufox-cli 浏览器二进制（--skip-browser）；后续手动：camoufox-cli install"
        return 0
    fi
    local node="$WISEFLOW_ROOT/$PORTABLE_NODE"
    local npm_bin; npm_bin="$(dirname "$node")/npm"
    local fork_dir="$WISEFLOW_ROOT/camoufox-cli"
    # portable node 的 npm 全局前缀指向 ~/.openclaw，让 camoufox-cli 进 PATH
    export PATH="$(dirname "$node"):$PATH"
    export npm_config_prefix="$WISEFLOW_ROOT"
    # fork 的 dist 是 tsc 编译，camoufox-js/playwright-core/pdf-lib 是 external import
    # （没打进 bundle），运行时靠 fork 目录下的 node_modules 解析。
    # tarball 为瘦身 ship 的 fork 不带 node_modules，npm install -g <目录> 又是 symlink
    # 到源目录（非 copy），所以必须先在 fork 目录装运行时依赖，否则 bin 跑起来 ERR_MODULE_NOT_FOUND。
    if command -v camoufox-cli >/dev/null 2>&1 && [ -d "$fork_dir/node_modules/camoufox-js" ]; then
        ui_success "camoufox-cli already installed"
    else
        [[ -d "$fork_dir" ]] || { ui_warn "camoufox-cli fork 不在 tarball 内：$fork_dir；跳过"; return 0; }
        run_required_step "Installing camoufox-cli fork deps" bash -c "cd '$fork_dir' && '$npm_bin' install --omit=dev --registry=https://registry.npmmirror.com"
        run_required_step "Installing camoufox-cli fork (local)" "$npm_bin" install -g "$fork_dir" --registry=https://registry.npmmirror.com
    fi
    ui_info "Ensuring camoufox Firefox binary (idempotent, ~557MB first run)"
    if ! camoufox-cli install; then
        ui_warn "camoufox-cli install failed; you can run it manually later: camoufox-cli install"
    fi
    ui_success "camoufox-cli ready"
}

# 装 openclaw-weixin 插件（config template 已预置 channel，但插件本体要 openclaw plugins install）
# 读 tarball 内 openclaw-weixin.version.json 的 pin，走国内 npmmirror。
# 幂等：openclaw plugins list 含 openclaw-weixin 则跳过。
install_weixin_plugin() {
    local claw_cmd="$WISEFLOW_ROOT/bin/openclaw"
    local pin_file="$WISEFLOW_ROOT/openclaw-weixin.version.json"
    [[ -f "$claw_cmd" ]] || { ui_warn "openclaw wrapper 不在 $claw_cmd；跳过 weixin 插件"; return 0; }
    local pkg ver
    if [[ -f "$pin_file" ]]; then
        pkg=$(python3 -c "import json;print(json.load(open('$pin_file'))['openclaw-weixin']['package'])" 2>/dev/null || true)
        ver=$(python3 -c "import json;print(json.load(open('$pin_file'))['openclaw-weixin']['version'])" 2>/dev/null || true)
    fi
    pkg="${pkg:-@tencent-weixin/openclaw-weixin}"
    ver="${ver:-2.4.6}"
    # 幂等检查：plugins list 已含则跳过
    if "$claw_cmd" plugins list 2>/dev/null | grep -q "openclaw-weixin"; then
        ui_success "openclaw-weixin plugin already installed"
        return 0
    fi
    ui_info "Installing openclaw-weixin plugin (${pkg}@${ver}) via npmmirror"
    if npm_config_registry=https://registry.npmmirror.com "$claw_cmd" plugins install "${pkg}@${ver}" --pin 2>/dev/null; then
        ui_success "openclaw-weixin plugin installed"
    else
        ui_warn "openclaw-weixin 插件安装失败；可后续手动：npm_config_registry=https://registry.npmmirror.com $claw_cmd plugins install ${pkg}@${ver} --pin"
    fi
}

# 装 awada 本地插件依赖（ws + zod）。
# awada 是 TS 插件经 jiti 运行时加载（openclaw.extensions: ["./index.ts"]），无需 build；
# tarball ship 的 awada/ 不带 node_modules，这里 npm install --omit=dev 装运行时依赖。
# config-templates/openclaw.json 已预置 plugins.load.paths=["${XIAOBEI_HOME}/awada"] + entries.awada.enabled=false，
# XIAOBEI_HOME 由 install_gateway_and_env 写进 daemon.env，gateway 启动时 ${XIAOBEI_HOME} env ref 解析到本目录。
install_awada_plugin() {
    local node="$WISEFLOW_ROOT/$PORTABLE_NODE"
    local npm_bin; npm_bin="$(dirname "$node")/npm"
    local awada_dir="$WISEFLOW_ROOT/awada"
    [[ -d "$awada_dir" ]] || { ui_warn "awada 不在 tarball 内：$awada_dir；跳过"; return 0; }
    if [ -d "$awada_dir/node_modules/ws" ] && [ -d "$awada_dir/node_modules/zod" ]; then
        ui_success "awada deps already installed"
        return 0
    fi
    ui_info "Installing awada plugin deps (ws + zod) via npmmirror"
    if bash -c "cd '$awada_dir' && '$npm_bin' install --omit=dev --registry=https://registry.npmmirror.com"; then
        ui_success "awada deps installed"
    else
        ui_warn "awada deps install 失败；可后续手动：cd '$awada_dir' && npm install --omit=dev"
    fi
}

# 放置 config template → ~/.openclaw/openclaw.json（已预置 awk provider，apiKey=${AWK_API_KEY} 由 gateway env 注入）
place_config_template() {
    local openclaw_home="${OPENCLAW_HOME:-$HOME/.openclaw}"
    local config_path="${OPENCLAW_CONFIG_PATH:-$openclaw_home/openclaw.json}"
    local tmpl="$WISEFLOW_ROOT/config-templates/openclaw.json"
    mkdir -p "$openclaw_home"
    if [[ ! -f "$config_path" ]]; then
        [[ -f "$tmpl" ]] && cp "$tmpl" "$config_path"
        ui_success "Placed openclaw.json template"
    elif [[ "$FORCE_RUNTIME" == "true" ]]; then
        local backup="${config_path}.bak.$(date +%s 2>/dev/null || echo 0)"
        cp "$config_path" "$backup"
        [[ -f "$tmpl" ]] && cp "$tmpl" "$config_path"
        ui_warn "openclaw.json 已存在，--force 覆盖（旧文件备份到 $backup）"
    else
        ui_info "openclaw.json 已存在，保留"
    fi
}

# ═══════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════
WISEFLOW_ROOT="${WISEFLOW_ROOT:-$WISEFLOW_ROOT_DEFAULT}"
# 运行数据目录（openclaw.json / daemon.env / workspace-*）；openclaw 引擎默认也用 ~/.openclaw
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
export OPENCLAW_HOME
VERBOSE=0
NO_PROMPT=0
USE_LOCAL=false
FORCE_RUNTIME=false
SKIP_WEIXIN_BIND=false
SKIP_BROWSER=false
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
            --force)
                # 强覆盖已有运行数据（~/.openclaw/openclaw.json + workspace-* + daemon.env）
                # 默认已装机器重跑 install 只更新 program（tarball）+ rebuild deps，不碰运行数据
                FORCE_RUNTIME=true
                shift
                ;;
            --github)
                # 切回 GitHub release（不走默认 atomgit 镜像）
                XIAOBEI_SOURCE=github
                XIAOBEI_MIRROR=""
                shift
                ;;
            --mirror)
                if [[ $# -lt 2 || "${2:-}" == --* ]]; then
                    ui_error "Missing value for $1"
                    exit 2
                fi
                XIAOBEI_MIRROR="$2"
                shift 2
                ;;
            --use-local)
                # 复用 WISEFLOW_ROOT 已有的本地 wiseflow checkout，跳 clone/fetch，保本地改动
                # 主要给开发/调试场景：在仓内跑 install.sh 验流程，不想被 fetch+reset 盖掉改动
                USE_LOCAL=true
                shift
                ;;
            --skip-bind)
                # 跳过末尾微信扫码绑定（CI/自动化或想后续手动绑）
                SKIP_WEIXIN_BIND=true
                shift
                ;;
            --skip-browser)
                # 跳过 camoufox-cli 装浏览器二进制（冒烟/CI，省 ~557MB Firefox 下载）
                SKIP_BROWSER=true
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
  --root <dir>       Program install directory (default: ~/xiaobei; runtime data stays in ~/.openclaw)
  --github           Use GitHub releases instead of the default atomgit mirror
  --mirror <url>     Custom mirror root (overrides default atomgit)
  --force            Overwrite existing runtime data (~/.openclaw); default preserves it on re-install
  --skip-bind        Skip the WeChat QR binding at the end (CI/automation)
  --skip-browser     Skip camoufox-cli browser binary install (smoke/CI, saves ~557MB Firefox)
  --verbose          Print debug output
  --no-prompt        Disable prompts (CI/automation)
  --help, -h         Show this help

Env:
  XIAOBEI_REPO       GitHub 仓（owner/repo，默认 TeamWiseFlow/xiaobei；测试可指 bigbrother666sh/wiseflow）
  XIAOBEI_SOURCE     设为 github 切回 GitHub release（等价 --github）
  XIAOBEI_MIRROR     镜像站根（默认 atomgit 国内镜像 https://atomgit.com/wiseflow/xiaobei，走其 Gitea API 取最新 tag）
  XIAOBEI_TAG        指定版本 tag（默认拉最新 release；自定义镜像建议配此项）
  XIAOBEI_TARBALL    本地已下好的 tarball 路径；设了就跳过下载直接用它（网络差时手工下好塞进来）
  XIAOBEI_HOME       程序目录覆盖（默认 ~/xiaobei）
  OPENCLAW_HOME      运行数据目录覆盖（默认 ~/.openclaw）
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

# ═══════════════════════════════════════════════════════════════════
# 首装末尾：自动出微信绑定二维码，手机扫码确认即用
# 已绑（accounts.json 存在）→ 跳过；非 TTY / --no-prompt / --skip-bind → 跳过并提示
# channels login 内部 waitForWeixinLogin 有 3 次刷新上限，外层循环重出直到绑成功
# ═══════════════════════════════════════════════════════════════════
weixin_account_bound() {
    local acc
    for acc in \
        "$OPENCLAW_HOME/openclaw-weixin/accounts.json" \
        "$OPENCLAW_HOME/.openclaw/openclaw-weixin/accounts.json"; do
        [[ -f "$acc" ]] && return 0
    done
    return 1
}

bind_weixin_channel() {
    if [[ "$SKIP_WEIXIN_BIND" == "true" || "$NO_PROMPT" == "1" ]]; then
        ui_info "跳过微信扫码绑定（--skip-bind / --no-prompt）；后续手动跑：openclaw channels login --channel openclaw-weixin"
        return 0
    fi
    if weixin_account_bound; then
        ui_success "检测到微信账号已绑定，跳过扫码"
        return 0
    fi
    if [[ ! -t 0 ]]; then
        ui_warn "非交互终端（stdin 非 TTY），跳过微信扫码绑定；后续手动跑：openclaw channels login --channel openclaw-weixin"
        return 0
    fi
    local claw="$WISEFLOW_ROOT/bin/openclaw"
    if [[ ! -x "$claw" ]]; then
        ui_warn "openclaw wrapper 未找到（$claw），跳过微信绑定"
        return 0
    fi
    ui_stage "绑定微信 channel（用手机扫码）"
    echo "  接下来会出二维码，用微信扫一下、点确认，小贝就能用了。"
    echo "  扫码慢没关系，二维码会自动刷新；扫完即继续。"
    echo ""
    local attempt=0
    while [[ $attempt -lt 5 ]]; do
        attempt=$((attempt + 1))
        # channels login 出码 + 等扫码确认；扫成功后写 accounts.json
        "$claw" channels login --channel openclaw-weixin || true
        if weixin_account_bound; then
            ui_success "微信账号绑定成功"
            return 0
        fi
        [[ $attempt -lt 5 ]] && ui_warn "本轮未检测到绑定，重出二维码（第 $((attempt + 1)) 次）..."
    done
    ui_warn "多次扫码未完成绑定。可后续手动跑：$claw channels login --channel openclaw-weixin"
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
    ui_kv "Program dir" "$WISEFLOW_ROOT"
    ui_kv "Runtime dir" "$OPENCLAW_HOME"
    ui_kv "Repo" "$WISEFLOW_REPO"
    [[ -n "$XIAOBEI_MIRROR" ]] && ui_kv "Mirror" "$XIAOBEI_MIRROR"
    echo ""

    # ─── 检测是否已装（决定走 update 还是 fresh install）──────
    # 已装 = $OPENCLAW_HOME/openclaw.json 存在。已装且非 --force：只更新 program
    # （tarball 解压 + rebuild deps + 幂等刷 camoufox/weixin/awada + daemon restart），
    # 不碰运行数据（openclaw.json / workspace-* / daemon.env 已有 key）。--force 强覆盖。
    local is_update=false
    if [[ -f "$OPENCLAW_HOME/openclaw.json" && "$FORCE_RUNTIME" != "true" ]]; then
        is_update=true
        ui_warn "检测到已有安装（$OPENCLAW_HOME/openclaw.json）→ 走更新路线，保留运行数据（传 --force 可强覆盖）"
    fi

    # ─── Step 1: 平台 + 版本 ────────────────────────────────
    ui_stage "Detecting platform"
    detect_platform_asset
    ui_stage "Resolving latest release"
    resolve_latest_version

    # ─── Step 2: 下载 + 解压 tarball（更新 program）──────────
    ui_stage "Downloading pre-built tarball"
    download_and_extract_tarball

    # ─── Step 3: pnpm install --prod（拉依赖，无 OOM）────────
    ui_stage "Installing dependencies (pnpm install --prod)"
    pnpm_install_prod

    # ─── Step 4: python skill deps ───────────────────────────
    ui_stage "Installing python skill deps"
    install_python_deps

    # ─── Step 5: awada 本地插件 deps（幂等）──────────────────
    ui_stage "Installing awada plugin deps"
    install_awada_plugin

    # ─── Step 6: camoufox-cli + Firefox binary（幂等）────────
    ui_stage "Installing camoufox-cli browser"
    install_camoufox_cli

    # ─── Step 7: openclaw-weixin 插件（幂等）─────────────────
    ui_stage "Installing WeChat plugin"
    install_weixin_plugin

    if [[ "$is_update" == "true" ]]; then
        # ─── 更新路线：不碰运行数据，只刷 gateway env 路径 + restart ──
        ui_stage "Refreshing gateway env and restarting"
        refresh_gateway_env_only
    else
        # ─── 首装路线：放 config + 预填微信 + setup-crew + gateway daemon ──
        ui_stage "Placing config template"
        place_config_template
        ui_stage "Pre-filling WeChat channel config"
        prefill_weixin_channel

        ui_stage "Setting up crew templates"
        if [[ -f "$WISEFLOW_ROOT/scripts/setup-crew.sh" ]]; then
            local crew_force=""
            [[ "$FORCE_RUNTIME" == "true" ]] && crew_force="--force"
            OPENCLAW_HOME="$OPENCLAW_HOME" XIAOBEI_BIN_DIR="$WISEFLOW_ROOT/bin" \
                bash "$WISEFLOW_ROOT/scripts/setup-crew.sh" $crew_force \
                || ui_warn "setup-crew.sh 非零退出（可后续手动 --force 修复）"
        else
            ui_warn "setup-crew.sh 不在 tarball 内，跳过"
        fi

        # 交互收 AWK_API_KEY + 装 gateway daemon（不走 onboard，小白友好）
        ui_stage "Configuring API key and gateway"
        install_gateway_and_env

        # 首装末尾自动出微信二维码扫码绑定（已绑过则跳过）
        bind_weixin_channel
    fi

    # ─── 完成 ────────────────────────────────────────────────
    echo ""
    if [[ "$is_update" == "true" ]]; then
        ui_celebrate "🦞 wiseflow updated successfully!"
    else
        ui_celebrate "🦞 wiseflow installed successfully!"
    fi
    echo ""
    ui_section "Next steps"
    echo "  把 $WISEFLOW_ROOT/bin 加到 PATH 即可用 openclaw 命令："
    echo "    export PATH=\"$WISEFLOW_ROOT/bin:\$PATH\""
    echo ""
    echo "  Dashboard: http://127.0.0.1:18789"
    echo "  Update later: re-run this install script (preserves ~/.openclaw runtime data)."
    echo ""
}

# ═══════════════════════════════════════════════════════════════════
# 预填微信 channel config（fork 自 update.sh install_weixin_channel 末尾段）
# 不装插件（update.sh 里装的，因为已 git clone；这里只预填 openclaw.json 的
# bindings + channels.entries，插件由用户后续 manually 装）
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
# ═════════════════════════════════════════════════════════════════
# 不走 openclaw onboard（对小白太复杂）。改为：
# 1. 交互问 AWK_API_KEY（config_template 里 awk.apiKey=${AWK_API_KEY}）
# 2. 写进 gateway env 文件（Linux: daemon.env / Darwin: service-env/ai.openclaw.gateway.env）
# 3. openclaw daemon install + restart，gateway 起来后 config 能解析到 key
# 平台分支复用 c441220 经验：Linux 先写 env+drop-in 再 install（避免 StartLimitBurst）；
# Darwin 先 install（创建 env 文件）再追加。
# ═════════════════════════════════════════════════════════════════
_USER_PROMPT_KEYS="AWK_API_KEY"
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

# 向 env 文件幂等写入缺失的询问 key + 硬编码默认值
# $1: env 文件路径   $2: kv（KEY=VALUE）或 export（export KEY='value'）
write_missing_env() {
    local env_file="$1" format="$2" _key="" _val="" _entry="" _sv="" _missing=""
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
        echo "$_missing"; echo ""
    fi
    for _key in $_USER_PROMPT_KEYS; do
        if [ "$format" = "export" ]; then
            grep -qE "^export ${_key}=" "$env_file" 2>/dev/null && continue
        else
            grep -qE "^${_key}=" "$env_file" 2>/dev/null && continue
        fi
        _sv="${!_key-}"
        if is_promptable; then
            _val="$(prompt_env_value "$_key" "${_sv:-}" "${_sv:+shell}")"
        else
            _val="${_sv:-}"
            [ -z "$_val" ] && ui_warn "Missing ${_key} in non-interactive mode; leaving unset."
        fi
        # 清洗：去所有空白。API key 是不透明 token，绝不含空白；
        # 防粘贴/环境变量带入前导换行或空格致 daemon.env 出现 `KEY=\nvalue` 错行。
        _val="$(printf '%s' "$_val" | tr -d '[:space:]')"
        if [ -n "$_val" ]; then
            if [ "$format" = "export" ]; then
                printf "export %s='%s'\n" "$_key" "${_val//\'/\'\\\'\'}" >> "$env_file"
            else
                printf "%s=%s\n" "$_key" "$_val" >> "$env_file"
            fi
        fi
    done
    for _entry in $_HARDCODED_DEFAULTS; do
        _key="${_entry%%=*}"; _val="${_entry#*=}"
        if [ "$format" = "export" ]; then
            grep -qE "^export ${_key}=" "$env_file" 2>/dev/null && continue
            printf "export %s='%s'\n" "$_key" "$_val" >> "$env_file"
        else
            grep -qE "^${_key}=" "$env_file" 2>/dev/null && continue
            printf "%s=%s\n" "$_key" "$_val" >> "$env_file"
        fi
    done
}

# 确保 env 文件的 PATH 含 portable node bin + openclaw bin（gateway 子进程解析 wrapper 用）
ensure_env_path() {
    local env_file="$1" node_bin_dir="$2" oc_bin_dir="$3"
    [ -f "$env_file" ] || return 0
    local need="${node_bin_dir}:${oc_bin_dir}"
    local cur; cur="$(grep -E '^PATH=' "$env_file" | tail -n1 | sed -E 's/^PATH=//' || true)"
    if [ -z "$cur" ]; then
        printf 'PATH=%s:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n' "$need" >> "$env_file"
        return 0
    fi
    case ":$cur:" in
        *":$node_bin_dir:"*) return 0 ;;
    esac
    {
        grep -v '^PATH=' "$env_file" 2>/dev/null || true
        printf 'PATH=%s:%s\n' "$need" "$cur"
    } > "${env_file}.new"
    mv "${env_file}.new" "$env_file"
}

# 把 XIAOBEI_HOME（程序目录绝对路径）幂等写进 env 文件，让 openclaw.json 里
# plugins.load.paths 的 ${XIAOBEI_HOME}/awada env ref 在 gateway 启动时能解析。
# $1: env 文件路径   $2: format（kv 或 export）
ensure_env_xiaobei_home() {
    local env_file="$1" format="$2"
    [ -f "$env_file" ] || return 0
    if [ "$format" = "export" ]; then
        grep -qE "^export XIAOBEI_HOME=" "$env_file" 2>/dev/null && return 0
        printf "export XIAOBEI_HOME='%s'\n" "$WISEFLOW_ROOT" >> "$env_file"
    else
        grep -qE "^XIAOBEI_HOME=" "$env_file" 2>/dev/null && return 0
        printf 'XIAOBEI_HOME=%s\n' "$WISEFLOW_ROOT" >> "$env_file"
    fi
}

# 更新路线用：不问 AWK_API_KEY、不 daemon install，只幂等刷 gateway env 路径
# （PATH + XIAOBEI_HOME）+ restart gateway 让新 program 生效。
refresh_gateway_env_only() {
    local claw_cmd="$WISEFLOW_ROOT/bin/openclaw"
    local node_bin_dir; node_bin_dir="$(dirname "$WISEFLOW_ROOT/$PORTABLE_NODE")"
    local oc_bin_dir="$WISEFLOW_ROOT/bin"
    local systemd_env="$OPENCLAW_HOME/daemon.env"
    local macos_env="$OPENCLAW_HOME/service-env/ai.openclaw.gateway.env"

    if [ "$(uname -s)" = "Linux" ] && [ -f "$systemd_env" ]; then
        ensure_env_path "$systemd_env" "$node_bin_dir" "$oc_bin_dir"
        ensure_env_xiaobei_home "$systemd_env" kv
        if command -v systemctl >/dev/null 2>&1; then
            systemctl --user daemon-reload 2>/dev/null || true
            systemctl --user restart "openclaw-gateway.service" 2>/dev/null && ui_success "Restarted gateway"
        fi
    elif [ "$(uname -s)" = "Darwin" ] && [ -f "$macos_env" ]; then
        ensure_env_path "$macos_env" "$node_bin_dir" "$oc_bin_dir"
        ensure_env_xiaobei_home "$macos_env" export
        "$claw_cmd" gateway restart 2>/dev/null && ui_success "Restarted gateway"
    else
        ui_info "无 gateway env 文件或平台不支持自动 restart；可手动：$claw_cmd gateway restart"
    fi
    ui_success "Gateway env refreshed"
}

install_gateway_and_env() {
    local claw_cmd="$WISEFLOW_ROOT/bin/openclaw"
    local node_bin_dir; node_bin_dir="$(dirname "$WISEFLOW_ROOT/$PORTABLE_NODE")"
    local oc_bin_dir="$WISEFLOW_ROOT/bin"
    # gateway env 文件属运行数据，落 OPENCLAW_HOME（非程序目录 WISEFLOW_ROOT）
    local systemd_env="$OPENCLAW_HOME/daemon.env"
    local macos_env="$OPENCLAW_HOME/service-env/ai.openclaw.gateway.env"

    # redirect stdin from /dev/tty so interactive read 工作于 curl|bash
    if is_promptable; then exec </dev/tty; fi

    if [ "$(uname -s)" = "Linux" ]; then
        # --- Linux: 先写 daemon.env + drop-in，再 daemon install（避免首次启动 StartLimitBurst）---
        mkdir -p "$(dirname "$systemd_env")"
        [ -f "$systemd_env" ] || touch "$systemd_env"
        chmod 600 "$systemd_env"
        write_missing_env "$systemd_env" kv
        ensure_env_path "$systemd_env" "$node_bin_dir" "$oc_bin_dir"
        ensure_env_xiaobei_home "$systemd_env" kv
        # WSL2 GUI 显示变量
        if grep -qi microsoft /proc/version 2>/dev/null; then
            {
                grep -vE "^(DISPLAY|WAYLAND_DISPLAY|XDG_RUNTIME_DIR)=" "$systemd_env" 2>/dev/null || true
                printf 'DISPLAY=:0\nWAYLAND_DISPLAY=wayland-0\nXDG_RUNTIME_DIR=/mnt/wslg/runtime-dir\n'
            } > "${systemd_env}.new"
            mv "${systemd_env}.new" "$systemd_env"; chmod 600 "$systemd_env"
        fi
        # systemd drop-in 引用 daemon.env（必须在 daemon install 之前）
        if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
            local svc="openclaw-gateway"
            local dropin_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/${svc}.service.d"
            mkdir -p "$dropin_dir"
            printf '[Service]\nEnvironmentFile=-%s\n' "$systemd_env" > "${dropin_dir}/10-env-file.conf"
            ui_success "systemd drop-in created (will reload after daemon install)"
        fi
        ui_info "Installing gateway daemon service"
        "$claw_cmd" daemon uninstall 2>/dev/null || true
        "$claw_cmd" daemon install || { ui_warn "daemon install failed; run later: $claw_cmd daemon install"; return 0; }
        if command -v systemctl >/dev/null 2>&1; then
            systemctl --user daemon-reload 2>/dev/null || true
            systemctl --user reset-failed "openclaw-gateway.service" 2>/dev/null || true
            systemctl --user restart "openclaw-gateway.service" 2>/dev/null && ui_success "Restarted gateway with daemon.env"
        fi
    elif [ "$(uname -s)" = "Darwin" ]; then
        # --- Darwin: 先 daemon install（创建 mac env 文件），再追加 key，再 restart ---
        ui_info "Installing gateway daemon service"
        "$claw_cmd" daemon uninstall 2>/dev/null || true
        "$claw_cmd" daemon install || { ui_warn "daemon install failed; run later: $claw_cmd daemon install"; return 0; }
        if [ -f "$macos_env" ]; then
            write_missing_env "$macos_env" export
            ensure_env_path "$macos_env" "$node_bin_dir" "$oc_bin_dir"
            ensure_env_xiaobei_home "$macos_env" export
            chmod 600 "$macos_env"
            "$claw_cmd" gateway restart 2>/dev/null || true
            ui_success "Restarted gateway with macos env"
        else
            ui_warn "macOS gateway env file not found at $macos_env"
            ui_info "Ensure gateway installed: $claw_cmd daemon install; then edit $macos_env"
        fi
    else
        ui_warn "Unsupported platform for daemon install; run manually: $claw_cmd daemon install"
    fi
    ui_success "Gateway configured"
}

if [[ "${WISEFLOW_INSTALL_SH_NO_RUN:-0}" != "1" ]]; then
    main "$@"
fi
