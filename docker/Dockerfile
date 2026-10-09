# xiaobei Docker image — 开箱即用版（v5.6.3+）
#
# 三阶段构建：
#   1. xiaobei-build  基础系统 + Node/pnpm 工具链 + 容器内 Xvfb/VNC/noVNC 软件
#      + 跑 docker-bootstrap.sh 完成"install.sh 装好后"的所有 immutable 层
#      （apply patches / 装 skills+deps / 编译 openclaw / camoufox-cli+Firefox /
#       预装 openclaw-weixin 插件 / 生成 runtime seed）
#   2. xiaobei-runtime  从 build 拷贝产物，只放可执行层 + entrypoint，体积更瘦
#
# 镜像语义：等价于裸机跑完 scripts/install.sh 后的状态——用户只需 docker compose up -d
# 即可启动，唯一要填的 AWK_API_KEY 走环境变量注入，不进镜像层。
#
# openclaw/ 源码树（含 .git 元数据）由 build-image.sh 或 CI 流水线在 docker build 之前
# 注入到仓根，apply-addons.sh 的 git apply --3way 需 .git object store 读补丁头 pre-image blob。

# ════════════════════════════════════════════════════════════════════
# Stage 1: build（装齐 immutable 应用层 + 显示栈软件）
# ════════════════════════════════════════════════════════════════════
# docker buildx multi-arch：基础镜像 node:24-bookworm 自身是多架构的，
# buildx --platform linux/amd64,linux/arm64 会自动拉对应架构的 node 镜像。
# camoufox-js 用 os.arch() 探测 CPU，arm64 上自动拉 camoufox-linux-arm64 release，
# 无需在此声明 TARGETARCH 分支。
FROM node:24-bookworm AS xiaobei-build

# NPM registry 走 ARG 参数——国内构建机走 npmmirror（省代理流量，与裸机 install.sh 同源），
# 海外构建机（GitHub Actions arm64 runner）走 npmjs（不跨境，最快）。
# 默认 npmmirror 兼容本地构建；GitHub workflow 里 override 成 npmjs。
ARG NPM_REGISTRY=https://registry.npmmirror.com

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/root \
    OPENCLAW_HOME=/root/.openclaw \
    OPENCLAW_STATE_DIR=/root/.openclaw \
    NPM_CONFIG_REGISTRY=${NPM_REGISTRY} \
    CONTAINER=true
# APT 源走阿里云（debian 源不论海内外都快），npm registry 由 ARG 控制

# 阿里云 APT 源加速（与裸机 install.sh 同源）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null \
    || sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null || true

