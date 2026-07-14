#!/bin/bash
# wiseflow addon - overrides.sh
# 由 apply-addons.sh 调用，接收环境变量：ADDON_DIR, OPENCLAW_DIR
#
# 浏览器栈转向（camoufox-cli pivot，见 docs/browser-extension-replacement-research.md §12）后，
# patchright 注入已移除（§12.4 R7）：
#   - 线 1 target=camoufox：Firefox 系，走 camoufox-cli daemon，不碰 playwright-core。
#   - 线 2 target=host existing-session：真机 Chrome 走 chrome-mcp relay，不需 patchright。
#   - 线 2 target=host/node remote-cdp：远端 Chrome 走 CDP，patchright 改的是本地
#     playwright-core 对远端浏览器无反侦测意义；playwright-core 留原版给 connectOverCDP 用。
# 故 pnpm overrides（playwright-core → patchright-core）与 doc sed（playwright-core → patchright-core）
# 均已删除。如未来需重新引入反侦测覆盖，再在此处恢复。
set -e

# ─── 禁用内置 web_search 工具（由 smart-search skill 通过浏览器替代） ──────────
# openclaw 加载顺序：CWD/.env → OPENCLAW_STATE_DIR/.env（不覆盖已有值）
# 这里写入 OPENCLAW_STATE_DIR/.env（默认 ~/.openclaw/.env）
OPENCLAW_STATE_DIR="${OPENCLAW_STATE_DIR:-$HOME/.openclaw}"
ENV_FILE="$OPENCLAW_STATE_DIR/.env"
mkdir -p "$OPENCLAW_STATE_DIR"
if ! grep -q "OPENCLAW_DISABLE_WEB_SEARCH" "$ENV_FILE" 2>/dev/null; then
  echo "OPENCLAW_DISABLE_WEB_SEARCH=1" >> "$ENV_FILE"
  echo "    → injected OPENCLAW_DISABLE_WEB_SEARCH=1 into $ENV_FILE"
else
  echo "    → OPENCLAW_DISABLE_WEB_SEARCH already set in $ENV_FILE"
fi
