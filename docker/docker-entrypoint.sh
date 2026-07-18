#!/usr/bin/env bash
set -euo pipefail

XIAOBEI_ROOT=/opt/xiaobei
OPENCLAW_HOME=${OPENCLAW_HOME:-/root/.openclaw}
CAMOUFOX_HOME=${CAMOUFOX_HOME:-/root/.camoufox-cli}
RUNTIME_SEED=/opt/xiaobei/runtime-seed/openclaw
DOTENV="$OPENCLAW_HOME/.env"
DAEMON_ENV="$OPENCLAW_HOME/daemon.env"

fail() {
  echo "[xiaobei] ERROR: $*" >&2
  exit 1
}

bootstrap_runtime_state() {
  if [ ! -f "$OPENCLAW_HOME/openclaw.json" ]; then
    [ -d "$RUNTIME_SEED" ] || fail "runtime seed is missing: $RUNTIME_SEED"
    echo "[xiaobei] initializing persistent OpenClaw state"
    install -d -m 700 "$OPENCLAW_HOME"
    cp -a "$RUNTIME_SEED/." "$OPENCLAW_HOME/"
  fi
  install -d -m 700 "$CAMOUFOX_HOME"
  chmod 700 "$OPENCLAW_HOME" "$CAMOUFOX_HOME"
}

