#!/bin/bash
# crew-workspaces.sh - shared helpers for deploying crew template directories

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

seed_builtin_crew_workspaces() {
  local crews_dir="$1"
  local openclaw_home="$2"
  local builtin_crews="${3:-main it-engineer}"
  local agent_id=""
  local source_dir=""
  local dest_dir=""

  mkdir -p "$openclaw_home"

  for agent_id in $builtin_crews; do
    source_dir="$crews_dir/$agent_id"
    dest_dir="$openclaw_home/workspace-$agent_id"

    [ -d "$source_dir" ] || continue

    if [ -d "$dest_dir" ]; then
      echo "  ⚠️  workspace-$agent_id already exists, skipping template bootstrap"
      continue
    fi

    copy_crew_template_contents "$source_dir" "$dest_dir"
    echo "  ✅ workspace-$agent_id bootstrapped from built-in template"
  done
}
