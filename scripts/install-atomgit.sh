#!/bin/bash
# install-atomgit.sh - wiseflow 一键首装脚本（预构建 tarball 路线，atomgit 国内镜像专线）
#
# 与 install.sh 区别：本脚本走 atomgit 国内镜像（tarball 走 atomgit.com → GitCode CDN，
#   tag 解析走 api.atomgit.com/api/v5），不经 GitHub；适合国内网络环境。
#
# 用法：
#   bash -c "$(curl -fsSL https://raw.atomgit.com/wiseflow/xiaobei/raw/master/scripts/install-atomgit.sh)"
#   bash -c "$(curl -fsSL https://raw.atomgit.com/wiseflow/xiaobei/raw/master/scripts/install-atomgit.sh)" -s -- [options]
#
# 与 update.sh 区别（两条互不混用的分发路线）：
#   - install-atomgit.sh = tarball 路线首装（已装机器重跑即更新；拉预构建 tarball → pnpm install --prod → 交互收 AWK_API_KEY + daemon install，全程无需用户预装 Node/git/pnpm）
#   - update.sh          = git clone 源码用户的升级路线（git fetch + reset → checkout openclaw@pin → apply-addons.sh → pnpm build → daemon reload；需系统 Node/git/pnpm，pnpm 必须 11+）
#
# 执行流程：
#   1. 检测 OS + arch → 选 tarball asset（linux-x64 / mac-arm64 / mac-x64 / win-x64）
#   2. bootstrap gum UI（TTY 才有，非 TTY 静默跳过）
#   3. 解析最新 release tag（atomgit v5 API：api.atomgit.com/api/v5/repos/wiseflow/xiaobei/releases/latest）
#   4. 下载 xiaobei-{ver}-{plat}.{tar.zst|tar.gz}（atomgit CDN）→ 临时文件（linux 用 zst，mac/win 用 gzip，bsdtar 原生支持）
#   5. 解压到 WISEFLOW_ROOT（默认 ~/xiaobei，程序目录）
#   6. pnpm install --prod --frozen-lockfile（用 ship 的 portable node + pnpm，在 openclaw/ 下；只拉依赖不编译，无 OOM，native 自动按平台）
#   7. pip install --user（skills 的 python deps，扫 requirements.txt）
#   8. 放置 config-templates/openclaw.json → ~/.openclaw/openclaw.json（运行数据目录 OPENCLAW_HOME）+ 预填微信 channel binding
#   9. setup-crew.sh（裸跑，无 --force；--force 只用户手动修复用；crew 模板来自 WISEFLOW_ROOT/crews，workspace 落 OPENCLAW_HOME）
#   10. camoufox-cli：npm install -g 本地 fork（ship 的 portable node）+ camoufox-cli install 下 Firefox
#   11. openclaw-weixin 插件：openclaw plugins install @tencent-weixin/openclaw-weixin@<pin> --pin（npmmirror）
#       幂等按**版本**判定：已装版本 == pin 才跳过，不等则 --force 升级到 pin
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
# 常量（atomgit 专线，硬编码）
# ═══════════════════════════════════════════════════════════════════
# 资产 URL 构造为 $XIAOBEI_ATOMGIT_MIRROR/releases/download/{tag}/xiaobei-{tag}-{plat}.{tar.zst|tar.gz}
#   - tarball 直链 host = atomgit.com（redirect 到 file-cdn.gitcode.com 签名 CDN，匿名 GET 可下，~140MB）
#   - 解 latest tag 走 api.atomgit.com/api/v5/repos/{o}/{r}/releases/latest（NOT Gitea v1，host/版本都不同）
WISEFLOW_REPO="wiseflow/xiaobei"
XIAOBEI_ATOMGIT_MIRROR="https://atomgit.com/wiseflow/xiaobei"
XIAOBEI_ATOMGIT_API="https://api.atomgit.com/api/v5/repos/wiseflow/xiaobei"
# 程序目录（引擎源码 + crew 模板 + 脚本 + portable node/pnpm + camoufox-cli fork + bin wrapper）
# 与运行数据目录 OPENCLAW_HOME（~/.openclaw：openclaw.json + daemon.env + workspace-*）分离。
# 不隐藏：用户能直接 ls 看到，符合"小白友好"。
WISEFLOW_ROOT_DEFAULT="${XIAOBEI_HOME:-$HOME/xiaobei}"
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
# atomgit 国内线路默认不拉 gum bootstrap（charmbracelet/gum 的 release 只在 GitHub，
# 国内连 GitHub 常超 75s 拖慢安装）。若机器已装 gum（brew install gum）仍会被检测使用；
# 想强制 bootstrap 走 GitHub 可 export OPENCLAW_GUM_VERSION=0.17.0。
GUM_VERSION="${OPENCLAW_GUM_VERSION:-}"
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

    # atomgit 国内线路默认不 bootstrap gum（GUM_VERSION 置空时跳下载，避免连 GitHub
    # 超时拖慢安装）。系统已装 gum 在上面 command -v 已命中。用户想强制 bootstrap 可
    # export OPENCLAW_GUM_VERSION=0.17.0。
    if [ -z "$GUM_VERSION" ]; then
        GUM_REASON="gum bootstrap disabled on atomgit route (export OPENCLAW_GUM_VERSION to enable)"
        return 1
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
        title="$("$GUM" style --foreground "#ff4d4d" --bold "wiseflow Installer (atomgit)")"
        tagline="$("$GUM" style --foreground "#8892b0" "$TAGLINE")"
        hint="$("$GUM" style --foreground "#5a6480" "modern installer mode")"
        card="$(printf '%s\n%s\n%s' "$title" "$tagline" "$hint")"
        "$GUM" style --border rounded --border-foreground "#ff4d4d" --padding "1 2" "$card"
        echo ""
        return
    fi

    echo -e "${ACCENT}${BOLD}"
    echo "  wiseflow Installer (atomgit)"
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

