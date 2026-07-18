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
    # camoufox (Firefox) 运行时依赖：GTK3 + dbus + 字体 + 音频 stub
    libgtk-3-0 libdbus-1-3 libxt6 libasound2 \
    fonts-liberation fonts-noto-cjk \
    # 虚拟显示 + VNC 远程查看栈（camoufox 有头登录场景，用户通过浏览器访问 :6080 看容器内界面）
    xvfb fluxbox x11vnc novnc websockify \
    && rm -rf /var/lib/apt/lists/*
# corepack 默认从 registry.npmjs.org 下载 pnpm，国内连不上会 ECONNRESET。
# 配淘宝 npm 镜像走国内线路。
RUN npm config set registry https://registry.npmmirror.com && \
    corepack enable && corepack prepare pnpm@latest --activate
# camoufox-cli 全局 + 下载 Camoufox Firefox 二进制
# 不用 --with-deps：该 flag 内部 spawnSync sudo apt-get，容器内无 sudo 会 ENOENT。
# camoufox 运行时系统依赖（libdbus/gtk 等）由 apt 段统一装，camoufox-cli 自身只下 Firefox + GeoIP。
RUN npm install -g camoufox-cli@0.6.2 && camoufox-cli install
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
# openclaw 的 tsdown 编译吃内存，Node 默认 ~2GB 堆不够会 OOM。
# 给 4GB 堆上限（GH Action runner 7GB RAM，够用）。
RUN NODE_OPTIONS=--max-old-space-size=4096 pnpm build
# TODO(Phase 6): ui:build（若 openclaw 含 UI 子包）
# RUN pnpm --filter ui build
# 装 openclaw-weixin 插件（按 openclaw-weixin.version.json 锁定版本，在线装）。
# 必须用 openclaw 自己的 `plugins install` 命令注册，而不是 npx cli install——
# 后者只落文件不注册插件表，gateway 检测到配置 enabled 但未注册会弹交互式安装 prompt，
# 容器非 TTY 环境下 channels login 挂死，二维码出不来。
# 配淘宝 npm 镜像避 registry.npmjs.org 连不上。
RUN npm config set registry https://registry.npmmirror.com && \
    _plugin_version="$(node -e 'const c=require("/opt/openclaw/openclaw-weixin.version.json");console.log(c["openclaw-weixin"].version)')" && \
    node scripts/run-node.mjs plugins install "@tencent-weixin/openclaw-weixin@${_plugin_version}"

# ── 阶段 3: wiseflow-layer ────────────────────────────────────────────────────
# COPY skills/crews/config → 组织成 /root/.openclaw/ 运行态；统一 npm/pip install；
# 编译改火山的 img-gen gen.py；生成 camoufox 冻结指纹模板。
FROM build AS wiseflow-layer
RUN mkdir -p /root/.openclaw
# Docker 不跑 setup-crew.sh，故不生成 OFB_ENV.md。AGENTS.md 已改为环境
# 自感知（检测 /.dockerenv → 用固定路径 /opt/openclaw + /root/.openclaw），
# 无需 OFB_ENV.md。源码部署仍由 setup-crew.sh §4 在此基础上合并 skills 过滤 / 路径规范化；
# Docker 不跑 setup-crew.sh，直接用模板（content-producer 已在模板 agents.list 预注册）。
# Docker 与源码部署同源：均从 config-templates/openclaw.json 派生（单源）。
COPY config-templates/openclaw.json /root/.openclaw/openclaw.json
# daemon.env 模板（gateway 运维变量：超时/bonjour/DISPLAY）+ .env 模板（技能密钥）
# entrypoint 首次启动时分别拷到 /root/.openclaw/ 下，用户编辑 .env 填 API key
COPY config/daemon.env.template /root/.openclaw/daemon.env.template
COPY config/.env.template /root/.openclaw/.env.template
# 公共技能：COPY 到 /root/.openclaw/skills（apply-addons.sh 在源码部署时做软链，
# Docker 走 COPY，容器内无 ~/wiseflow 源码故软链无意义）
COPY skills/ /root/.openclaw/skills/
# weixin-qr.mjs：容器内自动出 weixin 二维码，绕开 channels login 的交互式 prompt
COPY scripts/weixin-qr.mjs /opt/openclaw/scripts/weixin-qr.mjs
# Crew workspace：COPY 整个 crews/<id>/ 到 /root/.openclaw/workspace-<id>/（含
# AGENTS.md/SOUL.md/IDENTITY.md/MEMORY.md/TOOLS.md/USER.md/HEARTBEAT.md/BUILTIN_SKILLS/
# DENIED_SKILLS/skills/ 等。等价 setup-crew.sh 的 copy_crew_template_contents）。
# 源码部署时 setup-crew.sh 跑 cp -R crews/<id>/. → workspace-<id>/；Docker 不跑 setup-crew.sh，
# 走 COPY。sales-cs 默认不 COPY（用户启用时单独处理）。
COPY crews/main/ /root/.openclaw/workspace-main/
COPY crews/content-producer/ /root/.openclaw/workspace-content-producer/
COPY crews/it-engineer/ /root/.openclaw/workspace-it-engineer/
# it-engineer OFB_ENV.md：Docker 路径固定，直接 bake（等价 setup-crew.sh §5 的 Docker 分支）
RUN mkdir -p /root/.openclaw/workspace-it-engineer && \
    cat > /root/.openclaw/workspace-it-engineer/OFB_ENV.md << 'OEBEOF'
# wiseflow 环境信息（Docker 部署，由 Dockerfile bake，勿手动编辑）

- **部署环境**：Docker 容器
- **wiseflow 项目路径**：/opt/openclaw
- **openclaw 子目录**：/opt/openclaw/openclaw
- **配置文件**：/root/.openclaw/openclaw.json

## 环境变量文件

### 是什么

gateway 进程启动时从此文件读取环境变量，注入到所有 Agent 的运行时环境中。像 API Key、超时参数这类配置，不能硬编码在代码或 openclaw.json 里，必须放在这里。

### 文件位置

`/root/.openclaw/daemon.env`

### 写入格式

`KEY=value`（systemd EnvironmentFile 格式，一行一个；Docker entrypoint source 加载）

### 何时编辑

当你需要为某个技能添加新的环境变量时（如新的 API Key、新的超时配置）。典型场景：

- 用户要求启用某个需要 API Key 的技能（如 email-ops 需要 SMTP 变量、pexels-footage 需要 PEXELS_API_KEY）
- IT Engineer 需要调整 gateway 运行时参数
- 新增 Crew 模板依赖了新的外部服务

### 注意事项

1. **写入前先检查**：grep 确认该 key 是否已存在，避免重复写入
2. **写入后必须重启**：编辑 daemon.env 后需 `docker restart <容器名>` 生效（等价裸机 systemctl --user restart）
3. **禁止内联**：不要在 exec 调用中写 `KEY=value python3 script.py`，这会导致 allowlist miss

## 常用操作命令

```bash
# 重启 gateway（生效 daemon.env 改动）
docker restart <容器名>

# 重新应用 addons（源码部署用，Docker 不跑）
# cd /opt/openclaw && ./scripts/apply-addons.sh

# 直接调用上游 CLI（如需）
cd /opt/openclaw/openclaw && pnpm openclaw <subcommand>
```
OEBEOF
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
# 同时把 gateway.bind 从 loopback 改成 0.0.0.0：容器需对外暴露端口，loopback 只听 127.0.0.1 宿主机 curl 不通。
RUN node -e "\
  const fs=require('fs');const p='/root/.openclaw/openclaw.json';\
  const c=JSON.parse(fs.readFileSync(p,'utf8'));\
  c.plugins=c.plugins||{};c.plugins.load=c.plugins.load||{};\
  c.plugins.load.paths=Array.isArray(c.plugins.load.paths)?c.plugins.load.paths:[];\
  c.plugins.load.paths=c.plugins.load.paths.filter(x=>!x.endsWith('/awada'));\
  c.plugins.load.paths.push('/opt/openclaw/awada');\
  c.plugins.entries=c.plugins.entries||{};\
  if(!c.plugins.entries.awada)c.plugins.entries.awada={enabled:false};\
  c.gateway=c.gateway||{};\
  c.gateway.bind='lan';\
  c.gateway.auth=c.gateway.auth||{};\
  c.gateway.auth.mode='token';\
  c.gateway.auth.token='wiseflow-gateway-token';\
  c.plugins.entries=c.plugins.entries||{};\
  c.plugins.entries['openclaw-weixin']=c.plugins.entries['openclaw-weixin']||{};\
  c.plugins.entries['openclaw-weixin'].enabled=true;\
  c.channels=c.channels||{};\
  c.channels['openclaw-weixin']=c.channels['openclaw-weixin']||{};\
  c.channels['openclaw-weixin'].enabled=true;\
  c.session=c.session||{};\
  c.session.dmScope='per-channel-peer';\
  if(!Array.isArray(c.bindings))c.bindings=[];\
  if(!c.bindings.some(b=>b?.agentId==='main'&&b?.match?.channel==='openclaw-weixin'))\
    c.bindings.push({agentId:'main',comment:'openclaw-weixin -> Main Agent onboarding entry',match:{channel:'openclaw-weixin'}});\
  fs.writeFileSync(p,JSON.stringify(c,null,2)+'\n');"
# 把各 crew 专属 skill + 公共 skill 合并进每个 agent 的 skills 字段，排除 DENIED_SKILLS。
# 源码部署由 setup-crew.sh → resolve_agent_skills_json() 做 5 步合并（基线+addon+BUILTIN-DENIED+workspace）；
# Docker 不跑 setup-crew.sh，在此用 node 扫描 skills/ 和 workspace-*/skills/ 目录，合并去重，
# 读 workspace-*/DENIED_SKILLS 从最终列表排除，写回 openclaw.json。
# 排除 .DS_Store / _shared / *.md 等非 skill 条目。
RUN node -e "\
  const fs=require('fs'),path=require('path');\
  const p='/root/.openclaw/openclaw.json';\
  const c=JSON.parse(fs.readFileSync(p,'utf8'));\
  const isSkill=(n)=>n&&!n.startsWith('.')&&!n.startsWith('_')&&!n.endsWith('.md');\
  const ls=(d)=>fs.existsSync(d)?fs.readdirSync(d).filter(isSkill):[];\
  const publicSkills=ls('/root/.openclaw/skills');\
  const crewSkills={};const denied={};\
  for(const wdir of fs.readdirSync('/root/.openclaw').filter(n=>n.startsWith('workspace-'))){\
    const crewId=wdir.replace('workspace-','');\
    const sdir=path.join('/root/.openclaw',wdir,'skills');\
    crewSkills[crewId]=ls(sdir);\
    const df=path.join('/root/.openclaw',wdir,'DENIED_SKILLS');\
    if(fs.existsSync(df)){denied[crewId]=fs.readFileSync(df,'utf8').split(/\r?\n/).map(s=>s.trim()).filter(s=>s&&!s.startsWith('#'));}\
  }\
  for(const a of (c.agents?.list||[])){\
    const crewId=a.id;\
    const existing=new Set(a.skills||[]);\
    for(const s of publicSkills)existing.add(s);\
    for(const s of (crewSkills[crewId]||[]))existing.add(s);\
    const dn=denied[crewId]||[];\
    a.skills=Array.from(existing).filter(s=>!dn.includes(s)).sort();\
  }\
  fs.writeFileSync(p,JSON.stringify(c,null,2)+'\n');\
  console.log('[wiseflow-layer] skills merged + DENIED_SKILLS excluded');"
