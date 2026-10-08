#!/usr/bin/env bash
# video-edit.sh — video-edit 顶层 wrapper（子命令分发）
# 让 agent 用 `video-edit <子命令> [参数...]` 走 PATH，零路径拼接。
# 每个子命令 exec 转发到 scripts/ 下对应脚本，不改语义。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"

cmd="${1:-}"
if [ $# -gt 0 ]; then shift; fi

case "$cmd" in
  extract)   exec python3 "$SCRIPT_DIR/scripts/extract_and_concat.py" "$@" ;;
  assemble)  exec python3 "$SCRIPT_DIR/scripts/assemble.py" "$@" ;;
  audio-mix) exec python3 "$SCRIPT_DIR/scripts/audio_mix.py" "$@" ;;
  subtitles) exec python3 "$SCRIPT_DIR/scripts/burn_subtitles.py" "$@" ;;
  frames)    exec python3 "$SCRIPT_DIR/scripts/sample_frames.py" "$@" ;;
  apply-cut) exec python3 "$SCRIPT_DIR/scripts/apply_cut.py" "$@" ;;
  preview)   exec python3 "$SCRIPT_DIR/scripts/compress_preview.py" "$@" ;;
  *)
    cat >&2 <<'EOF'
用法: video-edit <子命令> [参数...]

子命令:
  extract    从视频抽段（head/tail/slice）、全片转 MP4（full）并可选多段拼接
  assemble   把 artifacts/ 下按数字前缀排序的片段拼成成片
  audio-mix  给视频加旁白/背景音乐（混音）
  subtitles  烧录 SRT/ASS 字幕
  frames     按间隔抽帧（画面分析用）
  apply-cut  按 cut_plan.json 剪拼
  preview    压缩出 ≤16MB 预览（仅聊天确认用）

每个子命令支持 --help 查看参数。
EOF
    exit 1
    ;;
esac
