#!/usr/bin/env bash
# aigc-video-gen.sh — aigc-video-gen 顶层 wrapper（薄转发）
# 让 agent 用 `aigc-video-gen <args>` 走 PATH，零路径拼接。
#
# 三供应商脚本拆分：
#   scripts/gen_minimax.py    — MiniMax Hailuo（视频 + 音乐）
#   scripts/gen_volc.py       — 火山引擎 Seedance
#   scripts/gen_dashscope.py  — 百炼业务空间 Wan3.0 / Fun-Music、Agent Plan HappyHorse
#
# Dispatch 顺序：
#   1. argv 含 --platform <value> → 转发到对应 gen_*.py（剔除 --platform 参数）
#   2. 视频按 env 自动判：MINIMAX_API_KEY → minimax；VOLC_SEEDANCE_API_KEY → volcengine；
#      MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY/WORKSPACE_ID → dashscope；
#      AWK_API_KEY → dashscope（agent plan 模式，排最后：它是主模型 key，
#      只在没有任何显式视频平台凭据时才兜底触发百炼）
#      音乐单独按 MINIMAX_API_KEY → 完整百炼业务空间凭据选路。
#   3. 皆无 → 输出提示让 Agent 改用 pexels-footage / pixabay-footage（退出码 2）
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
SCRIPTS="$SCRIPT_DIR/scripts"

# ---- 1. 扫 --platform <value> 显式指定 ----------------------------------------
PLATFORM=""
i=1
while [ "$i" -le "$#" ]; do
  arg="${!i}"
  if [ "$arg" = "--platform" ]; then
    j=$((i + 1))
    if [ "$j" -gt "$#" ]; then
      echo "[error] --platform 缺少参数值（minimax / volcengine / dashscope）" >&2
      exit 1
    fi
    PLATFORM="${!j}"
    break
  fi
  i=$((i + 1))
done

# 从 argv 剔除 --platform <value>（下游 gen_*.py 不识别此参数）
strip_platform() {
  local out=() skip=0
  for arg in "$@"; do
    if [ "$skip" -eq 1 ]; then
      skip=0
      continue
    fi
    if [ "$arg" = "--platform" ]; then
      skip=1
      continue
    fi
    out+=("$arg")
  done
  printf '%s\0' "${out[@]}"
}

# music 使用独立供应商选路，避免火山 / Agent Plan 视频凭据误触发。
mapfile -d '' -t CLEAN_ARGS < <(strip_platform "$@")
COMMAND="${CLEAN_ARGS[0]:-video}"

# ---- 2. 无 --platform 时按 env 自动判 -----------------------------------------
if [ -z "$PLATFORM" ]; then
  if [ "$COMMAND" = "music" ]; then
    if [ -n "${MINIMAX_API_KEY:-}" ]; then
      PLATFORM="minimax"
    elif [ -n "${WORKSPACE_ID:-}" ] && { [ -n "${MODELSTUDIO_API_KEY:-}" ] || [ -n "${DASHSCOPE_API_KEY:-}" ]; }; then
      PLATFORM="dashscope"
    else
      echo "[error] 音乐生成凭据未配置：需 MINIMAX_API_KEY，或 WORKSPACE_ID + MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY（百炼业务空间）。" >&2
      exit 2
    fi
  elif [ -n "${MINIMAX_API_KEY:-}" ]; then
    PLATFORM="minimax"
  elif [ -n "${VOLC_SEEDANCE_API_KEY:-}" ]; then
    PLATFORM="volcengine"
  elif [ -n "${MODELSTUDIO_API_KEY:-}" ] || [ -n "${DASHSCOPE_API_KEY:-}" ] || [ -n "${WORKSPACE_ID:-}" ]; then
    PLATFORM="dashscope"
  elif [ -n "${AWK_API_KEY:-}" ]; then
    PLATFORM="dashscope"
  else
    echo "[error] 未检测到任何视频生成平台的环境变量" >&2
    echo "        （MODELSTUDIO_API_KEY / DASHSCOPE_API_KEY / WORKSPACE_ID / AWK_API_KEY / VOLC_SEEDANCE_API_KEY / MINIMAX_API_KEY 均未设置）。" >&2
    echo "[hint] 请改用 pexels-footage 和 pixabay-footage 技能搜集素材：" >&2
    echo "       1) pexels-footage 搜索并下载 9:16 竖屏素材" >&2
    echo "       2) pexels 无结果时用 pixabay-footage 兜底" >&2
    echo "       3) 下载后按脚本片段编号重命名放入 artifacts/" >&2
    echo "       若要启用 AI 直生成，请配置上述任一平台的环境变量。" >&2
    exit 2
  fi
fi

if [ "$COMMAND" = "music" ] && [ "$PLATFORM" = "volcengine" ]; then
  echo "[error] music 仅支持 minimax / dashscope（百炼业务空间）" >&2
  exit 1
fi

# ---- 3. dispatch 到对应 gen_*.py ----------------------------------------------
case "$PLATFORM" in
  minimax)    target="$SCRIPTS/gen_minimax.py" ;;
  volcengine) target="$SCRIPTS/gen_volc.py" ;;
  dashscope)  target="$SCRIPTS/gen_dashscope.py" ;;
  *)
    echo "[error] 未知 --platform 值：$PLATFORM（合法值：minimax / volcengine / dashscope）" >&2
    exit 1
    ;;
esac

if [ ! -f "$target" ]; then
  echo "[error] 供应商脚本不存在：$target" >&2
  exit 1
fi

# 转发剔除 --platform 后的 argv
exec python3 "$target" "${CLEAN_ARGS[@]}"