# 预装带外部 npm 依赖的 skill（rss-reader / wx-mp-hunter / proactive-send）。
# 与 scripts/apply-addons.sh 的 per-skill 扫描同源：per-skill npm install --omit=dev。
# COPY 已在上一步落地到 /root/.openclaw/ 下，这里进每个目录装 node_modules。
RUN for d in /root/.openclaw/skills/*/  /root/.openclaw/workspace-*/skills/*/; do \
      [ -f "$d/package.json" ] || continue; \
      echo "[npm] $(dirname "$d")"; \
      (cd "$d" && npm install --omit=dev --no-audit --no-fund --loglevel=warn || \
       echo "  WARN: npm install failed for $d"); \
    done
# Phase 4.5.5: camoufox 指纹模板——改为运行时 lazy 生成（见 docker-entrypoint.sh）。
# build 期不跑 camoufox-cli：Firefox sandbox 在 docker build 默认 cap 下 EPERM，
# 且 docker build 不支持 --cap-add SYS_ADMIN。模板在容器首次启动时生成，
# 生成后落 /root/.openclaw/logins/_template/（VOLUME 挂载，跨容器保留）。
RUN mkdir -p /root/.openclaw/logins/_template && \
    echo "[wiseflow-layer] camoufox fingerprint template deferred to entrypoint"

# ── 阶段 4: runtime ───────────────────────────────────────────────────────────
# 复制产物 + 装 openclaw-weixin 插件(tgz) + ENTRYPOINT
FROM wiseflow-layer AS runtime
# TODO(Phase 6): 装 openclaw-weixin 插件 tgz（按 openclaw-weixin.version.json）
# COPY openclaw-weixin-*.tgz /tmp/ && npm install -g /tmp/openclaw-weixin-*.tgz
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
# 持久化卷声明（compose 里用 named volume 挂，好备份好迁移）：
#   /root/.openclaw       登录态/cookie 中央仓 + 各 session 指纹 profile（首选位置）
#   /root/.camoufox-cli   camoufox-cli 配置 + 默认 profile dir + geoip/db 运行时缓存
# 两块都挂卷，避免容器重建丢登录态/指纹/缓存。运行时 profile dir 推荐指到
# /root/.openclaw/logins/<session>/profile/（上一卷的子路径，单卷管登录+指纹）；
# /root/.camoufox-cli 这块兜底：非持久 session 的默认 profile、geoip db 等也留得住。
VOLUME /root/.openclaw
VOLUME /root/.camoufox-cli
EXPOSE 18789
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
