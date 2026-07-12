#!/bin/bash
# skill-wrappers.sh - 把 skill 顶层 wrapper 暴露到 ~/.openclaw/bin/（PATH 友好）
#
# 配合 D21 wrapper 覆盖：每个含顶层 <skill-name>.sh wrapper 的 skill，
# ln -sfn 一条 symlink 到 ~/.openclaw/bin/<skill-name>，幂等重建。
# agent 调 `<skill> <cmd>` 即可，零路径拼接（治弱模型拼错绝对路径）。
#
# 调用方：
#   apply-addons.sh       → 对公共 skills/ 暴露
#   crew-workspaces.sh    → 对各 crew crews/<id>/skills/ 暴露
#   setup-crew.sh         → 跑完 sync_crew_skills 后调
#
# 设计要点：
#   - bin 目录幂等建：mkdir -p
#   - symlink 幂等重建：ln -sfn 处理现存 symlink / 真文件 / 不存在 三种态
#     （-n 不解引用现存 symlink，避免把链 target 改成目录链套链）
#   - 仅扫顶层同名 wrapper <skill>/<skill>.sh；不带 wrapper 的 skill 不动
#     （纯指导 skill / 多并列脚本 skill 未加 wrapper，保持现状）
#   - PATH 注入：把 ~/.openclaw/bin 加进 ~/.zshrc / ~/.bashrc，幂等追加

OPENCLAW_BIN_DIR="${OPENCLAW_BIN_DIR:-$HOME/.openclaw/bin}"

# 把一个 skill 根目录下所有顶层 wrapper 暴露到 ~/.openclaw/bin/
#   $1  skills_root  skill 集合根目录（如 skills/ 或 crews/main/skills/）
expose_skill_wrappers() {
  local skills_root="$1"
  [ -d "$skills_root" ] || return 0
  mkdir -p "$OPENCLAW_BIN_DIR"

  local skill_dir=""
  local skill_name=""
  local wrapper=""
  local exposed=0
  for skill_dir in "$skills_root"/*/; do
    [ -d "$skill_dir" ] || continue
    skill_name="$(basename "$skill_dir")"
    # 跳过 _shared 等以下划线开头的辅助目录（不是 skill）
    case "$skill_name" in
      _*) continue ;;
    esac
    wrapper="$skill_dir${skill_name}.sh"
    [ -f "$wrapper" ] || continue
    ln -sfn "$wrapper" "$OPENCLAW_BIN_DIR/$skill_name"
    exposed=$((exposed + 1))
  done

  [ "$exposed" -gt 0 ] && echo "  ✅ exposed $exposed wrapper(s) → ~/.openclaw/bin (from $(basename "$skills_root"))"
}

# 把 ~/.openclaw/bin 加进 shell rc 的 PATH（幂等）
# 仅在源码部署跑：Docker 走 COPY，容器内 PATH 由 entrypoint 自管，不调本函数。
ensure_openclaw_bin_in_path() {
  mkdir -p "$OPENCLAW_BIN_DIR"
  local marker='# wiseflow skill wrappers (D21)'
  local line="export PATH=\"\$HOME/.openclaw/bin:\$PATH\"  $marker"

  local rc_file=""
  for rc_file in "$HOME/.zshrc" "$HOME/.bashrc"; do
    # rc 不存在时只建 bashrc（zshrc 由 zsh 自管建），但本机已用 zsh 则建之
    [ -f "$rc_file" ] || continue
    if grep -qF '.openclaw/bin' "$rc_file" 2>/dev/null; then
      continue
    fi
    printf '\n%s\n' "$line" >> "$rc_file"
    echo "  ✅ Added ~/.openclaw/bin to PATH in $(basename "$rc_file")"
  done
}
