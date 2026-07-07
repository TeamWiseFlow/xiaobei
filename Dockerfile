# syntax=docker/dockerfile:1
# wiseflow-client Dockerfile（多阶段，bake 出 ~/.openclaw 运行态）
#
# Phase 0 骨架：阶段 1-2 基本可构建；阶段 3-4 含 TODO，待 Phase 6-7
# crew/skill 扁平化 + img-gen 改火山 + camoufox 指纹模板落地后填实。
# 详见 docs/client-buildout.md 与 plan §六。

# ── 阶段 1: workspace-deps ────────────────────────────────────────────────────
# Node24 + pnpm + python3 + camoufox Firefox 二进制 + camoufox-cli(npm 全局)
# 不 bake chromium（fallback attach 的是用户本机 Chrome；patchright-core 仅作
# npm 依赖留给 connectOverCDP 驱动）。
FROM node:24-bookworm AS workspace-deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    ca-certificates curl git bash \
    && rm -rf /var/lib/apt/lists/*
RUN corepack enable && corepack prepare pnpm@latest --activate
# camoufox-cli 全局 + 下载 Camoufox Firefox 二进制
RUN npm install -g camoufox-cli@0.6.2 && camoufox-cli install --with-deps
# patchright-core 留作 fallback connectOverCDP 驱动（不 bake chromium）
# 在阶段 2 的 pnpm install 里通过 patches/overrides.sh 注入

# ── 阶段 2: build ─────────────────────────────────────────────────────────────
# COPY openclaw + apply patches（patchright override + 005/006）+ pnpm install + build + ui:build
FROM workspace-deps AS build
WORKDIR /opt/openclaw
# openclaw/ 是 clone 的引擎源码（.gitignore 排除，build 期由 build-image.sh 检出注入）
COPY openclaw/ ./openclaw/
COPY patches/ ./patches/
COPY openclaw.version openclaw-weixin.version.json ./
# TODO(Phase 6): apply patches/overrides.sh（patchright override）+ 005/006
# RUN bash patches/overrides.sh apply
WORKDIR /opt/openclaw/openclaw
RUN pnpm install --frozen-lockfile
RUN pnpm build
# TODO(Phase 6): ui:build（若 openclaw 含 UI 子包）
# RUN pnpm --filter ui build

# ── 阶段 3: wiseflow-layer ────────────────────────────────────────────────────
# COPY skills/crews/config → 组织成 /root/.openclaw/ 运行态；统一 npm/pip install；
# 编译改火山的 img-gen gen.py；生成 camoufox 冻结指纹模板。
FROM build AS wiseflow-layer
RUN mkdir -p /root/.openclaw
# TODO(Phase 7): crews 扁平化后 COPY crews/ → /root/.openclaw/workspace-*/
#   注意：Docker 不跑 setup-crew.sh，故不生成 OFB_ENV.md。AGENTS.md 已改为环境
#   自感知（检测 /.dockerenv → 用固定路径 /opt/openclaw + /root/.openclaw），
#   无需 OFB_ENV.md。源码部署仍由 setup-crew.sh 生成 OFB_ENV.md（路径可变）。
# TODO(Phase 7): skills 公共/私有拆分后 COPY skills/ → /root/.openclaw/skills
COPY config/openclaw.json /root/.openclaw/openclaw.json
# 全仓 Python 依赖（Docker 不跑 apply-addons.sh，需在此 bake）
# 与 scripts/apply-addons.sh 同源（仓根 requirements.txt），使用 aliyun 镜像保持一致
COPY requirements.txt /tmp/wiseflow-requirements.txt
RUN pip3 install --break-system-packages --quiet --no-warn-script-location \
      -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
      -r /tmp/wiseflow-requirements.txt \
    && rm -f /tmp/wiseflow-requirements.txt
# awada channel 插件：COPY 源码 + 预装 ws/zod 运行时依赖（awada 走 relay 网关 HTTP/WS 传输）。
# awada 自己的 node_modules 解析这些依赖，不走 ~/.openclaw/node_modules，故必须装在 awada/ 局部。
COPY awada/ /opt/openclaw/awada/
RUN cd /opt/openclaw/awada && npm install --omit=dev --no-audit --no-fund --loglevel=warn
# 把 awada 插件路径注入 openclaw.json（Docker 不跑 apply-addons.sh，需在此 bake）
RUN node -e "\
  const fs=require('fs');const p='/root/.openclaw/openclaw.json';\
  const c=JSON.parse(fs.readFileSync(p,'utf8'));\
  c.plugins=c.plugins||{};c.plugins.load=c.plugins.load||{};\
  c.plugins.load.paths=Array.isArray(c.plugins.load.paths)?c.plugins.load.paths:[];\
  c.plugins.load.paths=c.plugins.load.paths.filter(x=>!x.endsWith('/awada'));\
  c.plugins.load.paths.push('/opt/openclaw/awada');\
  c.plugins.entries=c.plugins.entries||{};\
  if(!c.plugins.entries.awada)c.plugins.entries.awada={enabled:false};\
  fs.writeFileSync(p,JSON.stringify(c,null,2)+'\n');"
# TODO(Phase 6): 各 skill 的 npm/pip install 统一在此跑
# TODO(Phase 5): img-gen gen.py 改火山生图编译
# Phase 4.5.5: 冻结 camoufox 指纹模板（spike 报告 §"Spike ② D18 落地方式"）
# 一次性 bootstrap：清空 profile dir → 跑一次 about:blank 生成 camoufox-cli.json
# → close。运行时各 agent session cp 此模板到独立 profile dir 用
# （D18：不 fork camoufox-cli；不 bake chromium；每 agent 一 session）。
# --headless 避免依赖 Xvfb 虚拟显示（容器内 build 更稳）。
# close --all 兜底清掉任何残留 daemon/进程，避免 build 上下文污染。
RUN mkdir -p /root/.openclaw/logins/_template && \
    rm -rf /root/.camoufox-cli/profiles/_template && \
    camoufox-cli --session _template --persistent --headless --json open about:blank && \
    camoufox-cli --session _template close; \
    camoufox-cli close --all 2>/dev/null || true; \
    cp /root/.camoufox-cli/profiles/_template/camoufox-cli.json \
       /root/.openclaw/logins/_template/camoufox-cli.json && \
    echo "[wiseflow-layer] camoufox fingerprint template baked to /root/.openclaw/logins/_template"

# ── 阶段 4: runtime ───────────────────────────────────────────────────────────
# 复制产物 + 装 openclaw-weixin 插件(tgz) + ENTRYPOINT
FROM wiseflow-layer AS runtime
# TODO(Phase 6): 装 openclaw-weixin 插件 tgz（按 openclaw-weixin.version.json）
# COPY openclaw-weixin-*.tgz /tmp/ && npm install -g /tmp/openclaw-weixin-*.tgz
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
VOLUME /root/.openclaw
EXPOSE 18789
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
