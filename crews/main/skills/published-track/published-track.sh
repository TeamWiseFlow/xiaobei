#!/usr/bin/env bash
# published-track.sh — published-track 顶层 wrapper（子命令分发）
# 让 agent 用 `published-track <子命令> [参数...]` 走 PATH，零路径拼接。
# 每个子命令 exec 转发到 scripts/ 下对应脚本，不改语义。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# 只解析 ~/.openclaw/bin 软链一层（bin/<skill> -> <workspace>/skills/<skill>/<skill>.sh），
# 不 readlink -f 继续展开 workspace 内 skills/<skill> 指向仓库模板的软链。
# 子脚本用 dirname $0/../../.. 推导 workspace 根（ROOT/db/…），readlink -f 会把
# workspace 折叠成仓库模板路径，导致 ROOT 解析到模板目录（无 db → 空结果）。
# 保留字面 workspace 路径，ROOT 才能命中真实运行数据目录。
if [ -L "$SELF" ]; then
  _target="$(readlink "$SELF")"
  case "$_target" in
    /*) SELF="$_target" ;;
    *)  SELF="$(cd "$(dirname "$SELF")" && pwd)/$_target" ;;
  esac
fi
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"

cmd="${1:-}"
if [ $# -gt 0 ]; then shift; fi

case "$cmd" in
  record)                 exec bash "$SCRIPT_DIR/scripts/record.sh" "$@" ;;
  update-metrics)         exec bash "$SCRIPT_DIR/scripts/update-metrics.sh" "$@" ;;
  platform-status)       exec python3 "$SCRIPT_DIR/scripts/platform-status.py" "$@" ;;
  query)                  exec bash "$SCRIPT_DIR/scripts/query.sh" "$@" ;;
  query-pending)          exec bash "$SCRIPT_DIR/scripts/query-pending.sh" "$@" ;;
  check-published)        exec bash "$SCRIPT_DIR/scripts/check-published.sh" "$@" ;;
  set-distribute-status)  exec bash "$SCRIPT_DIR/scripts/set-distribute-status.sh" "$@" ;;
  init-db)                exec bash "$SCRIPT_DIR/scripts/init-db.sh" "$@" ;;
  migrate-v3)             exec bash "$SCRIPT_DIR/scripts/migrate-v3.sh" "$@" ;;
  *)
    cat >&2 <<'USAGE'
用法: published-track <子命令> [参数...]

子命令:
  record                 发布记录入库（upsert；自动读 dna-meta.json 落 dna_id）
  update-metrics         更新单条/同 folder 记录的互动指标
  platform-status       查询平台是否启用（只读 calibration/platform-state.json）
  query                  通用查询（--platform [--limit]）
  query-pending          查询待分发内容
  check-published        查某作品是否已发布
  set-distribute-status  设置分发状态
  init-db                初始化数据库（幂等）
  migrate-v3             迁移到 v3 schema（dna_id/account/perf_evaluated，幂等）

每个子命令支持 --help 或无参调用查看参数（部分子命令）。
USAGE
    exit 1
    ;;
esac
