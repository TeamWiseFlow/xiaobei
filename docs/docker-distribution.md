# xiaobei Docker 分发

> ⚠️ **可选通道，现阶段不再主推**（2026-07-19）
>
> wiseflow 现以 `scripts/install.sh`（curl 一键脚本）为主分发通道，详见 `docs/native-distribution-plan-2026-07-18.md` 与 README「快速开始」段。
> `.github/workflows/release.yml` 的 `docker` job 已删除，CI 不再自动构建推送镜像；`release` job 仅保留版本 bump + tag。
>
> 本文档保留给需要沙箱 / 隔离场景的用户参考，但需自行 build 镜像（`docker/docker-bootstrap.sh`）或使用历史已推到阿里云的滞后镜像。Dockerfile 与 `docker/` 脚本本身不删，留作后续重启通道时的复用基础。

## 运行

生产镜像由 GitHub Actions 在合并到 `master` 后构建并推送到阿里云镜像服务。用户只需要：

```bash
AWK_API_KEY=<your-key> docker compose up -d
```

`docker-compose.yml` 默认使用：

```text
registry.cn-hangzhou.aliyuncs.com/<namespace>/xiaobei:latest
```

本地验证先构建，再覆盖镜像名：

```bash
./scripts/build-image.sh
AWK_API_KEY=<your-key> IMAGE=xiaobei:local docker compose up -d
```

## 构建语义

Docker 并不运行 `scripts/install.sh`。该脚本还负责拉取仓库、交互收集密钥以及安装 systemd/launchd daemon，这些都不属于镜像构建。

镜像构建使用 `scripts/docker-bootstrap.sh`，它复用与裸机安装相同的 `apply-addons.sh` 与 `setup-crew.sh` 路径，完成：

- 应用 OpenClaw patches 和 overrides；
- 安装 awada、公共/crew skills 的 Node 与 Python 依赖；
- 创建 crew workspace、skills allowlist、wrapper 与运行配置；
- 编译 patched OpenClaw；
- 安装仓内 fork 的 `camoufox-cli` 及 Firefox 二进制。

因此 Docker 与裸机部署只在“源码同步、交互式密钥收集、宿主机服务管理”上不同，能力安装链路保持同源。

GitHub Actions 与 `scripts/build-image.sh` 都会先按 `openclaw.version` 注入固定 commit 的 `openclaw/` 源码（连同 `.git` 元数据）。这样 patch 的 `git apply --3way` 可用，并且构建不依赖构建时拉取最新业务代码。

## 持久化和升级

| 卷 | 容器路径 | 内容 |
|---|---|---|
| `xiaobei-openclaw` | `/root/.openclaw` | 配置、`.env`、workspace、会话与渠道状态 |
| `xiaobei-camoufox` | `/root/.camoufox-cli` | 浏览器 profile、Cookie、指纹与运行缓存 |

入口脚本在卷为空时从镜像内 `/opt/xiaobei/runtime-seed/openclaw` 初始化；它不依赖 Docker 对 named volume 的首次复制行为，因此空 bind mount 也可正常启动。已有卷绝不会被镜像升级覆盖，登录态和用户配置会保留。

两个卷包含 API key 和平台登录态。备份时应限制文件权限；删除卷等同于清空该实例的配置与登录状态。

## 安全边界

- `AWK_API_KEY` 仅从运行环境读取，不写入镜像层或 `openclaw.json`。
- 首启会为 gateway 生成随机 `OPENCLAW_GATEWAY_TOKEN`，以 `0600` 写入持久化 `.env`。
- Gateway 和 noVNC 在 Compose 中只映射到 `127.0.0.1`。不要直接把 6080 暴露到公网。
- 当前 Camoufox sandbox 需要 `SYS_ADMIN` capability；只运行受信任的官方镜像，并保持 Docker daemon 权限最小化。

## CI 发布

`release.yml` 的 Docker job：

1. checkout release commit；
2. 按 `openclaw.version` clone pinned OpenClaw；
3. 用 Buildx 构建 `linux/amd64` 镜像；
4. 推送 `xiaobei:<version>` 和 `xiaobei:latest`。

在阿里云 ACR 中预先创建名为 `xiaobei` 的仓库，并配置 `ALIYUN_REGISTRY`、`ALIYUN_NAME_SPACE`、`ALIYUN_REGISTRY_USER` 和 `ALIYUN_REGISTRY_PASSWORD` 四个 GitHub Secrets。
