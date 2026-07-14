#!/usr/bin/env bash
# fetch_note_content.sh — Download XHS note images and text for analysis
#
# Wraps the TypeScript implementation. Agent calls this directly.
#
# Usage: fetch_note_content.sh --url <url> | --note-id <id> [--xsec-token <t>] [--xsec-source <s>] --output-dir <dir>
#
# Exit codes:
#   0  Success
#   1  General error
#   2  Cookie expired → trigger login-manager

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec node --experimental-strip-types "${SCRIPT_DIR}/fetch_note_content.ts" "$@"
