#!/usr/bin/env bash
# Build the immutable xiaobei application layer.
#
# This is deliberately not a wrapper around install.sh: image builds must not
# fetch/reset repositories, ask for API keys, or install a host daemon. It does
# reuse the same lower-level provisioning scripts used by install.sh so patches,
# crews, skills, wrappers, and dependency installation stay in one code path.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
OPENCLAW_CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-$OPENCLAW_HOME/openclaw.json}"

[ -d "$PROJECT_ROOT/openclaw/.git" ] || {
  echo "Docker build requires the pinned openclaw checkout (including .git)." >&2
  exit 1
}

mkdir -p "$OPENCLAW_HOME"
cp "$PROJECT_ROOT/config-templates/openclaw.json" "$OPENCLAW_CONFIG_PATH"
cp "$PROJECT_ROOT/config/daemon.env.template" "$OPENCLAW_HOME/daemon.env"
cp "$PROJECT_ROOT/config/.env.template" "$OPENCLAW_HOME/.env"
chmod 600 "$OPENCLAW_HOME/daemon.env" "$OPENCLAW_HOME/.env"

# The fork is the browser CLI used by the installed skills. Its own build and
# Firefox download are idempotent, matching the browser step in apply-addons.
"$PROJECT_ROOT/patches/camoufox-cli/build.sh"

# apply-addons is the shared installation core: reset/apply patches, install
# awada and skill dependencies, create crew workspaces, generate wrappers, and
# compile the patched OpenClaw distribution. Docker has no service to restart.
"$PROJECT_ROOT/scripts/apply-addons.sh" --force --no-restart

# Pre-install the openclaw-weixin channel plugin so first launch can go straight
# to QR login.  Switches stay off here (--no-enable); the entrypoint flips them
# on first launch, then runs weixin-qr.mjs to print the binding QR code.
"$PROJECT_ROOT/scripts/install-weixin-channel.sh" --no-enable

# Docker needs the gateway reachable through the published localhost port. Do
# not persist a token in the image; entrypoint creates one on first launch.
OPENCLAW_CONFIG_PATH="$OPENCLAW_CONFIG_PATH" node - <<'NODE'
const fs = require('fs');
const path = process.env.OPENCLAW_CONFIG_PATH;
const config = JSON.parse(fs.readFileSync(path, 'utf8'));
config.gateway = { ...(config.gateway || {}), bind: 'lan' };
config.gateway.auth = { ...(config.gateway.auth || {}), mode: 'token' };
delete config.gateway.auth.token;
fs.writeFileSync(path, `${JSON.stringify(config, null, 2)}\n`);
NODE

echo "[docker-bootstrap] immutable application layer prepared"
