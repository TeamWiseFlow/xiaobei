#!/bin/bash
# docker-entrypoint.sh — wiseflow-client 容器入口
#
# 流程（plan §六 entrypoint 运行期）：
#   1. 读 env 渲染 daemon.env（key 占位 → 真实值）
#   2. 注入 OFB_KEY / relay 端点到各 skill 配置
#   3. node openclaw.mjs gateway（非 systemd，--restart=always 保活）
#   4. 检测 weixin 未绑 → qrcode-terminal 输出 stdout + UI(18789) 兜底
#
# Phase 0 骨架：框架流程就位，步骤 1/2 的具体渲染待 Phase 6 填实。
set -euo pipefail

OPENCLAW_HOME="${OPENCLAW_HOME:-/root/.openclaw}"
DAEMON_ENV="$OPENCLAW_HOME/daemon.env"
GATEWAY_PORT="${GATEWAY_PORT:-18789}"

echo "[entrypoint] wiseflow-client starting, OPENCLAW_HOME=$OPENCLAW_HOME"

# ── 1. 加载 daemon.env（gateway 运维变量）+ .env（技能密钥）────────────────
# daemon.env：PATH/超时/bonjour/DISPLAY 等 gateway 进程运维参数
# .env：所有技能密钥（AWK_API_KEY/OFB_KEY/WXWORK_* 等），openclaw 启动时加载进 process.env
# 优先级：docker run -e 传的环境变量 > .env > daemon.env（source 顺序：先运维后密钥）
# 首次启动：从 template 拷一份，用户编辑 .env 填 API key 后 docker restart 生效
DOTENV="$OPENCLAW_HOME/.env"

# daemon.env（运维变量）
if [ ! -f "$DAEMON_ENV" ] && [ -f "$OPENCLAW_HOME/daemon.env.template" ]; then
  cp "$OPENCLAW_HOME/daemon.env.template" "$DAEMON_ENV"
  chmod 600 "$DAEMON_ENV"
  echo "[entrypoint] 首次启动：已从 daemon.env.template 拷贝到 $DAEMON_ENV"
fi
if [ -f "$DAEMON_ENV" ]; then
  echo "[entrypoint] loading $DAEMON_ENV (运维变量)"
  set -a
  # shellcheck disable=SC1090
  source "$DAEMON_ENV"
  set +a
fi

# .env（技能密钥）——source 在 daemon.env 之后，密钥覆盖运维（罕见冲突，安全兜底）
# 占位保护：template 拷来的 .env 含 __FILL_*__ 占位，source 会覆盖 docker run -e 传入的
# 真实值。改用逐行解析：跳过占位行，只 export 非占位的 KEY=value。
if [ ! -f "$DOTENV" ] && [ -f "$OPENCLAW_HOME/.env.template" ]; then
  cp "$OPENCLAW_HOME/.env.template" "$DOTENV"
  chmod 600 "$DOTENV"
  echo "[entrypoint] 首次启动：已从 .env.template 拷贝到 $DOTENV"
  echo "[entrypoint]   请编辑该文件填入 AWK_API_KEY 等 API keys，然后 docker restart 生效"
fi
if [ -f "$DOTENV" ]; then
  echo "[entrypoint] loading $DOTENV (技能密钥)"
  # 占位保护：template 拷来的 .env 含 __FILL_*__ 占位，直接 source 会覆盖 docker run -e
  # 传入的真值。先 grep -v 删占位行到临时文件再 source——source 原生处理注释/空行/引号，
  # 比 while read 逐行 export 稳（后者对注释行报 not a valid identifier）。
  _dotenv_clean="$(mktemp)"
  grep -v '__FILL_.*__' "$DOTENV" > "$_dotenv_clean"
  set -a
  # shellcheck disable=SC1090
  source "$_dotenv_clean"
  set +a
  rm -f "$_dotenv_clean"
else
  echo "[entrypoint] WARN: $DOTENV 不存在，技能密钥需通过环境变量传入"
fi

# ── 2. 注入 relay 端点到 skill 配置 ─────────────────────────────────────────
# OFB_KEY / WXWORK_* 等技能密钥归 .env，不在此检查（用到时由 skill 自检报错）。

# ── 2.5 虚拟显示 + VNC 远程查看栈 ──────────────────────────────────────────
# camoufox 有头登录场景：用户需看到浏览器界面才能手动扫码/验证。
# Docker 容器无物理显示器，用 Xvfb 虚拟帧缓冲 + fluxbox 窗口管理器 +
# x11vnc 把 X 显示通过 VNC 暴露 + noVNC/websockify 让用户浏览器访问 :6080。
#
# 访问方式：浏览器打开 http://<容器IP>:6080/vnc.html
#
# DISPLAY 也可由 daemon.env 注入；这里统一设 :99（Xvfb 默认 display 号）。
DISPLAY="${DISPLAY:-:99}"
export DISPLAY

# 启动 Xvfb（虚拟帧缓冲，模拟 X 显示）
Xvfb "$DISPLAY" -screen 0 1280x800x24 -ac >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!
sleep 1  # 等 X server 就绪