load_runtime_environment() {
  # Compose variables take precedence over persisted configuration. The seed
  # contains placeholders, which must never shadow a supplied AWK_API_KEY.
  local supplied_awk_api_key=${AWK_API_KEY:-}

  if [ -f "$DAEMON_ENV" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$DAEMON_ENV"
    set +a
  fi

  if [ -f "$DOTENV" ]; then
    local clean_dotenv
    clean_dotenv=$(mktemp)
    grep -v '__FILL_.*__' "$DOTENV" > "$clean_dotenv" || true
    set -a
    # shellcheck disable=SC1090
    . "$clean_dotenv"
    set +a
    rm -f "$clean_dotenv"
  fi

  if [ -n "$supplied_awk_api_key" ]; then
    export AWK_API_KEY="$supplied_awk_api_key"
  fi
}

ensure_gateway_token() {
  if [ -z "${OPENCLAW_GATEWAY_TOKEN:-}" ]; then
    umask 077
    OPENCLAW_GATEWAY_TOKEN=$(node -e 'process.stdout.write(require("node:crypto").randomBytes(32).toString("base64url"))')
    printf '\nOPENCLAW_GATEWAY_TOKEN=%s\n' "$OPENCLAW_GATEWAY_TOKEN" >> "$DOTENV"
    chmod 600 "$DOTENV"
    export OPENCLAW_GATEWAY_TOKEN
    echo "[xiaobei] generated and persisted a gateway token"
  fi
}

start_display_stack() {
  export DISPLAY=${DISPLAY:-:99}
  Xvfb "$DISPLAY" -screen 0 1280x800x24 -ac >/tmp/xiaobei-xvfb.log 2>&1 &
  fluxbox >/tmp/xiaobei-fluxbox.log 2>&1 &
  x11vnc -display "$DISPLAY" -forever -shared -nopw -rfbport 5900 >/tmp/xiaobei-x11vnc.log 2>&1 &
  websockify --web=/usr/share/novnc 6080 localhost:5900 >/tmp/xiaobei-websockify.log 2>&1 &
}

# Flip the openclaw-weixin switches on first launch so the channel comes up
# alongside the gateway.  The plugin itself is pre-installed in the image by
# docker-bootstrap.sh → install-weixin-channel.sh --no-enable.
enable_weixin_channel() {
  node -e '
    const fs = require("fs");
    const p = process.argv[1];
    const c = JSON.parse(fs.readFileSync(p, "utf8"));
    c.plugins = c.plugins || {};
    c.plugins.entries = c.plugins.entries || {};
    c.plugins.entries["openclaw-weixin"] = { ...(c.plugins.entries["openclaw-weixin"] || {}), enabled: true };
    c.channels = c.channels || {};
    c.channels["openclaw-weixin"] = { ...(c.channels["openclaw-weixin"] || {}), enabled: true };
    fs.writeFileSync(p, JSON.stringify(c, null, 2) + "\n");
  ' "$OPENCLAW_HOME/openclaw.json"
  echo "[xiaobei] openclaw-weixin channel enabled"
}

# First-launch WeChat binding: print the QR code to stdout and poll until the
# user scans + confirms.  Subsequent launches skip this (binding state persists
# in /root/.openclaw/openclaw-weixin/accounts.json + accounts/{accountId}.json).
#
# 注意:插件 accounts.js 的 resolveStateDir() = OPENCLAW_STATE_DIR || ~/.openclaw
# 容器里 OPENCLAW_HOME=/root/.openclaw 已写死,但 OPENCLAW_STATE_DIR 未设时插件用
# os.homedir() 拼 .openclaw —— 即嵌套层 /root/.openclaw/.openclaw/。扫码后绑定态
# 落到嵌套层 openclaw-weixin/accounts.json。entrypoint 兜底迁移到挂载卷根。
bind_weixin_channel() {
  local nested_dir="$OPENCLAW_HOME/.openclaw/openclaw-weixin"
  local nested_binding="$nested_dir/accounts.json"
  local root_dir="$OPENCLAW_HOME/openclaw-weixin"
  local root_binding="$root_dir/accounts.json"

  # 嵌套层有绑定态 → 迁到挂载卷根(只迁一次,幂等)
  if [ -f "$nested_binding" ] && [ ! -f "$root_binding" ]; then
    echo "[xiaobei] migrating weixin binding from nested .openclaw/ to volume root"
    install -d -m 700 "$root_dir"
    cp -a "$nested_dir/." "$root_dir/" 2>/dev/null || true
    echo "[xiaobei] weixin binding migrated — next restart will skip QR login"
  fi

  if [ -f "$root_binding" ]; then
    echo "[xiaobei] weixin already bound — skip QR login"
    return 0
  fi

  echo "[xiaobei] first launch — starting WeChat QR binding"
  echo "[xiaobei] scan the QR code below with WeChat on your phone, then confirm login"
  node "$XIAOBEI_ROOT/scripts/weixin-qr.mjs" || {
    echo "[xiaobei] ⚠️ weixin-qr exited non-zero; gateway will start without weixin binding"
    return 0
  }

  # 扫码成功后绑定态在嵌套层(插件路径决策)——立即迁到挂载卷根
  if [ -f "$nested_binding" ] && [ ! -f "$root_binding" ]; then
    install -d -m 700 "$root_dir"
    cp -a "$nested_dir/." "$root_dir/" 2>/dev/null || true
    echo "[xiaobei] weixin binding captured to persistent volume"
  fi
}

bootstrap_runtime_state
load_runtime_environment

if [ -z "${AWK_API_KEY:-}" ] || [[ "$AWK_API_KEY" == __FILL_*__ ]]; then
  fail "AWK_API_KEY is required; run: AWK_API_KEY=<key> docker compose up -d"
fi

ensure_gateway_token
start_display_stack
enable_weixin_channel

# Render ${AWK_API_KEY} placeholder in openclaw.json with the real env value.
# docker-bootstrap.sh copies config-templates/openclaw.json into the image during
# build — at build time AWK_API_KEY is unset, so the apiKey 字段 stays a literal
# "${AWK_API_KEY}" placeholder. Without substitution here, the gateway receives an
# empty AWK credential and silently falls back to openai/gpt-5.5 (bundled). Only
# the apiKey 字段 is touched; all other fields already shipped correct from the template.
# 必须在 bind_weixin_channel 之前:bind 步会前台跑 weixin-qr.mjs 等扫码,render 跑不到。
node -e '
  const fs = require("fs");
  const p = process.argv[1];
  const key = process.env.AWK_API_KEY;
  if (!key) { console.error("[xiaobei] AWK_API_KEY missing — cannot render openclaw.json"); process.exit(1); }
  let raw = fs.readFileSync(p, "utf8");
  const before = raw;
  raw = raw.replace(/\$\{AWK_API_KEY\}/g, key);
  if (raw !== before) {
    fs.writeFileSync(p, raw);
    console.log("[xiaobei] AWK_API_KEY rendered into openclaw.json");
  }
' "$OPENCLAW_HOME/openclaw.json"

bind_weixin_channel

echo "[xiaobei] starting gateway"
cd "$XIAOBEI_ROOT/openclaw"
exec pnpm openclaw gateway --allow-unconfigured
