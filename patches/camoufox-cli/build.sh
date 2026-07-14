#!/bin/bash
# Build the wiseflow fork of camoufox-cli and install it globally,
# replacing any upstream `camoufox-cli` on $PATH.
#
# Run from anywhere:  patches/camoufox-cli/build.sh
# Re-run after editing fork source. Idempotent in effect.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "→ [camoufox-cli fork] installing deps (incl. devDeps for tsc)..."
npm install

echo "→ [camoufox-cli fork] building dist/..."
npm run build

echo "→ [camoufox-cli fork] installing globally (replaces upstream)..."
npm install -g .

echo "✅ forked camoufox-cli installed. Verify with:"
echo "    camoufox-cli --help 2>&1 | head   # should list upload / identity"
echo "    npm ls -g camoufox-cli            # version 0.6.2-wiseflow.1"
