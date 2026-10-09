#!/usr/bin/env bash
# docker-bootstrap.sh — 构建镜像的 immutable 应用层（等价于"跑完 install.sh 装好后"状态）
#
# 与裸机 install.sh 区别：
#   - 不拉远程仓库（openclaw 源码已由 Dockerfile COPY 进来）
#   - 不跑 daemon install / 不交互收密钥（容器无 systemd，密钥走运行时环境变量）
#   - 不重启 gateway（构建阶段没运行实例）
#
# 复用裸机安装的同一套底层脚本，保证 patch / skills / wrappers / 依赖 / 编译语义与裸机同源：
#   - patches/camoufox-cli/build.sh         反指纹浏览器 CLI fork
#   - scripts/apply-addons.sh               patch 应用 + skills + crew workspace + 编译
#   - scripts/setup-crew.sh                 crew workspace 初始化（由 apply-addons 内部触发）
#   - weixin 插件在线 plugins install        （逻辑内联在此，不调独立的 install-weixin-channel.sh）
#
# 诊断：每步打 [bootstrap] STEP N done 标记，ACR 构建失败时精确定位哪步炸。
# 容错：非致命步骤（camoufox 二进制、weixin 插件）失败不中断构建——首启可手动补。
# 不用 set -u：buildkit 可能吞 stderr，unbound 错误走 stderr 会被吃掉变成静默 exit 1。
# 用显式检查 + set -o pipefail 控制致命步。
set -o pipefail

log() {
  echo "[bootstrap] $*" >&2
  echo "[bootstrap] $*" >> /opt/xiaobei/.bootstrap-log
}

# 首行无条件打印——证明脚本能跑起来（不依赖任何变量）
# ACR buildkit 不显示 RUN 步骤的 stdout/stderr，诊断标记同时写 /opt/xiaobei/.bootstrap-log
# 文件——Dockerfile 在 bootstrap RUN 后加独立 cat 步骤显示该文件（cat 步骤的 stdout
# buildkit 会显示）
: > /opt/xiaobei/.bootstrap-log 2>/dev/null || true
log "=== docker-bootstrap.sh started ==="
log "pwd=$(pwd) HOME=${HOME:-unset}"

PROJECT_ROOT="${XIAOBEI_ROOT:-/opt/xiaobei}"
OPENCLAW_HOME="${OPENCLAW_HOME:-/root/.openclaw}"
OPENCLAW_CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-$OPENCLAW_HOME/openclaw.json}"
# 显式标记 Docker 部署环境——setup-crew.sh 依赖此变量生成正确的 OFB_ENV.md
# （/.dockerenv 在 build stage 基础镜像里不存在，不可靠）
export WISEFLOW_DOCKER=1
log "PROJECT_ROOT=$PROJECT_ROOT OPENCLAW_HOME=$OPENCLAW_HOME"

# 走镜像源（与裸机 install.sh 链路同源）：registry 由 Dockerfile ARG NPM_REGISTRY
# 透传进 ENV NPM_CONFIG_REGISTRY，海外 arm64 runner override 成 npmjs 不跨境。
# bootstrap 内显式 export 让子进程（camoufox-cli/build.sh 的 npm install、
# apply-addons.sh 的 pnpm install、plugins install）都走同一 registry。
export npm_config_registry="${NPM_CONFIG_REGISTRY:-https://registry.npmmirror.com}"
log "npm_config_registry=$npm_config_registry"

# ─── 校验源码树（致命）────────────────────────────────────────────
[ -d "$PROJECT_ROOT/openclaw/.git" ] || { log "❌ openclaw 源码树缺 .git"; exit 1; }
[ -x "$PROJECT_ROOT/scripts/apply-addons.sh" ] || { log "❌ apply-addons.sh 缺失"; exit 1; }

mkdir -p "$OPENCLAW_HOME"

# ─── 放置 config template ────────────────────────────────────────
cp "$PROJECT_ROOT/config-templates/openclaw.json" "$OPENCLAW_CONFIG_PATH"
cp "$PROJECT_ROOT/config/daemon.env.template" "$OPENCLAW_HOME/daemon.env"
cp "$PROJECT_ROOT/config/.env.template" "$OPENCLAW_HOME/.env"
chmod 600 "$OPENCLAW_HOME/daemon.env" "$OPENCLAW_HOME/.env"

# template 内 ${XIAOBEI_HOME} 解析成容器内固定路径写回
node -e '
    const fs = require("fs");
    const p = process.argv[1];
    let raw = fs.readFileSync(p, "utf8");
    raw = raw.replace(/\$\{XIAOBEI_HOME\}/g, "/opt/xiaobei");
    fs.writeFileSync(p, raw);
' "$OPENCLAW_CONFIG_PATH"
log "STEP 1 done: config template placed"

# ─── camoufox-cli fork 构建 + 全局安装（致命：browser-guide 依赖）────
log "STEP 2: building camoufox-cli fork..."
if ! "$PROJECT_ROOT/patches/camoufox-cli/build.sh"; then
  log "❌ camoufox-cli build failed"
  exit 1
fi
log "STEP 2 done: camoufox-cli fork built + installed globally"

# ─── apply-addons：patch + skills + crew + 编译（致命）────────────
log "STEP 3: applying addons (patches + skills + crews + build)..."
if ! "$PROJECT_ROOT/scripts/apply-addons.sh" --force --no-restart; then
  log "❌ apply-addons.sh failed"
  exit 1
fi
log "STEP 3 done: addons applied + openclaw built"

