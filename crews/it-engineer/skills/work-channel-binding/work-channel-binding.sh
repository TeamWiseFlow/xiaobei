#!/usr/bin/env bash
set -euo pipefail

SELF="${BASH_SOURCE[0]}"
while [ -L "$SELF" ]; do
  LINK_DIR="$(cd "$(dirname "$SELF")" && pwd -P)"
  SELF="$(readlink "$SELF")"
  case "$SELF" in
    /*) ;;
    *) SELF="$LINK_DIR/$SELF" ;;
  esac
done
SCRIPTS="$(cd "$(dirname "$SELF")/scripts" && pwd)"
COMMAND="${1:-}"
if [ "$#" -gt 0 ]; then shift; fi

case "$COMMAND" in
  install-wecom) exec bash "$SCRIPTS/install-wecom-channel.sh" "$@" ;;
  check) exec python3 "$SCRIPTS/check-work-channel-bindings.py" "$@" ;;
  prepare) exec python3 "$SCRIPTS/prepare-work-channel-binding.py" "$@" ;;
  apply) exec python3 "$SCRIPTS/apply-work-channel-binding.py" "$@" ;;
  record-followup) exec python3 "$SCRIPTS/record-pending-followup.py" "$@" ;;
  restart) exec bash "$SCRIPTS/restart-gateway-confirmed.sh" "$@" ;;
  complete-followup) exec python3 "$SCRIPTS/complete-pending-followup.py" "$@" ;;
  *)
    printf 'Usage: work-channel-binding {install-wecom|check|prepare|apply|record-followup|restart|complete-followup}\n' >&2
    exit 2
    ;;
esac