# 基础工具 + 显示栈（camoufox 有头模式跑 Xvfb，用户经 noVNC 操作浏览器过验证）
# + 浏览器运行时依赖（gtk/dbus/nss/atspi/cups，camoufox Firefox 需要）
# + 微信容器配合：docker CLI 让 xiaobei 容器能 docker exec 进微信容器读消息库
# 合并成一次 apt-get 减层数
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash ca-certificates curl git openssl openssh-client \
        python3 python3-pip python3-venv \
        # 显示栈
        xvfb fluxbox x11vnc novnc websockify \
        # 浏览器运行时（camoufox Firefox）
        libasound2 libdbus-1-3 libgtk-3-0 libxt6 libxkbcommon-x11-0 \
        libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libgbm1 libpango-1.0-0 libcairo2 libatspi2.0-0 \
        libxcomposite1 libxdamage1 libxrandr2 libxshmfence1 libpangocairo-1.0-0 \
        fontconfig fonts-liberation fonts-noto-cjk fonts-wqy-microhei \
        # 微信容器配合（wx-mp-hunter posts-list 用 docker exec 读消息库）
        docker.io \
        # 视频处理（video-edit / talking-head-cut / aigc-video-gen / video-review /
        # viral-chaser / content-producer 等技能依赖；ffmpeg 包含 ffprobe）
        ffmpeg \
        # sqlite3 CLI（content-calibrator / published-track / wx-mp-engagement 等 shell 脚本用）
        sqlite3 \
        # 杂项
        sudo procps net-tools \
    && rm -rf /var/lib/apt/lists/*

# pnpm via npm install -g（不走 corepack 网络——corepack prepare 拉 pnpm 包跨境抖动）
# npm install -g 走 npm registry（npm_config_registry env 已设），拉 pnpm 装到 /usr/local/bin
RUN npm install -g pnpm@10.30.2

WORKDIR /opt/xiaobei

# 仓根整体 COPY（.dockerignore 排除 node_modules/dist/.git，但保留 openclaw/.git）
# docker-bootstrap.sh 在仓根 docker/ 下，apply-addons.sh / setup-crew.sh 在 scripts/ 下，
# camoufox-cli fork 在 patches/camoufox-cli/ 下，全部随仓根打进镜像。
COPY . /opt/xiaobei

# 校验源码树 + 跑 bootstrap 完成"装好后"状态
# bootstrap 复用裸机安装的 apply-addons.sh / setup-crew.sh / camoufox-cli/build.sh，
# 但不跑 daemon install / 不交互收密钥 / 不拉远程仓库（源码已 COPY 进来）
#
# 诊断设计（穿透 ACR buildkit 吞同 RUN stdout/stderr 的陷阱）：
#   - 执行步用 { ...; echo "BOOTSTRAP_CHAIN_EXIT=$?"; } 2>>.bootstrap-log 吞掉 exit code
#     让 buildkit 继续到独立 cat 步骤（否则 && 链 exit 1 后续步骤全跳过——
#     commit 8ff83f2 的独立 cat 跑不到就是这个原因）
#   - bootstrap 的 stderr 追加进 .bootstrap-log（脚本内 log() 也写这文件）
#   - 独立 cat 步骤 stdout 穿透 buildkit 显示诊断内容——无论 bootstrap 炸没炸都能跑
#   - 显式校验步 grep BOOTSTRAP_CHAIN_EXIT=0 决定是否 fail build
RUN { \
        test -d /opt/xiaobei/openclaw \
        && test -d /opt/xiaobei/openclaw/.git \
        && test -x /opt/xiaobei/docker/docker-bootstrap.sh \
        && NODE_OPTIONS="--max-old-space-size=4096" /opt/xiaobei/docker/docker-bootstrap.sh \
        && install -d /opt/xiaobei/runtime-seed/openclaw \
        && cp -a /root/.openclaw/. /opt/xiaobei/runtime-seed/openclaw/; \
        echo "BOOTSTRAP_CHAIN_EXIT=$?" >> /opt/xiaobei/.bootstrap-log; \
    } 2>>/opt/xiaobei/.bootstrap-log

# 独立 cat 诊断——这步 stdout 穿透 buildkit 显示 bootstrap 写的日志
RUN cat /opt/xiaobei/.bootstrap-log

# 显式 fail build——bootstrap 链炸了（exit code 非 0）就别继续
RUN grep -q "BOOTSTRAP_CHAIN_EXIT=0" /opt/xiaobei/.bootstrap-log

# ════════════════════════════════════════════════════════════════════
# Stage 2: runtime（瘦运行镜像，从 build 拷 immutable 层）
# ════════════════════════════════════════════════════════════════════
FROM node:24-bookworm

# runtime 镜像里 pnpm openclaw gateway 启动时不拉包，NPM_CONFIG_REGISTRY 仅给
# 首启用户手动 npm install -g 补包用。默认走 npmmirror（与裸机 install.sh 同源），
# buildx 海外 runner override ARG NPM_REGISTRY=npmjs 不影响运行时（ENV 进镜像层，
# 用户运行时可 docker run -e NPM_CONFIG_REGISTRY=... 覆盖）。
ARG NPM_REGISTRY=https://registry.npmmirror.com

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/root \
    OPENCLAW_HOME=/root/.openclaw \
    OPENCLAW_STATE_DIR=/root/.openclaw \
    CAMOUFOX_INSTALL_DIR=/root/.camoufox-cli \
    WISEFLOW_DOCKER=1 \
    DISPLAY=:99 \
    LANG=C.UTF-8 \
    NPM_CONFIG_REGISTRY=${NPM_REGISTRY} \
    CONTAINER=true
# APT 源走阿里云（debian 源不论海内外都快），npm registry 由 ARG 控制

# 阿里云 APT 源加速（与裸机 install.sh 同源）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null \
    || sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null || true

# runtime 只装显示栈 + 浏览器运行时 + docker CLI（不带构建工具链，瘦镜像）
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash ca-certificates curl openssl \
        python3 python3-pip \
        xvfb fluxbox x11vnc novnc websockify \
        libasound2 libdbus-1-3 libgtk-3-0 libxt6 libxkbcommon-x11-0 \
        libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libgbm1 libpango-1.0-0 libcairo2 libatspi2.0-0 \
        libxcomposite1 libxdamage1 libxrandr2 libxshmfence1 libpangocairo-1.0-0 \
        fontconfig fonts-liberation fonts-noto-cjk fonts-wqy-microhei \
        docker.io \
        ffmpeg \
        sqlite3 \
        procps net-tools \
    && rm -rf /var/lib/apt/lists/*

# 从 build 阶段拷贝 immutable 应用层
# /opt/xiaobei       仓根（引擎源码+dist / patches / scripts / crews / skills / awada / camoufox-cli fork）
# /root/.openclaw    预装态（openclaw.json template / 全局 skills / crew workspaces / weixin 插件）
# /root/.camoufox-cli  Firefox 二进制 + camoufox-cli 全局包
# /usr/local         Node + pnpm（node:24 带，corepack pnpm 在 build 装的）
COPY --from=xiaobei-build /opt/xiaobei /opt/xiaobei
COPY --from=xiaobei-build /root/.openclaw /root/.openclaw
COPY --from=xiaobei-build /root/.camoufox-cli /root/.camoufox-cli
# camoufox-cli 全局 npm 包（build 阶段 npm install -g 装的）
COPY --from=xiaobei-build /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=xiaobei-build /usr/local/bin /usr/local/bin.d-build
# 把 build 阶段的全局 bin（camoufox-cli 等）合并到 runtime 的 /usr/local/bin
RUN cp -a /usr/local/bin.d-build/* /usr/local/bin/ 2>/dev/null || true && rm -rf /usr/local/bin.d-build

# pnpm 在 runtime 也需要（openclaw gateway 用 pnpm openclaw gateway 启动）
# 装和 build stage 同版本 pnpm（不走 corepack 网络，绕跨境抖动）
RUN npm install -g pnpm@10.30.2

# 入口脚本（源文件在 docker/ 下，COPY 源路径相对 build context 仓根）
COPY docker/docker-entrypoint.sh /usr/local/bin/xiaobei-entrypoint
RUN chmod 0755 /usr/local/bin/xiaobei-entrypoint

# /root/.openclaw 外挂持久化（API key + 平台登录态 + workspace + sessions）。
# 不声明 /root/.camoufox-cli 为 VOLUME——否则 Docker 会自动建匿名 volume 覆盖镜像层里
# 的 camoufox 浏览器二进制 654MB（immutable 资源应留在镜像层，升级镜像时跟随更新）。
# 仅 /root/.camoufox-cli/profiles 子目录由 docker-compose.yml 显式挂 named volume
# 持久化 profile + cookie + 登录态。
VOLUME ["/root/.openclaw"]

# gateway API + noVNC web
EXPOSE 18789 6080

ENTRYPOINT ["/usr/local/bin/xiaobei-entrypoint"]
