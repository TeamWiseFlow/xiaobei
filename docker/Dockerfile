# syntax=docker/dockerfile:1
# xiaobei Docker image
#
# The build intentionally reuses the same lower-level installation scripts as
# scripts/install.sh.  It differs only where a container has no service manager:
# CI supplies the pinned source tree, Docker builds immutable application files,
# and the entrypoint initializes the writable runtime state on first launch.

FROM node:24-bookworm AS xiaobei-build

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/root \
    OPENCLAW_HOME=/root/.openclaw \
    NPM_CONFIG_REGISTRY=https://registry.npmmirror.com

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git openssl \
    python3 python3-pip python3-venv \
    libasound2 libdbus-1-3 libgtk-3-0 libxt6 \
    fonts-liberation fonts-noto-cjk \
    xvfb fluxbox x11vnc novnc websockify \
    && rm -rf /var/lib/apt/lists/*

RUN corepack enable && corepack prepare pnpm@10.30.2 --activate

WORKDIR /opt/xiaobei

# openclaw/ is injected at the commit pinned by openclaw.version before either
# local builds or the GitHub Actions image build.  Its .git metadata is retained
# because apply-addons.sh applies the maintained patch series with git --3way.
COPY . /opt/xiaobei

RUN test -d /opt/xiaobei/openclaw \
    && test -d /opt/xiaobei/openclaw/.git \
    && test -x /opt/xiaobei/scripts/docker-bootstrap.sh \
    && NODE_OPTIONS="--max-old-space-size=4096" /opt/xiaobei/scripts/docker-bootstrap.sh \
    && install -d /opt/xiaobei/runtime-seed/openclaw \
    && cp -a /root/.openclaw/. /opt/xiaobei/runtime-seed/openclaw/

FROM xiaobei-build AS xiaobei-runtime

COPY docker-entrypoint.sh /usr/local/bin/xiaobei-entrypoint
RUN chmod 0755 /usr/local/bin/xiaobei-entrypoint

# Both directories contain credentials and platform login state.  The
# entrypoint initializes empty named volumes and empty bind mounts from
# /opt/xiaobei/runtime-seed instead of relying on Docker's volume-copy detail.
VOLUME ["/root/.openclaw", "/root/.camoufox-cli"]

EXPOSE 18789 6080
ENTRYPOINT ["/usr/local/bin/xiaobei-entrypoint"]
