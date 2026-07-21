#!/bin/bash
# build-image.sh — wiseflow-client 镜像构建辅助
#
# 职责：检出 openclaw 引擎源码（按 openclaw.version 锁定）→ 注入到 build 上下文 →
#   docker build。install.sh 是给裸机装的；镜像构建复用 docker-bootstrap.sh 的安装语义。
#
# Phase 0 骨架：检出 + build 流程就位，Dockerfile 阶段 3-4 待 Phase 6-7 填实。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# 读 openclaw 版本锁
source openclaw.version
echo "[build] openclaw $OPENCLAW_VERSION @ $OPENCLAW_COMMIT"

# 检出引擎源码（.gitignore 排除 openclaw/，build 期需要）
if [ ! -d openclaw ] || ! git -C openclaw rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[build] cloning openclaw..."
  git clone https://github.com/openclaw/openclaw openclaw
fi
git -C openclaw fetch --depth=1 origin "$OPENCLAW_COMMIT"
git -C openclaw checkout "$OPENCLAW_COMMIT"

# 镜像 tag
TAG="${IMAGE_TAG:-xiaobei:local}"
echo "[build] building $TAG"

docker build \
  --build-arg OPENCLAW_VERSION="$OPENCLAW_VERSION" \
  --build-arg OPENCLAW_COMMIT="$OPENCLAW_COMMIT" \
  -t "$TAG" \
  .

echo "[build] done: $TAG"
echo "[run]   AWK_API_KEY=xxx IMAGE=$TAG docker compose up -d"
