#!/usr/bin/env bash
# Install the pinned deck-render runtime shared by source, tarball and Docker paths.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$ROOT/crews/content-producer/skills/expert-video/tools/deck-render"
BROWSER_DIR="$TOOL/.browsers"
MARKER="$TOOL/.deck-render-browser"
SKIP_BROWSER=false

for arg in "$@"; do
  case "$arg" in
    --skip-browser) SKIP_BROWSER=true ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ ! -f "$TOOL/package.json" ]; then
  echo "deck-render package.json missing: $TOOL" >&2
  exit 1
fi
for bin in node npm; do
  command -v "$bin" >/dev/null 2>&1 || { echo "deck-render needs $bin" >&2; exit 1; }
done
node -e 'if (+process.versions.node.split(".")[0] < 22) process.exit(1)' || {
  echo "deck-render needs Node >=22" >&2
  exit 1
}

font_ready() {
  if command -v fc-list >/dev/null 2>&1; then
    local families
    families="$(fc-list : family)"
    [[ "$families" == *'Noto Sans CJK SC'* ]] && return 0
  fi
  [ "$(uname -s)" = Darwin ] && \
    { [ -f "$HOME/Library/Fonts/NotoSansCJKsc-Regular.otf" ] || \
      [ -f "/Library/Fonts/NotoSansCJKsc-Regular.otf" ]; }
}

need_ffmpeg=false
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  need_ffmpeg=true
fi
if ! font_ready || [ "$need_ffmpeg" = true ]; then
  case "$(uname -s)" in
    Linux)
      command -v apt-get >/dev/null 2>&1 || { echo "Install FFmpeg and Noto Sans CJK SC with your system package manager" >&2; exit 1; }
      apt=(apt-get)
      if [ "$(id -u)" -ne 0 ]; then
        command -v sudo >/dev/null 2>&1 || { echo "sudo required to install FFmpeg/CJK fonts" >&2; exit 1; }
        apt=(sudo apt-get)
      fi
      packages=(fontconfig fonts-noto-cjk)
      [ "$need_ffmpeg" = true ] && packages+=(ffmpeg)
      "${apt[@]}" update
      "${apt[@]}" install -y "${packages[@]}"
      fc-cache -f
      ;;
    Darwin)
      command -v brew >/dev/null 2>&1 || { echo "Homebrew required for FFmpeg/Noto Sans CJK SC" >&2; exit 1; }
      [ "$need_ffmpeg" = true ] && brew install ffmpeg
      font_ready || brew install --cask font-noto-sans-cjk-sc
      ;;
    *) echo "Install FFmpeg and Noto Sans CJK SC before using deck-render" >&2; exit 1 ;;
  esac
fi
for bin in ffmpeg ffprobe; do
  command -v "$bin" >/dev/null 2>&1 || { echo "deck-render needs $bin" >&2; exit 1; }
done
font_ready || { echo "Noto Sans CJK SC still unavailable after installation" >&2; exit 1; }

# apply-addons.sh also installs per-skill packages in source/Docker builds; the
# tarball path does not run it. Verify the exact versions here in every path.
if ! node - "$TOOL" <<'NODE'
const fs = require('fs');
const path = require('path');
const tool = process.argv[2];
const deps = require(path.join(tool, 'package.json')).dependencies;
for (const [name, version] of Object.entries(deps)) {
  const installed = path.join(tool, 'node_modules', name, 'package.json');
  if (!fs.existsSync(installed) || require(installed).version !== version) process.exit(1);
}
NODE
then
  echo "Installing pinned deck-render npm packages..."
  (cd "$TOOL" && npm install --omit=dev --no-audit --no-fund \
    --registry="${NPM_CONFIG_REGISTRY:-https://registry.npmmirror.com}")
fi

if [ "$SKIP_BROWSER" = true ]; then
  echo "deck-render packages/fonts ready; browser skipped by request"
  exit 0
fi

browser=""
if [ -f "$MARKER" ]; then
  IFS=$'\t' read -r version relative < "$MARKER" || true
  if [ "$version" = "1.61.1" ] && [ -n "${relative:-}" ]; then
    browser="$TOOL/$relative"
    [ -x "$browser" ] || browser=""
  fi
fi

if [ -z "$browser" ]; then
  echo "Installing pinned Playwright Chromium headless shell..."
  mkdir -p "$BROWSER_DIR"
  PLAYWRIGHT_BROWSERS_PATH="$BROWSER_DIR" \
    "$TOOL/node_modules/.bin/playwright-core" install chromium-headless-shell
  browser="$(find "$BROWSER_DIR" -type f \( -name chrome-headless-shell -o -name headless_shell \) -print -quit)"
  [ -n "$browser" ] && [ -x "$browser" ] || { echo "Playwright browser install produced no executable" >&2; exit 1; }
  printf '1.61.1\t%s\n' "${browser#"$TOOL/"}" > "$MARKER"
fi
"$browser" --version >/dev/null || { echo "Chromium headless shell cannot start: $browser" >&2; exit 1; }
echo "deck-render ready: HyperFrames 0.8.50, Playwright Chromium, Noto Sans CJK SC"
