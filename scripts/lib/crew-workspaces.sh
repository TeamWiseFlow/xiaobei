#!/bin/bash
# crew-workspaces.sh - shared helpers for deploying crew template directories

# skill-wrappers.sh 提供 expose_skill_wrappers（D21 wrapper 暴露到 ~/.openclaw/bin）
# 用 lazy source 避免循环依赖：仅在 sync_crew_skills 调用时确保已加载
_skill_wrappers_sourced() {
  type expose_skill_wrappers &>/dev/null
}

copy_crew_template_contents() {
  local source_dir="$1"
  local dest_dir="$2"

  if [ ! -d "$source_dir" ]; then
    echo "❌ Crew template directory not found: $source_dir" >&2
    return 1
  fi

  mkdir -p "$dest_dir"
  cp -R "$source_dir/." "$dest_dir/"
}

# 同步 crew 专属 skill 到已部署 workspace（spec §2.3）。
#   src_crew：仓库 crews/<id>/
#   dest_ws：~/.openclaw/workspace-<id>/
# 语义：
#   - 对仓库里每个合法 skill（含 SKILL.md），rm -rf + ln -s 软链到 dest_ws/skills/<name>/
#   - 不删除 dest_ws/skills/ 里仓库没有的 skill（保留部署实例自定义 skill）
#   - 不碰 dest_ws 下的 AGENTS.md / TOOLS.md / Memory 等（保留用户编辑）
#   - node 依赖不在此装：由 apply-addons.sh per-skill npm install 写进仓内 skill 目录，
#     Node 从脚本 realpath 向上解析命中 skill 自己的 node_modules
# 软链而非拷贝：skill 在仓里改完即生效，运行实例无需重跑 setup。
# openclaw skill loader 跟随软链（local-loader.ts readdirSync isDirectory + realpathSync）。
# 幂等：dest 若是旧拷贝留下的真目录，rm -rf 清掉再 ln -s；已是正确软链则重建无害。
sync_crew_skills() {
  local src_crew="$1"
  local dest_ws="$2"
  local src_skills="$src_crew/skills"
  local dest_skills="$dest_ws/skills"

  [ -d "$src_skills" ] || return 0
  mkdir -p "$dest_skills"

  local skill_dir=""
  local skill_name=""
  local synced=0
  for skill_dir in "$src_skills"/*/; do
    [ -d "$skill_dir" ] || continue
    [ -f "${skill_dir}SKILL.md" ] || continue
    skill_name="$(basename "$skill_dir")"
    rm -rf "$dest_skills/$skill_name"
    ln -s "${skill_dir%/}" "$dest_skills/$skill_name"
    synced=$((synced + 1))
  done

  [ "$synced" -gt 0 ] && echo "  ✅ synced $synced crew skill(s) → $(basename "$dest_ws")"

  # D21 wrapper 暴露：把 src_skills 下顶层 wrapper 暴露到 ~/.openclaw/bin/
  # （不走 dest_ws/skills，因 dest 是软链、链回 src；扫描 src 直接命中真 wrapper 文件）
  if ! _skill_wrappers_sourced; then
    local _script_dir
    _script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    [ -f "$_script_dir/skill-wrappers.sh" ] && source "$_script_dir/skill-wrappers.sh"
  fi
  type expose_skill_wrappers &>/dev/null && expose_skill_wrappers "$src_skills"
}

ensure_soul_crew_type() {
  local soul_file="$1"
  local crew_type="$2"

  [ -f "$soul_file" ] || return 0

  case "$crew_type" in
    internal|external) ;;
    *)
      echo "❌ Invalid crew-type: $crew_type" >&2
      return 1
      ;;
  esac

  if grep -qi '^crew-type:' "$soul_file" 2>/dev/null; then
    sed -i.bak "s/^[Cc]rew-[Tt]ype:.*$/crew-type: $crew_type/" "$soul_file"
    rm -f "$soul_file.bak"
  else
    printf '\ncrew-type: %s\n' "$crew_type" >> "$soul_file"
  fi
}