# ─── deck-render: pinned npm packages, Chromium shell and CJK font ───
# The browser is stored under /opt/xiaobei, so the runtime stage COPY includes it.
log "STEP 3.5: installing deck-render runtime..."
if ! "$PROJECT_ROOT/scripts/install-deck-render.sh"; then
  log "❌ deck-render runtime install failed"
  exit 1
fi
log "STEP 3.5 done: deck-render ready"

# ─── camoufox-cli install：拉 Firefox 二进制（非致命，首启可补）────
# 幂等：已装且版本一致时打印 "already up to date" 并返回
#
# camoufox-js 的 INSTALL_DIR 默认 ~/.cache/camoufox（Linux XDG 缓存路径）。
# 这里显式设 CAMOUFOX_INSTALL_DIR=/root/.camoufox-cli，让浏览器二进制装进
# 与 entrypoint volume 一致的目录——stage-2 COPY 和运行时 volume 都指向这里，
# 装到别处会导致镜像层拷不出来 + 运行时 volume 找不到浏览器。
# 先 mkdir -p 确保目录存在（install 失败时 stage-2 COPY 也不会因源缺失炸掉）。
export CAMOUFOX_INSTALL_DIR="${CAMOUFOX_INSTALL_DIR:-/root/.camoufox-cli}"
install -d -m 700 "$CAMOUFOX_INSTALL_DIR"
log "STEP 4: ensuring camoufox Firefox binary (CAMOUFOX_INSTALL_DIR=$CAMOUFOX_INSTALL_DIR)..."
camoufox-cli install || log "⚠️ camoufox-cli install failed（可后续手动 camoufox-cli install）"
log "STEP 4 done"

# ─── 预装 openclaw-weixin 插件（非致命，首启可补）────────────────
# 与裸机 install.sh 的 install_weixin_plugin() 同源：读 pin 走在线 plugins install
# 幂等：**已装版本 == pin 版本**才跳过；不等则 --force 升级到 pin。
# 容器里 /root/.openclaw 是持久卷，镜像升级后插件包不会自己跟着 pin 走，所以这里必须比版本。
weixin_installed_version() {
    local pkg="$1" oc_home="${OPENCLAW_HOME:-/root/.openclaw}" v f
    v="$((cd "$PROJECT_ROOT/openclaw" && pnpm openclaw plugins list --json) 2>/dev/null | python3 -c "
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
    if [ -n "$v" ]; then printf '%s\n' "$v"; return 0; fi
    for f in "$oc_home"/npm/projects/*/node_modules/"$pkg"/package.json; do
        [ -f "$f" ] || continue
        v="$(python3 -c "import json;print(json.load(open('$f')).get('version',''))" 2>/dev/null)"
        if [ -n "$v" ]; then printf '%s\n' "$v"; return 0; fi
    done
    return 1
}

install_weixin_plugin() {
    local pin_file="$PROJECT_ROOT/openclaw-weixin.version.json"
    local pkg ver
    if [ -f "$pin_file" ]; then
        pkg=$(python3 -c "import json;print(json.load(open('$pin_file'))['openclaw-weixin']['package'])" 2>/dev/null || true)
        ver=$(python3 -c "import json;print(json.load(open('$pin_file'))['openclaw-weixin']['version'])" 2>/dev/null || true)
    fi
    pkg="${pkg:-@tencent-weixin/openclaw-weixin}"
    ver="${ver:-2.4.8}"
    # 幂等检查：已装版本 == pin 才跳过
    local installed force_flag=""
    installed="$(weixin_installed_version "$pkg" || true)"
    if [ -n "$installed" ] && [ "$installed" = "$ver" ]; then
        log "openclaw-weixin plugin already installed (${ver})"
        return 0
    fi
    if [ -n "$installed" ]; then
        log "openclaw-weixin 已装 ${installed}，pin=${ver} → --force 升级"
        force_flag="--force"
    elif (cd "$PROJECT_ROOT/openclaw" && pnpm openclaw plugins list 2>/dev/null | grep -q "openclaw-weixin"); then
        log "⚠️ openclaw-weixin 已装但版本读不到；按 pin ${ver} 强制重装"
        force_flag="--force"
    fi
    log "installing openclaw-weixin plugin (${pkg}@${ver})"
    if (cd "$PROJECT_ROOT/openclaw" && pnpm openclaw plugins install "${pkg}@${ver}" --pin $force_flag); then
        log "openclaw-weixin plugin installed (${ver})"
    else
        log "⚠️ openclaw-weixin 插件预装失败；首启可手动：pnpm openclaw plugins install ${pkg}@${ver} --pin $force_flag"
    fi
}
log "STEP 5: installing openclaw-weixin plugin..."
install_weixin_plugin
log "STEP 5 done"

# ─── gateway 配置：bind lan + token mode ─────────────────────────
# 容器内 gateway 要经 published localhost:18789 端口被宿主访问，故 bind lan
# token 不持久化进镜像，entrypoint 首启生成随机 token 写 ~/.openclaw/.env
OPENCLAW_CONFIG_PATH="$OPENCLAW_CONFIG_PATH" node - <<'NODE'
const fs = require('fs');
const path = process.env.OPENCLAW_CONFIG_PATH;
const config = JSON.parse(fs.readFileSync(path, 'utf8'));
config.gateway = { ...(config.gateway || {}), bind: 'lan' };
config.gateway.auth = { ...(config.gateway.auth || {}), mode: 'token' };
delete config.gateway.auth.token;
fs.writeFileSync(path, `${JSON.stringify(config, null, 2)}\n`);
NODE
log "STEP 6 done: gateway config (bind lan + token mode)"

log "✅ immutable application layer prepared"
