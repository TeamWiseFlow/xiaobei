# xiaobei Docker 部署（v5.6.3+）

> **开箱即用**：镜像内已装好 openclaw 引擎 + 全部 skills/crews + camoufox-cli + Firefox +
> openclaw-weixin 插件 + deck-render 的 HyperFrames/Playwright Chromium/Noto Sans CJK SC + Xvfb/fluxbox/x11vnc/websockify/noVNC 显示栈。
> 用户本地 build 镜像后只需填 `AWK_API_KEY`，`docker compose up -d` 即可启动。

## 快速开始

**工作目录前提**：`docker build` 的 build context 是仓库根，必须**在仓库根**执行；
`docker compose` 的 compose 文件和自动加载的 `.env` 都在 `docker/` 下，必须**在
`docker/` 下**执行。下文每步会标出当前应在哪个目录。

```bash
# ─── 在仓库根执行 ───────────────────────────────────────────
# 1. 本地构建镜像（openclaw 源码需先按 openclaw.version 锁定 commit 检出到仓根 openclaw/）
docker build -f docker/Dockerfile -t xiaobei:local .

# 2. 拷贝环境模板到 docker/.env
cp docker/.env.example docker/.env

# 3. 编辑 docker/.env，填入你的 AWK_API_KEY（阿里云百炼 token）
#    AWK_API_KEY=sk-xxxxxxxxxxxxxxxx

# ─── 切到 docker/ 下执行（compose 文件 + .env 自动加载都在这）──
cd docker

# 4. 启动
AWK_API_KEY=<key> docker compose up -d

# 5. 访问
#    gateway API:   http://localhost:18789
#    noVNC web:      http://localhost:6080/vnc.html
```

首启会打印微信扫码绑定二维码，用手机微信扫码确认登录即可。绑定态持久化在
`xiaobei-openclaw` 卷，后续重启自动跳过扫码。

镜像 tag 默认是 `xiaobei:local`（`docker-compose.yml` 里
`image: ${IMAGE:-xiaobei:local}`）。如需换 tag，build 时改 `-t`，并 `IMAGE=xxx` 覆盖启动：

```bash
# 在仓库根
docker build -f docker/Dockerfile -t my-xiaobei:v1 .

# 在 docker/ 下
IMAGE=my-xiaobei:v1 docker compose up -d
```

> **注意**：`docker compose` 必须在 `docker/` 目录下执行。若想在别处跑，需用
> `docker compose -f /path/to/docker/docker-compose.yml …` 显式指定 compose 文件和
> `.env` 路径，否则 `.env` 不会被自动加载。

## 镜像内容（= 跑完 install.sh 后的状态）

| 层 | 内容 |
|----|------|
| openclaw 引擎 | 按 `openclaw.version` pin 的 commit + 全部 patches + 编译后的 dist |
| awada 插件 | 本地 TS 插件 + ws/zod 运行时依赖 |
| skills | 公共 skills（`skills/`）+ crew 专属 skills（`crews/*/skills/`）+ python deps |
| crews workspace | main / content-producer / it-engineer / sales-cs 四套 crew 预初始化 |
| camoufox-cli | wiseflow fork（反指纹浏览器 CLI）+ Firefox 二进制（~557MB） |
| deck-render | 锁定 HyperFrames/GSAP/Playwright 包 + Chromium headless shell + Noto Sans CJK SC；构建时安装，运行层直接使用 |
| openclaw-weixin | 预装微信 channel 插件（首启扫码绑定） |
| 显示栈 | Xvfb（虚拟显示）+ fluxbox（窗口管理）+ x11vnc + websockify + noVNC |

**不装**：systemd/launchd daemon（容器无服务管理器）、交互式密钥收集（走环境变量）。

## 数据外挂（两个 named volume）

| Volume | 容器路径 | 内容 |
|--------|---------|------|
| `xiaobei-openclaw` | `/root/.openclaw` | openclaw.json、`.env`、workspace、会话、微信登录态 |
| `xiaobei-camoufox` | `/root/.camoufox-cli` | 浏览器 profile、Cookie、指纹缓存 |

**首启行为**：空卷从镜像内 `/opt/xiaobei/runtime-seed/openclaw` 初始化。
**升级行为**：已有卷**绝不覆盖**，登录态和用户配置保留。
**备份**：两个卷含 API key 和平台登录态，备份时应限制文件权限。
**清空**：`docker compose down -v` 删除卷，等同于清空该实例的配置与登录状态。

## noVNC — 浏览器操作容器内桌面

camoufox 有头模式跑在容器内 Xvfb 虚拟显示里。用户浏览器打开
`http://localhost:6080/vnc.html` 即可看到该显示里的 fluxbox 柌面，里面能看到 camoufox
浏览器窗口——用于**小红书/抖音等平台登录过验证**的场景。

**端口默认只绑 Docker host 的 `127.0.0.1`**。远程访问应走 SSH 隧道或显式配置代理，
不要直接把 6080 暴露到公网。

## 微信容器配合（wx-mp-hunter posts-list）

`wx-mp-hunter` skill 的 `posts-list` 子命令依赖一个运行中的微信客户端容器，
通过 `docker exec` 进微信容器读 SQLCipher 加密的消息库。

**微信客户端容器不在本公开仓暴露**（知识产权风险），由有权限的用户自行另起
compose override 引入。`docker-compose.yml` 已为这种场景预留接入点：

- `xiaobei` 容器挂载宿主 `/var/run/docker.sock`（只读），用于 `docker exec` 进微信容器
- 环境变量 `WX_BIZ_CONTAINER` / `WX_BIZ_USER_DIR` / `WX_BIZ_KEYS_FILE` 指向微信容器
  （默认值与微信容器约定，用户自行 override）

如果只用到 `wx-mp-hunter` 的 `fetch` / `homepage` 子命令（不依赖微信容器），
则无需引入微信容器，`xiaobei` 容器可独立运行。

## 安全边界

- `AWK_API_KEY` 仅从运行环境读取，**不写入镜像层**也不写 `openclaw.json` 的明文。
- 首启会为 gateway 生成随机 `OPENCLAW_GATEWAY_TOKEN`，以 `0600` 写入持久化 `.env`。
- Gateway 和 noVNC 在 Compose 中只映射到 `127.0.0.1`。**不要直接把 6080 暴露到公网**。
- 当前 Camoufox sandbox 需要 `SYS_ADMIN` capability；只运行受信任的官方镜像，并保持
  Docker daemon 权限最小化。
- `/var/run/docker.sock` 只读挂载——xiaobei 容器能 `docker exec` 进微信容器读消息库，
  但无法修改宿主 docker 状态。若需更强隔离，可改用 docker-socket-proxy。
