#!/usr/bin/env bash
# xiaobei 容器入口脚本
#
# 职责：
#   1. 首启从镜像内 runtime-seed 初始化空的 /root/.openclaw 和 /root/.camoufox-cli 卷
#      （已有卷绝不覆盖——升级镜像时登录态和用户配置会保留）
#   2. 加载持久化 .env / daemon.env，把各 LLM 网关 key 渲染进 openclaw.json 的 apiKey 字段
#      （AWK_API_KEY → bailian-token-plan/awk，ORCAROUTER_API_KEY → orcarouter）
#   3. 首启生成随机 OPENCLAW_GATEWAY_TOKEN 写 ~/.openclaw/.env（不进镜像层）
#   4. 启动显示栈：Xvfb（虚拟显示，camoufox 有头模式跑这里）+ fluxbox + x11vnc + websockify + noVNC
#      用户浏览器开 http://localhost:6080 操作 VNC 桌面，里面能看到 camoufox 浏览器窗口
#      过小红书/抖音等平台验证
#   5. 首启若未绑定微信则打印扫码二维码（weixin-qr.mjs），扫码后绑定态迁到挂载卷根
#   6. 启动 openclaw gateway（--allow-unconfigured，首启即跑）
set -euo pipefail

XIAOBEI_ROOT=/opt/xiaobei
OPENCLAW_HOME="${OPENCLAW_HOME:-/root/.openclaw}"
CAMOUFOX_HOME="${CAMOUFOX_HOME:-/root/.camoufox-cli}"
RUNTIME_SEED=/opt/xiaobei/runtime-seed/openclaw
DOTENV="$OPENCLAW_HOME/.env"
DAEMON_ENV="$OPENCLAW_HOME/daemon.env"
DISPLAY_NUM="${DISPLAY_NUM:-99}"
export DISPLAY=":${DISPLAY_NUM}"

fail() {
  echo "[xiaobei] ERROR: $*" >&2
  exit 1
}

# ─── 1. 首启初始化空卷 ──────────────────────────────────────────────
bootstrap_runtime_state() {
  if [ ! -f "$OPENCLAW_HOME/openclaw.json" ]; then
    [ -d "$RUNTIME_SEED" ] || fail "runtime seed missing: $RUNTIME_SEED"
    echo "[xiaobei] first launch — initializing persistent OpenClaw state from seed"
    install -d -m 700 "$OPENCLAW_HOME"
    cp -a "$RUNTIME_SEED/." "$OPENCLAW_HOME/"
  fi
  install -d -m 700 "$CAMOUFOX_HOME"
  chmod 700 "$OPENCLAW_HOME" "$CAMOUFOX_HOME"
}

# ─── 2. 加载运行时环境 ─────────────────────────────────────────────
load_runtime_environment() {
  # Compose 注入的 AWK_API_KEY 优先于持久化 .env 里的值
  local supplied_awk_api_key="${AWK_API_KEY:-}"

  if [ -f "$DAEMON_ENV" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$DAEMON_ENV"
    set +a
  fi

  if [ -f "$DOTENV" ]; then
    local clean_dotenv
    clean_dotenv=$(mktemp)
    # 过滤 placeholder（__FILL_*__），避免阴影真实 key
    grep -v '__FILL_.*__' "$DOTENV" > "$clean_dotenv" || true
    set -a
    # shellcheck disable=SC1090
    . "$clean_dotenv"
    set +a
    rm -f "$clean_dotenv"
  fi

  # 仅当 compose 注入的是真值时才覆盖 .env 的值；
  # 占位符 __FILL_*__ 说明调用方没传 key，应让 .env 里的真值保留
  if [ -n "$supplied_awk_api_key" ] && [[ "$supplied_awk_api_key" != __FILL_*__ ]]; then
    export AWK_API_KEY="$supplied_awk_api_key"
  fi

  # daemon.env 来自持久卷，内容不可控：若其中混入 DISPLAY（如宿主机桌面机的
  # DISPLAY=:0 被抄进来），会覆盖入口脚本上方 export 的 Xvfb 显示号（:99），
  # 有头浏览器开去不存在的显示、noVNC 里什么都看不到。这里强制恢复入口设定。
  export DISPLAY=":${DISPLAY_NUM}"

  # 保证 skill wrapper 软链目录在 PATH 最前。gateway 不 source shell rc，agent exec
  # 调裸技能名（如 aigc-video-gen）靠 PATH 解析 ~/.openclaw/bin 下的 wrapper 软链。
  # 幂等：已在 PATH 中则跳过；缺失则前置，避免 daemon.env 模板或持久卷里漏写。
  if [ -d "$OPENCLAW_HOME/bin" ]; then
    case ":${PATH:-}:" in
      *":$OPENCLAW_HOME/bin:"*) ;;
      *) export PATH="$OPENCLAW_HOME/bin:$PATH" ;;
    esac
  fi
}