# 解析最新 release tag + 版本号（atomgit v5 API 专线，无 fallback）
resolve_latest_version() {
    if [[ -n "${XIAOBEI_TAG:-}" ]]; then
        XIAOBEI_VER="${XIAOBEI_TAG#v}"
        ui_success "Using pinned tag: $XIAOBEI_TAG"
        return 0
    fi
    local resp
    resp="$(curl -fsSL "$XIAOBEI_ATOMGIT_API/releases/latest" 2>/dev/null || true)"
    XIAOBEI_TAG="$(printf '%s' "$resp" | grep -oE '"tag_name"[[:space:]]*:[[:space:]]*"v[^"]+"' | head -1 | sed -E 's/.*"v([^"]+)".*/v\1/')"
    if [[ -z "$XIAOBEI_TAG" ]]; then
        ui_error "无法解析最新 release tag（atomgit v5 API）"
        echo "指定版本：export XIAOBEI_TAG=v5.5.0 后重跑"
        exit 1
    fi
    XIAOBEI_VER="${XIAOBEI_TAG#v}"
    ui_success "Latest release (via atomgit v5 API): $XIAOBEI_TAG"
}

# 构造 tarball 下载 URL（atomgit CDN 专线）
tarball_url() {
    local asset="xiaobei-${XIAOBEI_TAG}-${PLAT}.${TAR_EXT}"
    echo "$XIAOBEI_ATOMGIT_MIRROR/releases/download/$XIAOBEI_TAG/$asset"
}

download_and_extract_tarball() {
    local url; url="$(tarball_url)"
    local asset="xiaobei-${XIAOBEI_TAG}-${PLAT}.${TAR_EXT}"
    # 缓存下过的 tarball，重跑（含失败重试）免重复下 120MB。XIAOBEI_TARBALL 优先（用户自带）。
    local cache_dir="${XIAOBEI_CACHE_DIR:-$HOME/.xiaobei/cache}"
    local cached="$cache_dir/$asset"
    local tmp
    if [[ -n "${XIAOBEI_TARBALL:-}" && -f "${XIAOBEI_TARBALL:-}" ]]; then
        ui_kv "Asset" "$asset (local)"
        ui_kv "File" "$XIAOBEI_TARBALL"
        tmp="$XIAOBEI_TARBALL"
    elif [[ -f "$cached" && -s "$cached" ]]; then
        ui_kv "Asset" "$asset (cached)"
        ui_kv "File" "$cached"
        tmp="$cached"
    else
        ui_kv "Asset" "$asset"
        ui_kv "URL" "$url"
        mkdir -p "$cache_dir"
        # 原子写：先下到 .part 临时文件，成功后 rename 到 cached，
        # 避免断网留半截损坏文件导致下次重跑命中损坏缓存。
        local part="$cached.part"
        rm -f "$part"
        ui_info "Downloading $asset (~120MB, atomgit CDN) → $cached ..."
        if download_file "$url" "$part"; then
            mv -f "$part" "$cached"
            ui_success "Downloaded"
        else
            rm -f "$part"
            ui_error "下载失败：$url"
            exit 1
        fi
        tmp="$cached"
    fi

    mkdir -p "$WISEFLOW_ROOT"
    ui_info "Extracting to $WISEFLOW_ROOT ..."
    local extract_ok=1
    if [[ "$TAR_EXT" == "tar.zst" ]]; then
        tar --zstd -xf "$tmp" -C "$WISEFLOW_ROOT" || extract_ok=0
    else
        tar -xzf "$tmp" -C "$WISEFLOW_ROOT" || extract_ok=0
    fi
    if [[ "$extract_ok" -ne 1 ]]; then
        # 解压失败：缓存可能损坏/半下，删了重下一次再试（用户自带的 XIAOBEI_TARBALL 不删）
        if [[ -z "${XIAOBEI_TARBALL:-}" && -f "$cached" ]]; then
            ui_warn "解压失败，删损坏缓存重下..."
            rm -f "$cached"
            download_file "$url" "$cached"
            if [[ "$TAR_EXT" == "tar.zst" ]]; then
                tar --zstd -xf "$cached" -C "$WISEFLOW_ROOT"
            else
                tar -xzf "$cached" -C "$WISEFLOW_ROOT"
            fi
        else
            ui_error "解压失败：$tmp"
            exit 1
        fi
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
    local node_bin_dir; node_bin_dir="$(dirname "$node")"
    ui_info "pnpm install --prod --frozen-lockfile（拉依赖 + native prebuilt，~30s-2min）"
    # 把 portable node bin 前置到 PATH：esbuild/protobufjs/tlon-skill 等 postinstall
    # 跑 sh -c "node ..."，PATH 里没 node 就 command not found。本脚本卖点是无预装 Node，
    # 小白机无系统 node，必须显式前置 portable node，否则 postinstall 全挂。
    run_required_step "pnpm install --prod" \
        env PATH="$node_bin_dir:$PATH" NODE_OPTIONS="--max-old-space-size=4096" \
        "$node" "$pnpm" -C "$openclaw_dir" install --prod --frozen-lockfile \
        --registry=https://registry.npmmirror.com --fetch-retries=5 --fetch-timeout=600000 --network-concurrency=8
    ui_success "Dependencies installed"
}

# skills 的 python 依赖（扫仓内 requirements.txt，pip install --user）
# 优先高版本 python（3.12/3.11/3.10），回退 python3；小白机可能只有 CommandLineTools 的 3.9。
install_python_deps() {
    local root="$WISEFLOW_ROOT"
    local merged=""
    local f
    while IFS= read -r -d '' f; do
        merged+="$(cat "$f" 2>/dev/null)"$'\n'
    done < <(find "$root/skills" "$root/crews" "$root" -maxdepth 4 -name requirements.txt -print0 2>/dev/null)
    [[ -z "$merged" ]] && { ui_info "No requirements.txt found; skip python deps"; return 0; }
    # 选 python：优先 3.12/3.11/3.10，回退 python3
    local PY_BIN=""
    for cand in python3.12 python3.11 python3.10 python3; do
        if command -v "$cand" &>/dev/null; then PY_BIN="$cand"; break; fi
    done
    if [[ -z "$PY_BIN" ]]; then
        ui_warn "python3 未安装，跳过 python 依赖（skills 用到时再装）"
        return 0
    fi
    if ! "$PY_BIN" -m pip --version &>/dev/null; then
        ui_warn "$PY_BIN -m pip 不可用，跳过 python 依赖"
        return 0
    fi
    ui_info "Installing python skill deps via $PY_BIN (--user --break-system-packages)"
    # --no-warn-script-location 抑制 'script installed in .../bin which is not on PATH'（小白噪音）
    # --disable-pip-version-check 抑制 pip 升级提示
    # PEP 668：现代系统（Homebrew/Debian/PEP 668）下 pip install --user 仍被拒，
    # 直接加 --break-system-packages 跨过；--user 限目标目录，不碰系统 site-packages，安全。
    printf '%s' "$merged" | sort -u | grep -vE '^\s*#|^\s*$' | \
        "$PY_BIN" -m pip install --user --break-system-packages \
            --no-warn-script-location --disable-pip-version-check \
            -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
            -r /dev/stdin || \
        ui_warn "pip install 部分失败，可稍后手动补"
    ui_success "Python deps done"
}

