#!/usr/bin/env bash
# render-manim.sh — Manim 场景渲染 + 封面帧导出
#
# Usage: render-manim.sh <scene_file.py> <ClassName> [quality] [output_dir]
#   quality  : low（冒烟测试，默认）| medium（预览）| high（正式输出）
#   output_dir: 输出目录（默认 ./output）
#
# 输出：
#   <output_dir>/<scene>_<Class>_<quality>.mp4
#   <output_dir>/<scene>_<Class>_thumbnail.png
#   stdout 最后一行：JSON {"ok":true,"video":"...","thumbnail":"..."}

set -euo pipefail

SCENE_FILE="${1:?Usage: render-manim.sh <scene_file.py> <ClassName> [quality] [output_dir]}"
CLASS_NAME="${2:?Missing ClassName}"
QUALITY="${3:-low}"
OUTPUT_DIR="${4:-./output}"

[[ -f "$SCENE_FILE" ]] || { echo "ERROR: 场景文件不存在: $SCENE_FILE"; exit 1; }

case "$QUALITY" in
  low)    Q_FLAG="-ql" ;;
  medium) Q_FLAG="-qm" ;;
  high)   Q_FLAG="-qh" ;;
  *) echo "ERROR: quality 必须是 low/medium/high"; exit 1 ;;
esac

mkdir -p "$OUTPUT_DIR"
SCENE_BASE=$(basename "$SCENE_FILE" .py)

# 使用临时 media 目录，避免污染工作目录
MEDIA_DIR=$(mktemp -d)
trap "rm -rf '$MEDIA_DIR'" EXIT

echo ">>> 渲染: $CLASS_NAME ($QUALITY)"
manim "$Q_FLAG" "$SCENE_FILE" "$CLASS_NAME" --media_dir "$MEDIA_DIR"

# 找到渲染输出的 MP4
VIDEO_PATH=$(find "$MEDIA_DIR/videos" -name "*.mp4" | head -1)
[[ -n "$VIDEO_PATH" ]] || { echo "ERROR: 未找到渲染输出文件"; exit 1; }

FINAL_VIDEO="$OUTPUT_DIR/${SCENE_BASE}_${CLASS_NAME}_${QUALITY}.mp4"
cp "$VIDEO_PATH" "$FINAL_VIDEO"
echo ">>> 视频: $FINAL_VIDEO"

# 导出封面帧（第 2 秒）
THUMBNAIL="$OUTPUT_DIR/${SCENE_BASE}_${CLASS_NAME}_thumbnail.png"
ffmpeg -y -i "$FINAL_VIDEO" -ss 2 -frames:v 1 "$THUMBNAIL" -loglevel error
echo ">>> 封面帧: $THUMBNAIL"

echo "{\"ok\":true,\"video\":\"$FINAL_VIDEO\",\"thumbnail\":\"$THUMBNAIL\"}"