# ─── 3. 首启生成 gateway token ─────────────────────────────────────
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

# ─── 4. 显示栈：Xvfb + fluxbox + x11vnc + websockify ───────────────
# camoufox 有头模式跑在 Xvfb 虚拟显示里，用户经 noVNC（http://localhost:6080）
# 看到该显示里的浏览器窗口，可操作过小红书/抖音验证。
start_display_stack() {
  echo "[xiaobei] starting display stack (Xvfb :${DISPLAY_NUM} + fluxbox + x11vnc + websockify)"
  # Xvfb 虚拟显示（1280x800 分辨率足够浏览器窗口 + 验证码滑块操作）
  Xvfb "$DISPLAY" -screen 0 1280x800x24 -ac >/tmp/xiaobei-xvfb.log 2>&1 &
  # 等显示就绪
  for i in 1 2 3 4 5; do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then break; fi
    sleep 0.5
  done
  # fluxbox 极简窗口管理器（看到浏览器窗口标题栏 + 可拖动）
  DISPLAY="$DISPLAY" fluxbox >/tmp/xiaobei-fluxbox.log 2>&1 &
  # x11vnc 把 Xvfb 显示暴露成 VNC（5900 内部端口，无密码——容器内只绑 127.0.0.1）
  x11vnc -display "$DISPLAY" -forever -shared -nopw -rfbport 5900 -localhost >/tmp/xiaobei-x11vnc.log 2>&1 &
  # websockify 把 VNC 流转成 WebSocket，noVNC web 客户端通过它连
  websockify --web=/usr/share/novnc 6080 localhost:5900 >/tmp/xiaobei-websockify.log 2>&1 &
  echo "[xiaobei] noVNC web client: http://localhost:6080/vnc.html"
}

# ─── 5. 渲染 LLM 网关 key 进 openclaw.json ─────────────────────────
# 每次启动都用当前环境变量覆盖 openclaw.json 里各 provider 的 apiKey 字段。
#
# 历史问题：旧版用 raw.replace(/\$\{AWK_API_KEY\}/g, key) 替换 placeholder，
# 但第一次渲染后 placeholder 就没了，第二次启动找不到 placeholder 就跳过写入——
# openclaw.json 里永远是第一次的值，后面改环境变量没用。
#
# 修复：改成 JSON 解析，直接定位 models.providers["<provider>"].apiKey，
# 每次启动用当前环境变量覆盖。无论 openclaw.json 里是 ${VAR} placeholder 还是
# 已渲染的真值，都能正确更新。
#
# 每个 provider 用各自的 key 环境变量：
#   bailian-token-plan / awk → AWK_API_KEY
#   orcarouter                → ORCAROUTER_API_KEY
render_provider_api_keys() {
  node -e '
    const fs = require("fs");
    const p = process.argv[1];
    const config = JSON.parse(fs.readFileSync(p, "utf8"));
    const providers = config?.models?.providers || {};

    // provider 名（归一化小写）→ 该 provider 的 key 环境变量
    const keyEnvByProvider = {
      "bailian-token-plan": "AWK_API_KEY",
      "awk": "AWK_API_KEY",
      "orcarouter": "ORCAROUTER_API_KEY",
    };

    let updated = false;
    for (const [name, provider] of Object.entries(providers)) {
      if (!provider || typeof provider.apiKey !== "string") continue;
      const envVar = keyEnvByProvider[name.toLowerCase()];
      if (!envVar) continue; // 未知 provider，不碰
      const key = process.env[envVar];
      if (!key || key.includes("__FILL")) {
        console.error(`[xiaobei] ${envVar} missing — skipping provider "${name}"`);
        continue;
      }
      if (provider.apiKey !== key) {
        provider.apiKey = key;
        updated = true;
      }
    }

    if (updated) {
      fs.writeFileSync(p, JSON.stringify(config, null, 2) + "\n");
      console.log("[xiaobei] provider API keys rendered into openclaw.json");
    }
  ' "$OPENCLAW_HOME/openclaw.json"
}

