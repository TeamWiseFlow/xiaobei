#!/usr/bin/env bash
# viral_chaser.sh — Viral video analyzer CLI
#
# Wraps the TypeScript implementation. Agent calls this directly.
#
# Usage: viral_chaser.sh <url> [--no-frames]
#
# Exit codes:
#   0  Success
#   1  General error
#   2  Cookie expired → trigger login-manager

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec node --experimental-strip-types "${SCRIPT_DIR}/viral_chaser.ts" "$@"