# 启动 fluxbox（轻量窗口管理器，camoufox 有头需要 WM）
fluxbox >/tmp/fluxbox.log 2>&1 &
FLUXBOX_PID=$!

# 启动 x11vnc（把 X 显示通过 VNC 暴露）
# -forever: 保持运行，不退出
# -shared: 允许多客户端连接
# -rfbport: VNC 端口 5900
x11vnc -display "$DISPLAY" -forever -shared -nopw -rfbport 5900 >/tmp/x11vnc.log 2>&1 &
X11VNC_PID=$!

# 启动 websockify（noVNC 前端，HTTP→VNC 桥）
# 监听 6080，转发到 localhost:5900（x11vnc）
websockify --web=/usr/share/novnc 6080 localhost:5900 >/tmp/websockify.log 2>&1 &
WEBSOCKIFY_PID=$!

echo "[entrypoint] 虚拟显示栈已启动:"
echo "  Xvfb PID=$XVFB_PID (display=$DISPLAY, 1280x800x24)"
echo "  fluxbox PID=$FLUXBOX_PID"
echo "  x11vnc PID=$X11VNC_PID (VNC :5900)"
echo "  websockify PID=$WEBSOCKIFY_PID (noVNC :6080)"
echo "[entrypoint] 浏览器访问 http://<容器IP>:6080/vnc.html 看容器内界面"

# ── 2.6 camoufox 指纹模板 lazy 生成 ────────────────────────────────────────
# build 期不跑 camoufox-cli（Firefox sandbox 在 docker build cap 下 EPERM）。
# 容器首次启动时现生成指纹模板，落 /root/.openclaw/logins/_template/。
# 需 docker run --cap-add SYS_ADMIN（Firefox sandbox 需要 user namespace）。
TEMPLATE_DIR="$OPENCLAW_HOME/logins/_template"
if [ ! -f "$TEMPLATE_DIR/camoufox-cli.json" ]; then
  echo "[entrypoint] baking camoufox fingerprint template..."
  rm -rf /root/.camoufox-cli/profiles/_template
  if camoufox-cli --session _template --persistent --json open about:blank >/dev/null 2>&1; then
    camoufox-cli --session _template close >/dev/null 2>&1 || true
    cp /root/.camoufox-cli/profiles/_template/camoufox-cli.json "$TEMPLATE_DIR/" 2>/dev/null || true
    echo "[entrypoint] camoufox fingerprint template baked to $TEMPLATE_DIR"
  else
    echo "[entrypoint] WARN: camoufox fingerprint template bake failed." >&2
    echo "[entrypoint]   确认 docker run 带 --cap-add SYS_ADMIN；或运行时首会话现生成。" >&2
  fi
  camoufox-cli close --all >/dev/null 2>&1 || true
fi

# ── 3. 起 gateway ───────────────────────────────────────────────────────────
OPENCLAW_BIN="${OPENCLAW_BIN:-/opt/openclaw/openclaw/openclaw.mjs}"
if [ -f "$OPENCLAW_BIN" ]; then

  # AWK_API_KEY 软校验兜底（compose 用 ${AWK_API_KEY:-} 软校验，down 不拦）
  if [ -z "${AWK_API_KEY:-}" ] || [[ "${AWK_API_KEY}" == __FILL_*__ ]] || [ "${AWK_API_KEY}" = "dummy" ]; then
    echo "[entrypoint] ERROR: AWK_API_KEY 未设置或仍是占位。compose 启动需传真值：" >&2
    echo "[entrypoint]   AWK_API_KEY=<你的火山引擎key> docker compose up -d" >&2
    exit 1
  fi

  # ── 3a. 直填 AWK_API_KEY 真值进 openclaw.json ─────────────────────────────
  # openclaw gateway 启动时不主动 probe model catalog，apiKey 是 \${AWK_API_KEY} SecretRef
  # 时若解析时机有问题就回退 DEFAULT_MODEL=gpt-5.5。直填真值绕开 SecretRef 解析黑箱：
  # gateway 启动时直接认得 awk provider 可用，agent model 会是 awk/glm-latest。
  # 安全：真值写在 named volume 的 openclaw.json 里，不 bake 进镜像层。
  node -e "\
    const fs=require('fs'),p='$OPENCLAW_HOME/openclaw.json';\
    const c=JSON.parse(fs.readFileSync(p,'utf8'));\
    if(c.models?.providers?.awk?.apiKey==='\${AWK_API_KEY}'){\
      c.models.providers.awk.apiKey=process.env.AWK_API_KEY;\
      fs.writeFileSync(p,JSON.stringify(c,null,2)+'\\n');\
      console.log('[entrypoint] awk.apiKey 直填真值 OK');\
    }" || true

  export OPENCLAW_GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-wiseflow-gateway-token}"
  echo "[entrypoint] launching gateway: pnpm openclaw gateway"
  cd /opt/openclaw/openclaw && \
    exec pnpm openclaw gateway --allow-unconfigured --token "$OPENCLAW_GATEWAY_TOKEN"
else
  echo "[entrypoint] WARN: $OPENCLAW_BIN 不存在（build 产物未 bake）。退出。" >&2
  exit 0
fi
