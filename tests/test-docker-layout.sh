#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

contains() {
  local file="$1" pattern="$2"
  rg -Fq -- "$pattern" "$file" || fail "$file must contain: $pattern"
}

not_contains() {
  local file="$1" pattern="$2"
  if rg -Fq -- "$pattern" "$file"; then
    fail "$file must not contain: $pattern"
  fi
}

# The image must build the same application tree that install.sh configures,
# rather than maintaining a second, hand-written installer in Dockerfile.
contains Dockerfile "COPY . /opt/xiaobei"
contains Dockerfile "scripts/docker-bootstrap.sh"
contains Dockerfile "/opt/xiaobei/runtime-seed/openclaw"
not_contains Dockerfile "wiseflow-client"

# A first launch needs one user-supplied secret only. All mutable data belongs
# to named volumes whose names are part of the public deployment contract.
contains docker-compose.yml "AWK_API_KEY: \${AWK_API_KEY:?"
contains docker-compose.yml "xiaobei-openclaw:/root/.openclaw"
contains docker-compose.yml "xiaobei-camoufox:/root/.camoufox-cli"
not_contains docker-compose.yml "OFB_KEY"
not_contains docker-compose.yml "wiseflow-"

# Entrypoint must restore an empty volume from the baked seed and must never
# bake a predictable gateway credential into the image or command line.
contains docker-entrypoint.sh "/opt/xiaobei/runtime-seed/openclaw"
contains docker-entrypoint.sh "OPENCLAW_GATEWAY_TOKEN"
not_contains docker-entrypoint.sh "wiseflow-gateway-token"

# Production publishing uses the same public xiaobei image name.
contains .github/workflows/release.yml "/xiaobei"

echo "PASS: Docker deployment layout"