install_deck_render() {
    local node="$WISEFLOW_ROOT/$PORTABLE_NODE"
    local node_bin_dir="$(dirname "$node")"
    local args=()
    [[ "$SKIP_BROWSER" == "true" ]] && args+=(--skip-browser)
    run_required_step "Installing deck-render runtime" \
        env PATH="$node_bin_dir:$PATH" \
        bash "$WISEFLOW_ROOT/scripts/install-deck-render.sh" "${args[@]}"
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

# 步数总数在 main 里按 is_update 动态设（首装 12 / 更新 11）；此默认仅防 ui_stage 在 main 前被调。
INSTALL_STAGE_TOTAL=11
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

is_promptable() {
    if [[ "$NO_PROMPT" == "1" ]]; then
        return 1
    fi
    if has_controlling_tty; then
        return 0
    fi
    return 1
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
    # portable node 的 npm 全局前缀指向 $WISEFLOW_ROOT，bin 落 $WISEFLOW_ROOT/bin；
    # 该目录不在默认 PATH，须显式前置，否则下一步 camoufox-cli install �报 command not found。
    export PATH="$WISEFLOW_ROOT/bin:$(dirname "$node"):$PATH"
    export npm_config_prefix="$WISEFLOW_ROOT"
    # fork 的 dist 是 tsc 编译，camoufox-js/playwright-core/pdf-lib 是 external import
    # （没打进 bundle），运行时靠 fork 目录下的 node_modules 解析。
    # tarball 为瘦身 ship 的 fork 不带 node_modules，npm install -g <目录> 又是 symlink
    # 到源目录（非 copy），所以必须先在 fork 目录装运行时依赖，否则 bin 跑起来 ERR_MODULE_NOT_FOUND。
    if command -v camoufox-cli >/dev/null 2>&1 && [ -d "$fork_dir/node_modules/camoufox-js" ]; then
        ui_success "camoufox-cli already installed"
    else
        [[ -d "$fork_dir" ]] || { ui_warn "camoufox-cli fork 不在 tarball 内：${fork_dir}；跳过"; return 0; }
        run_required_step "Installing camoufox-cli fork deps" bash -c "cd '$fork_dir' && '$npm_bin' install --omit=dev --registry=https://registry.npmmirror.com"
        run_required_step "Installing camoufox-cli fork (local)" "$npm_bin" install -g "$fork_dir" --registry=https://registry.npmmirror.com
    fi
    # npm install -g 基的 bin 可能缺 +x（symlink 目标权限没带过来），直接调会 Permission denied。
    # chmod +x 跟随 symlink 改目标权限（macOS/Linux 一致）。
    local cbin="$WISEFLOW_ROOT/bin/camoufox-cli"
    [[ -e "$cbin" ]] && chmod +x "$cbin" 2>/dev/null || true
    ui_info "Ensuring camoufox Firefox binary (idempotent, ~557MB first run)"
    if ! camoufox-cli install; then
        ui_warn "camoufox-cli install failed; you can run it manually later: camoufox-cli install"
    fi
    ui_success "camoufox-cli ready"
}

# 读已装 openclaw-weixin 的版本号；读不到返回非零。
# 优先 `plugins list --json`（字段 id / name / version），回落到 npm projects 下实装 package.json。
weixin_installed_version() {
    local claw_cmd="$1" pkg="$2" oc_home="${OPENCLAW_HOME:-$HOME/.openclaw}"
    local v f
    v="$("$claw_cmd" plugins list --json 2>/dev/null | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for p in d.get('plugins', []):
    if p.get('id') == 'openclaw-weixin' or p.get('name') == '$pkg':
        print(p.get('version') or '')
        break
" 2>/dev/null)"
    if [[ -n "$v" ]]; then printf '%s\n' "$v"; return 0; fi
    # 回落：CLI/JSON 不可用时直接读实装 package.json（目录名带 hash，只能 glob）
    for f in "$oc_home"/npm/projects/*/node_modules/"$pkg"/package.json; do
        [[ -f "$f" ]] || continue
        v="$(python3 -c "import json;print(json.load(open('$f')).get('version',''))" 2>/dev/null)"
        if [[ -n "$v" ]]; then printf '%s\n' "$v"; return 0; fi
    done
    return 1
}

# 装 openclaw-weixin 插件（config template 已预置 channel，但插件本体要 openclaw plugins install）
# 读 tarball 内 openclaw-weixin.version.json 的 pin，走国内 npmmirror。
# 幂等：**已装版本 == pin 版本**才跳过；已装版本 ≠ pin 则 `--force` 升级到 pin。
# （旧逻辑只 grep 插件名就 return，导致 bump pin 后已装实例永远停在旧版；
#   `plugins install --force` = "Overwrite an existing installed plugin"，7.1-2 起就有该 flag。
#   升级只换 npm/projects 下的包，登录态在 $OPENCLAW_HOME/openclaw-weixin/ 数据目录，不受影响。
#   升级后需 gateway 重启才生效——更新路线在后面 refresh_gateway_env_only 里会重启。）
install_weixin_plugin() {
    local claw_cmd="$WISEFLOW_ROOT/bin/openclaw"
    local pin_file="$WISEFLOW_ROOT/openclaw-weixin.version.json"
    [[ -f "$claw_cmd" ]] || { ui_warn "openclaw wrapper 不在 ${claw_cmd}；跳过 weixin 插件"; return 0; }
    local pkg ver
    if [[ -f "$pin_file" ]]; then
        pkg=$(python3 -c "import json;print(json.load(open('$pin_file'))['openclaw-weixin']['package'])" 2>/dev/null || true)
        ver=$(python3 -c "import json;print(json.load(open('$pin_file'))['openclaw-weixin']['version'])" 2>/dev/null || true)
    fi
    pkg="${pkg:-@tencent-weixin/openclaw-weixin}"
    ver="${ver:-2.4.8}"
    # 幂等检查：已装版本 == pin 才跳过
    local installed force_flag=""
    installed="$(weixin_installed_version "$claw_cmd" "$pkg" || true)"
    if [[ -n "$installed" && "$installed" == "$ver" ]]; then
        ui_success "openclaw-weixin plugin already installed (${ver})"
        return 0
    fi
    if [[ -n "$installed" ]]; then
        ui_info "openclaw-weixin 已装 ${installed}，pin=${ver} → --force 升级"
        force_flag="--force"
    elif "$claw_cmd" plugins list 2>/dev/null | grep -q "openclaw-weixin"; then
        # 插件在但版本读不到（CLI/JSON 异常）：按 pin 强制重装，保证与 pin 一致
        ui_warn "openclaw-weixin 已装但版本读不到；按 pin ${ver} 强制重装"
        force_flag="--force"
    fi
    ui_info "Installing openclaw-weixin plugin (${pkg}@${ver}) via npmmirror"
    if npm_config_registry=https://registry.npmmirror.com "$claw_cmd" plugins install "${pkg}@${ver}" --pin $force_flag 2>/dev/null; then
        ui_success "openclaw-weixin plugin installed (${ver})"
    else
        ui_warn "openclaw-weixin 插件安装失败；可后续手动：npm_config_registry=https://registry.npmmirror.com $claw_cmd plugins install ${pkg}@${ver} --pin $force_flag"
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
    [[ -d "$awada_dir" ]] || { ui_warn "awada 不在 tarball 内：${awada_dir}；跳过"; return 0; }
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

# 放置 config template → ~/.openclaw/openclaw.json（已预置 awk provider，apiKey=${AWK_API_KEY} 由 gateway env 注入；
# plugins.load.paths 里的 ${XIAOBEI_HOME}/awada 在放置后由本函数直接解析成绝对路径写回，不依赖运行时 env）
# 健康判定：现有 config 必须同时有 models + agents.defaults，否则视为被极简化（openclaw 首启自动生成
# 的最小 config 缺这两块），用 template 覆盖。这样首装 / 重跑 / 更新路线都能自愈极简 config。
place_config_template() {
    # bash 3.2（macOS 自带 /bin/bash）在 set -eu 下对 `local a=1 b="" c=""`（多变量一行 local）
    # 有已知坑：只绑第一个变量，后续变量在 set -u 下报 unbound。故这里每个变量单独 local 声明、
    # 再用纯赋值预绑，且引用时一律 ${var} 加花括号（避免后接全角字符被 C locale 渲染成 `?` 误判）。
    local openclaw_home
    local config_path
    local tmpl
    local need_place
    local reason
    local backup
    openclaw_home="${OPENCLAW_HOME:-$HOME/.openclaw}"
    config_path="${OPENCLAW_CONFIG_PATH:-$openclaw_home/openclaw.json}"
    tmpl="$WISEFLOW_ROOT/config-templates/openclaw.json"
    need_place=0
    reason=""
    backup=""
    mkdir -p "$openclaw_home"
    if [[ ! -f "$tmpl" ]]; then
        ui_error "config template 缺失: ${tmpl} (tarball 损坏?)"
        return 1
    fi
    if [[ ! -f "$config_path" ]]; then
        need_place=1
        reason="不存在"
    elif [[ "$FORCE_RUNTIME" == "true" ]]; then
        need_place=1
        reason="--force"
    else
        # 现有 config 存在——检查是否健康（有 models + agents.defaults）
        if "$WISEFLOW_ROOT/$PORTABLE_NODE" -e '
            const fs=require("fs");
            const c=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));
            process.exit(c.models && c.agents && c.agents.defaults ? 0 : 1);
        ' "$config_path" 2>/dev/null; then
            need_place=0
        else
            need_place=1
            reason="缺 models/agents.defaults (疑似被极简化)"
        fi
    fi
    if [[ "$need_place" == "1" ]]; then
        if [[ -f "$config_path" ]]; then
            backup="${config_path}.bak.$$.${RANDOM:-0}"
            cp "$config_path" "$backup"
            ui_warn "openclaw.json ${reason} -> 用 template 覆盖 (旧文件备份到 ${backup})"
        else
            ui_info "Placing openclaw.json template (${reason})"
        fi
        cp "$tmpl" "$config_path"
        ui_success "Placed openclaw.json template"
    else
        ui_info "openclaw.json 已存在且健康 (有 models + agents.defaults), 保留"
    fi
    # 把 plugins.load.paths 里的 ${XIAOBEI_HOME} env ref 直接解析成绝对路径写回 config。
    # 原因：openclaw 在 CLI 上下文（daemon install / doctor / status / 用户裸跑 openclaw）校验
    # config 时用的是当前 shell env，未必有 XIAOBEI_HOME → ${XIAOBEI_HOME}/awada 不展开 →
    # "plugin path not found" 误报。awada 位置在 install 时已知（$WISEFLOW_ROOT/awada），
    # 直接写死绝对路径，daemon / CLI / 裸终端所有上下文都能解析。AWK_API_KEY 是 secret，
    # 保持 ${AWK_API_KEY} env ref 不写死（写死会让 key 落盘明文 + 进 .bak 备份 + doctor 可见）。
    # 幂等：已是绝对路径则 no-op。更新路线也跑（修老 config 里残留的 ${XIAOBEI_HOME} ref）。
    if ! "$WISEFLOW_ROOT/$PORTABLE_NODE" -e '
        const fs=require("fs");
        const p=process.argv[1], root=process.argv[2];
        const c=JSON.parse(fs.readFileSync(p,"utf8"));
        const paths=(c.plugins?.load?.paths) || [];
        let changed=false;
        const fixed=paths.map(s => {
            if (typeof s==="string" && s.indexOf("${XIAOBEI_HOME}")!==-1) {
                changed=true;
                return s.split("${XIAOBEI_HOME}").join(root);
            }
            return s;
        });
        if (changed) {
            c.plugins.load.paths=fixed;
            fs.writeFileSync(p, JSON.stringify(c,null,2)+"\n");
        }
    ' "$config_path" "$WISEFLOW_ROOT" 2>/dev/null; then
        ui_warn "plugins.load.paths 路径解析失败 (非致命, config 仍可用, 但 awada 可能加载不到)"
    fi
}

# ═══════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════
WISEFLOW_ROOT="${WISEFLOW_ROOT:-$WISEFLOW_ROOT_DEFAULT}"
# 运行数据目录（openclaw.json / daemon.env / workspace-*）；本脚本内部统一用 OPENCLAW_HOME 指代。
# 注意：openclaw 引擎的 resolveStateDir 把 $OPENCLAW_HOME 当 HOME 根再 append /.openclaw
# （见 openclaw/src/config/paths.ts resolveStateDir → newStateDir = homedir/.openclaw），
# 故若 export OPENCLAW_HOME=~/.openclaw 给引擎，会产出 ~/.openclaw/.openclaw 崌套。
# 正确做法：export OPENCLAW_STATE_DIR（引擎用作 state dir 直接覆盖，不 append），OPENCLAW_HOME 仅本脚本内部用、不外传。
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
export OPENCLAW_STATE_DIR="$OPENCLAW_HOME"
VERBOSE=0
NO_PROMPT=0
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
            --)
                # 选项/位置参数分隔符（README 的 `bash -c "..." -s -- --verbose` 会把 -- 透传进来）
                shift
                ;;
            --help|-h)
                cat <<EOF
wiseflow installer (macOS + Linux, atomgit 专线) — 预构建 tarball 路线

Usage:
  bash -c "\$(curl -fsSL https://raw.atomgit.com/wiseflow/xiaobei/raw/master/scripts/install-atomgit.sh)"
  bash -c "\$(curl -fsSL https://raw.atomgit.com/wiseflow/xiaobei/raw/master/scripts/install-atomgit.sh)" -s -- [options]

Options:
  --root <dir>       Program install directory (default: ~/xiaobei; runtime data stays in ~/.openclaw)
  --force            Overwrite existing runtime data (~/.openclaw); default preserves it on re-install
  --skip-bind        Skip the WeChat QR binding at the end (CI/automation)
  --skip-browser     Skip Camoufox Firefox and deck-render Chromium downloads (smoke/CI)
  --verbose          Print debug output
  --no-prompt        Disable prompts (CI/automation)
  --help, -h         Show this help

Env:
  XIAOBEI_TAG        指定版本 tag（默认拉最新 release via atomgit v5 API）
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
    # accounts.json 落 state dir（OPENCLAW_STATE_DIR=~/.openclaw，引擎不再嵌套 /.openclaw）
    local acc="$OPENCLAW_HOME/openclaw-weixin/accounts.json"
    [[ -f "$acc" ]] && return 0
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
        ui_warn "openclaw wrapper 未找到（${claw}），跳过微信绑定"
        return 0
    fi
    # 不用 ui_stage（会递增计数器致超出总数）；用 ui_section 出独立标题。
    ui_section "绑定微信 channel（用手机扫码）"
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
    ui_kv "Repo" "$WISEFLOW_REPO (atomgit)"
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

    # 步数总数按路线动态设：首装 12 步（含 config/crew/gateway），更新 11 步（自愈 config + 刷 program+restart）。
    if [[ "$is_update" == "true" ]]; then
        INSTALL_STAGE_TOTAL=11
    else
        INSTALL_STAGE_TOTAL=12
    fi

    # 更新路线：先停 gateway。否则 pnpm install --prod 重写 node_modules 时与运行中的 gateway
    # 文件句柄竞争，macOS 上可卡几十分钟（EBUSY 重试）。末尾 refresh_gateway_env_only 会重启。
    if [[ "$is_update" == "true" ]]; then
        stop_gateway_if_running
    fi

    # ─── Step 1: 平台 + 版本 ────────────────────────────────
    ui_stage "Detecting platform"
    detect_platform_asset
    ui_stage "Resolving latest release (atomgit v5 API)"
    resolve_latest_version

    # ─── Step 2: 下载 + 解压 tarball（更新 program）──────────
    ui_stage "Downloading pre-built tarball (atomgit CDN)"
    download_and_extract_tarball

    # ─── Step 3: pnpm install --prod（拉依赖，无 OOM）────────
    ui_stage "Installing dependencies (pnpm install --prod)"
    pnpm_install_prod
    run_required_step "Installing per-skill Node.js dependencies" \
        env PATH="$WISEFLOW_ROOT/tools/node/bin:$PATH" \
        "$WISEFLOW_ROOT/$PORTABLE_NODE" "$WISEFLOW_ROOT/scripts/install-skill-deps.mjs" \
        --root "$WISEFLOW_ROOT" --state-dir "$OPENCLAW_HOME" \
        --npm-cli "$WISEFLOW_ROOT/tools/node/lib/node_modules/npm/bin/npm-cli.js"

    # ─── Step 4: python skill deps ───────────────────────────
    ui_stage "Installing python skill deps"
    install_python_deps

    # ─── Step 5: awada 本地插件 deps（幂等）──────────────────
    ui_stage "Installing awada plugin deps"
    install_awada_plugin

    # ─── Step 6: HyperFrames + Playwright Chromium + CJK 字体 ──
    ui_stage "Installing deck-render runtime"
    install_deck_render

    # ─── Step 7: camoufox-cli + Firefox binary（幂等）────────
    ui_stage "Installing camoufox-cli browser"
    install_camoufox_cli

    # ─── Step 8: openclaw-weixin 插件（幂等）─────────────────
    ui_stage "Installing WeChat plugin"
    install_weixin_plugin

    if [[ "$is_update" == "true" ]]; then
        # ─── 更新路线：先自愈 config（若被极简化），再刷 gateway env 路径 + restart ──
        # 不碰运行数据（daemon.env 的 key / workspace 不动），但 openclaw.json 若缺 models/agents.defaults
        # （openclaw 首启自动生成的极简 config）则用 template 覆盖，否则更新路线永远修不回完整 config。
        ui_stage "Checking config health"
        place_config_template
        ui_stage "Refreshing gateway env and restarting"
        refresh_gateway_env_only
    else
        # ─── 首装路线：放 config + setup-crew + gateway daemon ──
        # config-templates/openclaw.json 已预置 channels.openclaw-weixin.enabled=true
        # + plugins.entries.openclaw-weixin.enabled=true + bindings + session.dmScope，
        # 故不再运行时 mutate（曾因此把 plugins 顶层写坏致 "Invalid input"）。
        ui_stage "Placing config template"
        place_config_template

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
}

# ═══════════════════════════════════════════════════════════════════
# 不走 openclaw onboard（对小白太复杂）。改为：
# 1. 交互问 AWK_API_KEY（config_template 里 awk.apiKey=${AWK_API_KEY}）
# 2. 写进 gateway env 文件（Linux: daemon.env / Darwin: service-env/ai.openclaw.gateway.env）
# 3. openclaw daemon install + restart，gateway 起来后 config 能解析到 key
# 平台分支复用 c441220 经验：Linux 先写 env+drop-in 再 install（避免 StartLimitBurst）；
# Darwin 先 install（创建 env 文件）再追加。
# ═══════════════════════════════════════════════════════════════════
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
# $1: env 文件路径   $2: kv（KEY=value）或 export（export KEY='value'）
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

# 确保 env 文件的 PATH 含 node bin + program bin（openclaw 启动器）+ wrapper bin
# （~/.openclaw/bin，skill-wrappers.sh 暴露的技能软链）。gateway 是 systemd/launchd 服务，
# 不 source shell rc；agent exec 调裸技能名（如 `aigc-video-gen`）靠 PATH 解析 wrapper 软链，
# 故三者 daemon.env PATH 缺一不可。幂等：仅当三者均已就位才跳过。
ensure_env_path() {
    local env_file="$1" node_bin_dir="$2" oc_bin_dir="$3" wrapper_bin_dir="${4:-}"
    [ -f "$env_file" ] || return 0
    local need="${node_bin_dir}:${oc_bin_dir}"
    [ -n "$wrapper_bin_dir" ] && need="${need}:${wrapper_bin_dir}"
    local cur; cur="$(grep -E '^PATH=' "$env_file" | tail -n1 | sed -E 's/^PATH=//' || true)"
    if [ -z "$cur" ]; then
        printf 'PATH=%s:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n' "$need" >> "$env_file"
        return 0
    fi
    # 三者都已就位才跳过（旧逻辑只查 node_bin_dir，会漏补 wrapper bin）
    local d all_present=1
    for d in "$node_bin_dir" "$oc_bin_dir" "$wrapper_bin_dir"; do
        [ -n "$d" ] || continue
        case ":$cur:" in *":$d:"*) ;; *) all_present=0 ;; esac
    done
    [ "$all_present" -eq 1 ] && return 0
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

# 把 OPENCLAW_STATE_DIR 幂等写进 gateway env 文件。gateway 是独立进程（systemd/launchd），
# 不继承本脚本 export 的环境；不写进去则 gateway 走默认 homedir/.openclaw（多数情况也对，
# 但 HOME 异常或 daemon install 捕获了别的 OPENCLAW_HOME 时会偏）。显式写入消除歧义，
# 引擎 resolveStateDir 把 OPENCLAW_STATE_DIR 当直接覆盖、不 append /.openclaw。
# $1: env 文件路径   $2: format（kv 或 export）
ensure_env_state_dir() {
    local env_file="$1" format="$2"
    [ -f "$env_file" ] || return 0
    if [ "$format" = "export" ]; then
        grep -qE "^export OPENCLAW_STATE_DIR=" "$env_file" 2>/dev/null && return 0
        printf "export OPENCLAW_STATE_DIR='%s'\n" "$OPENCLAW_HOME" >> "$env_file"
    else
        grep -qE "^OPENCLAW_STATE_DIR=" "$env_file" 2>/dev/null && return 0
        printf 'OPENCLAW_STATE_DIR=%s\n' "$OPENCLAW_HOME" >> "$env_file"
    fi
}

# 把刚写进 env 文件的 AWK_API_KEY + XIAOBEI_HOME 加载进当前 install shell，让后续 openclaw
# CLI 调用（daemon install / gateway restart / channels login）校验 config 时能解析到，
# 避免 "missing env var AWK_API_KEY / XIAOBEI_HOME" 误报。daemon 自己经 env-file wrapper
# 也能拿到（launchd wrapper 在 exec 前 . env_file），这里纯粹为 install 期间 CLI 上下文。
# 不写进用户 shell rc（secret 不落明文 rc）；用户裸跑 openclaw 仍可能 warn，属 env-ref 固有。
# $1: env 文件路径
load_env_vars_for_cli() {
    local env_file="$1" _awk=""
    [ -f "$env_file" ] || return 0
    export XIAOBEI_HOME="$WISEFLOW_ROOT"
    _awk="$(grep -E "^(export )?AWK_API_KEY=" "$env_file" 2>/dev/null | tail -n1 || true)"
    _awk="${_awk#export }"
    _awk="${_awk#AWK_API_KEY=}"
    _awk="$(printf '%s' "$_awk" | tr -d "'")"
    if [ -n "$_awk" ]; then export AWK_API_KEY="$_awk"; fi
}

# Linux：确保 30-wait-display.conf drop-in 存在（幂等）。
# 背景：gateway 随 default.target 开机即启，早于桌面会话把 DISPLAY 登记进 user manager
# 环境（systemd 不回填已运行服务）-> 重启机器后到下次 gateway 重启之间，整个 gateway
# 进程树（agent exec、camoufox daemon）都缺 DISPLAY，agent 误判无头环境、有头浏览器
# 无法启动。drop-in 让 gateway 启动前等 DISPLAY 出现：有桌面几秒内等到（检查本身毫秒级），
# 无桌面 30s 超时放行（行为与不加一致）。openclaw 升级重写主 unit 不清 drop-in。
# WSL2 场景不走此 drop-in（WSLg 恒定提供 :0，由使用方直接注 DISPLAY 进 daemon.env）。
ensure_systemd_wait_display_dropin() {
    [ "$(uname -s)" = "Linux" ] || return 0
    command -v systemctl >/dev/null 2>&1 || return 0
    systemctl --user show-environment >/dev/null 2>&1 || return 0
    grep -qi microsoft /proc/version 2>/dev/null && return 0
    local svc="openclaw-gateway"
    local dropin_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/${svc}.service.d"
    mkdir -p "$dropin_dir"
    cat > "${dropin_dir}/30-wait-display.conf" <<'DROPIN_EOF'
[Service]
ExecStartPre=/bin/sh -c 'i=0; while [ "$i" -lt 30 ]; do systemctl --user show-environment | grep -q "^DISPLAY=" && exit 0; sleep 1; i=$((i+1)); done; exit 0'
DROPIN_EOF
    ui_success "systemd wait-display drop-in ensured (${dropin_dir}/30-wait-display.conf)"
}

# 停掉运行中的 gateway（更新路线开头调，避免 pnpm 重写 node_modules 时文件句柄竞争卡死）。
# 平台分支：Linux systemctl --user stop；Darwin openclaw gateway stop。无 service / 未运行则静默。
stop_gateway_if_running() {
    local claw_cmd="$WISEFLOW_ROOT/bin/openclaw"
    if [ "$(uname -s)" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
        systemctl --user stop "openclaw-gateway.service" 2>/dev/null && ui_info "Stopped gateway before update" || true
    elif [ "$(uname -s)" = "Darwin" ] && [ -x "$claw_cmd" ]; then
        "$claw_cmd" gateway stop 2>/dev/null && ui_info "Stopped gateway before update" || true
    fi
}

# 更新路线用：不问 AWK_API_KEY、不 daemon install，只幂等刷 gateway env 路径
# （PATH + XIAOBEI_HOME/OPENCLAW_STATE_DIR 走 .env 业务变量）+ restart gateway 让新 program 生效。
# env 分工对齐首装：业务变量在 .env，daemon.env 只放 3 固定值 + OPENCLAW_STATE_DIR + PATH。
refresh_gateway_env_only() {
    local claw_cmd="$WISEFLOW_ROOT/bin/openclaw"
    local node_bin_dir; node_bin_dir="$(dirname "$WISEFLOW_ROOT/$PORTABLE_NODE")"
    local oc_bin_dir="$WISEFLOW_ROOT/bin"
    local dot_env="$OPENCLAW_HOME/.env"
    local systemd_env="$OPENCLAW_HOME/daemon.env"
    local macos_env="$OPENCLAW_HOME/service-env/ai.openclaw.gateway.env"

    # 刷 .env 业务变量（XIAOBEI_HOME / OPENCLAW_STATE_DIR），幂等
    if [ -f "$dot_env" ]; then
        grep -vE "^export (XIAOBEI_HOME|OPENCLAW_STATE_DIR)=" "$dot_env" 2>/dev/null > "${dot_env}.new" || true
        mv "${dot_env}.new" "$dot_env"
        {
            printf "export XIAOBEI_HOME='%s'\n" "${WISEFLOW_ROOT//\'/\'\\\'\'}"
            printf "export OPENCLAW_STATE_DIR='%s'\n" "${OPENCLAW_HOME//\'/\'\\\'\'}"
        } >> "$dot_env"
        chmod 600 "$dot_env"
        load_env_vars_for_cli "$dot_env"
        ui_success ".env business vars refreshed"
    else
        ui_warn ".env 不存在（跳过业务变量刷）"
    fi

    # daemon.env 只刷 PATH + OPENCLAW_STATE_DIR（固定值不变），幂等
    local daemon_env_file
    if [ "$(uname -s)" = "Darwin" ]; then daemon_env_file="$macos_env"; else daemon_env_file="$systemd_env"; fi
    if [ -f "$daemon_env_file" ]; then
        ensure_env_path "$daemon_env_file" "$node_bin_dir" "$oc_bin_dir" "$OPENCLAW_HOME/bin"
        grep -vE "^OPENCLAW_STATE_DIR=" "$daemon_env_file" 2>/dev/null > "${daemon_env_file}.new" || true
        mv "${daemon_env_file}.new" "$daemon_env_file"
        printf 'OPENCLAW_STATE_DIR=%s\n' "$OPENCLAW_HOME" >> "$daemon_env_file"
        if [ "$(uname -s)" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
            ensure_systemd_wait_display_dropin
            systemctl --user daemon-reload 2>/dev/null || true
            systemctl --user restart "openclaw-gateway.service" 2>/dev/null && ui_success "Restarted gateway"
        elif [ "$(uname -s)" = "Darwin" ]; then
            "$claw_cmd" gateway restart 2>/dev/null && ui_success "Restarted gateway"
        fi
    else
        ui_info "无 daemon.env 或平台不支持自动 restart；可手动：$claw_cmd gateway restart"
    fi
    ui_success "Gateway env refreshed"
}

install_gateway_and_env() {
    local claw_cmd="$WISEFLOW_ROOT/bin/openclaw"
    local node_bin_dir; node_bin_dir="$(dirname "$WISEFLOW_ROOT/$PORTABLE_NODE")"
    local oc_bin_dir="$WISEFLOW_ROOT/bin"
    # env 分工（对齐 ps1 + 上游踩坑经验）：
    #   ~/.openclaw/.env        ← 业务变量（AWK_API_KEY/XIAOBEI_HOME/OPENCLAW_STATE_DIR），CLI 裸跑用
    #   ~/.openclaw/daemon.env  ← gateway service 用，只放 3 固定值 + OPENCLAW_STATE_DIR
    # 原因：Linux systemd EnvironmentFile= 对含特殊字符的业务变量（PATH 带分号、AWK 带连字符）
    # 有踩坑历史，业务变量挪 .env 让 systemd 只加载稳的固定值。daemon.env 仍走 systemd drop-in。
    # macOS launchd wrapper 走 `. env_file` source，没这个坑，但为风格统一照此分工（业务变量也在 .env）。
    local dot_env="$OPENCLAW_HOME/.env"
    local systemd_env="$OPENCLAW_HOME/daemon.env"
    local macos_env="$OPENCLAW_HOME/service-env/ai.openclaw.gateway.env"

    # ─── 提示用户清掉错误的 OPENCLAW_HOME 环境变量 ─────────────
    # 引擎 resolveStateDir 把 OPENCLAW_HOME 当 homedir 再 append /.openclaw（见
    # openclaw/src/config/paths.ts），故若用户 shell export 了 OPENCLAW_HOME=~/.openclaw，
    # 会产出嵌套路径。本脚本顶部已把 OPENCLAW_HOME 设成内部变量且未 export，不会传给引擎子进程，
    # 所以这里只打 info 提示用户清理 shell 环境变量，不能 unset——unset 会误伤脚本内部变量，
    # 导致后续 ${OPENCLAW_HOME//...} 在 set -u 下报 unbound variable。
    if [ -n "${OPENCLAW_HOME:-}" ] && [ "$(cd "${OPENCLAW_HOME:-}" && pwd)" = "$(cd "$HOME/.openclaw" && pwd)" ]; then
        ui_info "检测到 shell 里 export OPENCLAW_HOME=${OPENCLAW_HOME:-}（不影响本次安装，但建议清掉避免引擎嵌套）"
    fi

    # redirect stdin from /dev/tty so interactive read 工作于 curl|bash
    if is_promptable; then exec </dev/tty; fi

    # ─── 写 .env（业务变量，export 格式，CLI 裸跑用）──────────
    # 幂等：先剥同 key 旧行再追加。AWK_API_KEY 是 secret，单引号裹 + '\'' 转义内置单引号。
    mkdir -p "$(dirname "$dot_env")"
    [ -f "$dot_env" ] || touch "$dot_env"
    chmod 600 "$dot_env"
    # 剥同 key 旧行
    grep -vE "^export (AWK_API_KEY|XIAOBEI_HOME|OPENCLAW_STATE_DIR)=" "$dot_env" 2>/dev/null > "${dot_env}.new" || true
    mv "${dot_env}.new" "$dot_env"
    # 追加业务变量
    {
        if [ -n "${AWK_API_KEY:-}" ] || is_promptable; then
            local _awk="${AWK_API_KEY:-}"
            if [ -z "$_awk" ] && is_promptable; then
                _awk="$(prompt_env_value AWK_API_KEY "" "")"
            fi
            _awk="$(printf '%s' "$_awk" | tr -d '[:space:]')"
            if [ -n "$_awk" ]; then
                printf "export AWK_API_KEY='%s'\n" "${_awk//\'/\'\\\'\'}"
            fi
        fi
        printf "export XIAOBEI_HOME='%s'\n" "${WISEFLOW_ROOT//\'/\'\\\'\'}"
        printf "export OPENCLAW_STATE_DIR='%s'\n" "${OPENCLAW_HOME//\'/\'\\\'\'}"
    } >> "$dot_env"
    chmod 600 "$dot_env"
    ui_success ".env written (业务变量，CLI 裸跑用)"

    # ─── 写 daemon.env（gateway service 用，只放 3 固定值 + OPENCLAW_STATE_DIR）──
    # Linux 走 systemd EnvironmentFile=，只放 systemd 加载稳的固定值。
    # macOS 走 launchd wrapper `. env_file` source，没格式坑，但为风格统一照此分工。
    local daemon_env_file
    if [ "$(uname -s)" = "Darwin" ]; then
        daemon_env_file="$macos_env"
        mkdir -p "$(dirname "$daemon_env_file")"
    else
        daemon_env_file="$systemd_env"
        mkdir -p "$(dirname "$daemon_env_file")"
    fi
    [ -f "$daemon_env_file" ] || touch "$daemon_env_file"
    chmod 600 "$daemon_env_file"
    # 剥同 key 旧行
    grep -vE "^(OPENCLAW_BROWSER_TIMEOUT_MS|OPENCLAW_DISABLE_BONJOUR|PATH|OPENCLAW_STATE_DIR)=" "$daemon_env_file" 2>/dev/null > "${daemon_env_file}.new" || true
    mv "${daemon_env_file}.new" "$daemon_env_file"
    # 追加固定值
    {
        printf 'OPENCLAW_BROWSER_TIMEOUT_MS=90000\n'
        printf 'OPENCLAW_DISABLE_BONJOUR=true\n'
        printf 'OPENCLAW_STATE_DIR=%s\n' "$OPENCLAW_HOME"
    } >> "$daemon_env_file"
    chmod 600 "$daemon_env_file"
    ensure_env_path "$daemon_env_file" "$node_bin_dir" "$oc_bin_dir" "$OPENCLAW_HOME/bin"
    ui_success "daemon.env written (gateway service 用，3 固定值 + PATH + OPENCLAW_STATE_DIR)"

    # 把 .env 业务变量加载进当前 install shell，让后续 daemon install / gateway restart / channels login
    # 校验 config 时能解析到 AWK_API_KEY / XIAOBEI_HOME（CLI 裸跑本会 . .env，install shell 也得有）
    load_env_vars_for_cli "$dot_env"

    # ─── daemon install（平台分支）─────────────────────────
    if [ "$(uname -s)" = "Linux" ]; then
        # systemd drop-in 引用 daemon.env（必须在 daemon install 之前）
        if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
            local svc="openclaw-gateway"
            local dropin_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/${svc}.service.d"
            mkdir -p "$dropin_dir"
            printf '[Service]\nEnvironmentFile=-%s\n' "$systemd_env" > "${dropin_dir}/10-env-file.conf"
            ensure_systemd_wait_display_dropin
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
        "$claw_cmd" gateway restart 2>/dev/null || true
        ui_success "Restarted gateway with macos env"
    else
        ui_warn "Unsupported platform for daemon install; run manually: $claw_cmd daemon install"
    fi
    ui_success "Gateway configured"
}

if [[ "${WISEFLOW_INSTALL_SH_NO_RUN:-0}" != "1" ]]; then
    main "$@"
fi
