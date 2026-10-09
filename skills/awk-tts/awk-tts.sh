#!/usr/bin/env bash
# awk-tts.sh — awk-tts 顶层 wrapper（薄转发）
# 让 agent 用 `awk-tts <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/tts.py；wrapper 自身只是 exec 转发，不改语义。
# 凭据走火山 VOLC_TTS_*（旧控制台双头）或 VOLC_TTS_APP_KEY（新控制台单头），见 SKILL.md。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
case "${1:-}" in
  voice-design|voice-clone|voice-status|voice-list)
    exec python3 "$SCRIPT_DIR/scripts/voice_customization.py" "$@" ;;
esac
exec python3 "$SCRIPT_DIR/scripts/tts.py" "$@"
