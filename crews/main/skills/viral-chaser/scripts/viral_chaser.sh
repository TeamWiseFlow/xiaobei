#!/usr/bin/env bash
# viral_chaser.sh — Viral video analyzer CLI
#
# Wraps the TypeScript implementation. Agent calls this directly.
#
# Usage: viral_chaser.sh --video <local-file> [--audio <local-audio>] [--output-dir <dir>] [--no-frames]
#
# Exit codes:
#   0  Success
#   1  General error
#   2  ASR credentials missing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec node --experimental-strip-types "${SCRIPT_DIR}/analyzer.ts" "$@"
