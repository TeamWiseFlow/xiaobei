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

# ── 1. 渲染 daemon.env ──────────────────────────────────────────────────────
# TODO(Phase 6): 从 $OPENCLAW_HOME/daemon.env.template 渲染，把占位换成真实 env。
#   必填：AWK_API_KEY、OFB_KEY；可选：SMTP_*、RELAY_BASE_URL（默认固定端点）。
if [ ! -f "$DAEMON_ENV" ]; then
  echo "[entrypoint] WARN: $DAEMON_ENV 不存在，Phase 6 渲染逻辑未就位，用环境变量直传"
fi

# ── 2. 注入 relay 端点 + OFB_KEY 到 skill 配置 ─────────────────────────────
# relay 无状态多租户模型（2026-07-06）：RELAY_BASE_URL + OFB_KEY 作为环境变量注入，
#   各 skill 脚本从 env 读取。凭据按 skill 分置：
#   - wxwork-moments / wxwork-drive：WXWORK_CORP_ID + WXWORK_CORP_SECRET 从 daemon.env 读
#   - wx-mp-publisher：多账号凭据在 skill 目录 accounts.json（Agent 帮用户维护，gitignore）
#   - xhs-publish / bilibili-publish 等：业务凭据各自管理
export RELAY_BASE_URL="${RELAY_BASE_URL:-https://relay.wiseflow.example.com}"
# OFB_KEY 必须由用户传入
if [ -z "${OFB_KEY:-}" ]; then
  echo "[entrypoint] ERROR: OFB_KEY 未设置。容器需 -e OFB_KEY=<产品方发放的 key>" >&2
  exit 1
fi

# ── 3. 起 gateway ───────────────────────────────────────────────────────────
# TODO(Phase 6): 真正的入口是 node openclaw.mjs gateway。此处先 exec 占位。
OPENCLAW_BIN="${OPENCLAW_BIN:-/opt/openclaw/openclaw/openclaw.mjs}"
if [ -f "$OPENCLAW_BIN" ]; then
  echo "[entrypoint] launching gateway: node $OPENCLAW_BIN gateway"
  exec node "$OPENCLAW_BIN" gateway
else
  echo "[entrypoint] WARN: $OPENCLAW_BIN 不存在（Phase 6 build 产物未 bake）。退出。" >&2
  exit 0
fi

# ── 4. weixin 二维码 ───────────────────────────────────────────────────────
# TODO(Phase 6): gateway 起来后检测 weixin binding 未绑 → qrcode-terminal 输出
#   stdout（docker logs 可见）+ UI(18789) 兜底。由 gateway 内置逻辑或此处轮询实现。
