#!/bin/bash
# install-wecom-channel.sh - install and enable the WeCom OpenClaw channel plugin
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
PIN_FILE="$PROJECT_ROOT/openclaw-weixin.version.json"
OPENCLAW_CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-$HOME/.openclaw/openclaw.json}"

if [ "${WISEFLOW_CONFIRM_WECOM_INSTALL:-}" != "confirmed" ]; then
  echo "ERROR: WeCom plugin install requires explicit confirmation."
  echo "Run with WISEFLOW_CONFIRM_WECOM_INSTALL=confirmed after the user confirms installation."
  exit 1
fi

if [ ! -f "$OPENCLAW_CONFIG_PATH" ]; then
  echo "ERROR: openclaw config not found: $OPENCLAW_CONFIG_PATH"
  exit 1
fi

if [ ! -f "$PIN_FILE" ]; then
  echo "ERROR: pin file not found: $PIN_FILE"
  exit 1
fi

pin_values="$(node -e '
  const fs = require("fs");
  const p = process.argv[1];
  const c = JSON.parse(fs.readFileSync(p, "utf8"));
  const entry = c["wecom-openclaw-cli"] || {};
  const validPackage = /^@[a-z0-9._-]+\/[a-z0-9._-]+$/;
  const validVersion = /^\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9._-]+)?$/;
  const validIntegrity = /^sha512-[A-Za-z0-9+/]+={0,2}$/;
  if (!validPackage.test(entry.package || "")) throw new Error("wecom package invalid");
  if (!validVersion.test(entry.version || "")) throw new Error("wecom version invalid");
  if (!validIntegrity.test(entry.integrity || "")) throw new Error("wecom integrity invalid");
  console.log([entry.package, entry.version, entry.integrity].join("\t"));
' "$PIN_FILE")"
IFS=$'\t' read -r WECOM_PACKAGE WECOM_VERSION WECOM_INTEGRITY <<< "$pin_values"

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "Installing pinned WeCom OpenClaw channel plugin: $WECOM_PACKAGE@$WECOM_VERSION"
pack_output="$(npm pack "$WECOM_PACKAGE@$WECOM_VERSION" --json --pack-destination "$TMP_DIR")"
package_file="$(node -e '
  const fs = require("fs");
  const payload = JSON.parse(fs.readFileSync(0, "utf8"));
  if (!Array.isArray(payload) || payload.length !== 1 || !payload[0].filename) {
    throw new Error("unexpected npm pack output");
  }
  console.log(payload[0].filename);
' <<< "$pack_output")"
package_file="$TMP_DIR/$package_file"
package_integrity="$(node -e '
  const fs = require("fs");
  const crypto = require("crypto");
  const file = process.argv[1];
  console.log("sha512-" + crypto.createHash("sha512").update(fs.readFileSync(file)).digest("base64"));
' "$package_file")"

if [ "$package_integrity" != "$WECOM_INTEGRITY" ]; then
  echo "ERROR: integrity mismatch for $package_file"
  exit 1
fi

npx -y "$package_file" install

node -e '
  const fs = require("fs");
  const path = process.argv[1];
  const backup = path + ".bak-" + new Date().toISOString().replace(/[-:.TZ]/g, "");
  const tmp = path + ".tmp";
  const c = JSON.parse(fs.readFileSync(path, "utf8"));
  c.plugins = c.plugins || {};
  c.plugins.entries = c.plugins.entries || {};
  c.plugins.entries.wecom = { ...(c.plugins.entries.wecom || {}), enabled: true };
  c.channels = c.channels || {};
  c.channels.wecom = { ...(c.channels.wecom || {}), enabled: true };
  fs.copyFileSync(path, backup);
  fs.writeFileSync(tmp, JSON.stringify(c, null, 2) + "\n", { mode: 0o600 });
  fs.renameSync(tmp, path);
  console.log(JSON.stringify({ updated: path, backup }, null, 2));
' "$OPENCLAW_CONFIG_PATH"

echo "WeCom channel plugin installed and enabled. Gateway restart is required before binding verification."