# ─── 6. 启用 weixin channel + 首启扫码绑定 ─────────────────────────
# 插件本体已在镜像内预装（docker-bootstrap.sh 阞装），这里只翻 enabled 开关 + 扫码绑定。
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

# 首启微信扫码绑定：打印 QR 到 stdout + 轮询扫码状态 + 写绑定态。
# 已绑定（accounts.json 存在）则跳过。
# 注意：插件 accounts.js 的 resolveStateDir() 用 os.homedir() 拼 .openclaw，容器里
# OPENCLAW_HOME=/root/.openclaw 但 OPENCLAW_STATE_DIR 也设了同名，仍可能嵌套层写绑定态，
# 扫码后兜底迁移到挂载卷根（与裸机 install.sh bind_weixin 同逻辑）。
bind_weixin_channel() {
  local nested_dir="$OPENCLAW_HOME/.openclaw/openclaw-weixin"
  local nested_binding="$nested_dir/accounts.json"
  local root_dir="$OPENCLAW_HOME/openclaw-weixin"
  local root_binding="$root_dir/accounts.json"

  # 嵌套层有绑定态 → 迁到挂载卷根（幂等）
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
  node "$XIAOBEI_ROOT/docker/weixin-qr.mjs" || {
    echo "[xiaobei] ⚠️ weixin-qr exited non-zero; gateway will start without weixin binding"
    return 0
  }

  # 扫码成功后绑定态可能在嵌套层，立即迁到挂载卷根
  if [ -f "$nested_binding" ] && [ ! -f "$root_binding" ]; then
    install -d -m 700 "$root_dir"
    cp -a "$nested_dir/." "$root_dir/" 2>/dev/null || true
    echo "[xiaobei] weixin binding captured to persistent volume"
  fi
}

# ─── main ──────────────────────────────────────────────────────────
bootstrap_runtime_state
load_runtime_environment

# 根据 openclaw.json 里实际存在的 provider 校验对应 key（用户换了模板则校验对应 key）
missing_provider_keys=""
for provider_env in "bailian-token-plan:AWK_API_KEY" "awk:AWK_API_KEY" "orcarouter:ORCAROUTER_API_KEY"; do
  provider="${provider_env%%:*}"
  env_var="${provider_env##*:}"
  if node -e 'const fs=require("fs");const c=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));const p=c?.models?.providers||{};process.exit(p[process.argv[2]]?0:1)' "$OPENCLAW_HOME/openclaw.json" "$provider"; then
    if [ -z "${!env_var:-}" ] || [[ "${!env_var}" == __FILL_*__ ]]; then
      missing_provider_keys="${missing_provider_keys} ${env_var}"
    fi
  fi
done
if [ -n "$missing_provider_keys" ]; then
  fail "missing required provider key(s):${missing_provider_keys}; run with the matching env var, e.g. AWK_API_KEY=<key> or ORCAROUTER_API_KEY=<key> docker compose up -d"
fi

ensure_gateway_token
render_provider_api_keys
start_display_stack
enable_weixin_channel
bind_weixin_channel

echo "[xiaobei] starting gateway"
cd "$XIAOBEI_ROOT/openclaw"
exec pnpm openclaw gateway --allow-unconfigured
