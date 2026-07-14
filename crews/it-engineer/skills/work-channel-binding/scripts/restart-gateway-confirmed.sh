#!/usr/bin/env bash
set -euo pipefail

if [ "${WISEFLOW_CONFIRM_GATEWAY_RESTART:-}" != "confirmed" ]; then
  echo "Refusing to restart Gateway without WISEFLOW_CONFIRM_GATEWAY_RESTART=confirmed" >&2
  exit 2
fi

reason="${1:-manual}"
log_dir="${HOME}/.openclaw/workspace-main"
mkdir -p "$log_dir"
printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$reason" >> "$log_dir/gateway-restart-audit.log"
exec systemctl --user restart openclaw-gateway
