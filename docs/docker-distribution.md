# Docker 分发方案（三层）

> 2026-07-16 · 三层 Docker 分发：源码 Dockerfile → GitHub Action 自动构建 → 阿里云容器镜像服务转存

## 一、方案概览

wiseflow-client 的 Docker 分发分三层，对应三个独立但串接的环节：

| 层 | 载体 | 职责 | 触发时机 |
|----|------|------|----------|
| 1. 构建 | `Dockerfile`（仓根） | 从源码构建可运行镜像 | `docker build` / CI |
| 2. 自动化 | `.github/workflows/release.yml` 的 `docker` job | PR merge 时自动构建+推送 | PR closed+merged |
| 3. 转存 | 阿里云容器镜像服务（ACR） | 国内拉取加速 | docker job push 时 |

**最终效果**：开发者向上游提 PR → PR 被合并 → 自动触发版本 bump + GitHub Release（zip 源码包）+ Docker 镜像构建并推送到阿里云 ACR → 国内用户 `docker pull` 即可拉取。

---

## 二、第一层：Dockerfile（源码构建）

### 2.1 多阶段结构

仓根 `Dockerfile` 采用四阶段多阶段构建：

```
阶段 1: workspace-deps   基础环境（node:24-bookworm + pnpm + python3 + camoufox-cli + Firefox）
阶段 2: build            COPY openclaw 源码 + patches + pnpm install + pnpm build
阶段 3: wiseflow-layer   COPY skills/crews/config → /root/.openclaw 运行态；pip/npm 预装；camoufox 指纹模板
阶段 4: runtime          复制产物 + ENTRYPOINT（docker-entrypoint.sh）
```

### 2.2 openclaw 源码注入

`openclaw/` 目录被 `.gitignore` 排除，不能直接 COPY 进镜像。构建时需先 clone 并按 `openclaw.version` 锁定的 commit checkout：

```bash
# 本地构建（用 scripts/build-image.sh 一键完成）
bash scripts/build-image.sh

# 或手动
source openclaw.version
git clone https://github.com/openclaw/openclaw openclaw
git -C openclaw checkout $OPENCLAW_COMMIT
docker build --build-arg OPENCLAW_VERSION=$OPENCLAW_VERSION \
             --build-arg OPENCLAW_COMMIT=$OPENCLAW_COMMIT \
             -t wiseflow-client:local .
```

CI 里由 `release.yml` 的 `docker` job 自动完成这一步。

### 2.3 skills/crews COPY 策略

Docker 走 COPY（不软链），容器内无 `~/wiseflow` 源码故软链无意义：

| 来源 | 目标 | 说明 |
|------|------|------|
| `skills/` | `/root/.openclaw/skills/` | 公共技能 |
| `crews/main/skills/` | `/root/.openclaw/workspace-main/skills/` | main crew 私有技能 |
| `crews/content-producer/skills/` | `/root/.openclaw/workspace-content-producer/skills/` | content-producer crew 私有技能 |
| `crews/it-engineer/skills/` | `/root/.openclaw/workspace-it-engineer/skills/` | it-engineer crew 私有技能 |

`sales-cs` 默认不 COPY（用户启用时单独处理）。

### 2.4 skill npm 依赖预装

带外部 npm 依赖的 skill（`rss-reader`、`wx-mp-hunter`、`proactive-send`）在 `wiseflow-layer` 阶段 per-skill `npm install --omit=dev`，与 `scripts/apply-addons.sh` 的扫描逻辑同源。

### 2.5 .dockerignore

`.dockerignore` 排除本地 `node_modules` / `dist` / `.git` / 构建产物，避免打进镜像（镜像内统一重新 install）。

---

## 三、第二层：GitHub Action 自动构建

### 3.1 触发条件

`.github/workflows/release.yml` 在 PR closed + merged 到 `master` 时触发，也可通过 `workflow_dispatch` 手动触发。

### 3.2 两个 job

**release job**（原有，不变）：
1. 计算 new version（基于 PR labels / workflow_dispatch 输入）
2. 更新 `version` 文件 + commit + tag + push
3. clone openclaw 源码
4. 打 zip 包
5. 创建 GitHub Release 附带 zip

**docker job**（新增）：
1. `needs: release`，等待 release job 完成（确保 `version` 文件已 commit）
2. checkout 最新 master（含 release job 提交的 version+tag）
3. clone openclaw 源码
4. `docker build` 多阶段镜像
5. tag 为版本号 + `latest`
6. push 到阿里云 ACR

两个 job 串接，release 先做 version bump，docker 后做镜像构建。

### 3.3 镜像 tag 策略

每次 PR merge 生成两个 tag：

| tag | 含义 | 用途 |
|-----|------|------|
| `<version>` | 具体版本号（如 `v5.6.0`） | 版本回滚、审计 |
| `latest` | 最新版本 | 默认拉取 |

---

## 四、第三层：阿里云容器镜像服务（ACR）转存

### 4.1 为什么用阿里云 ACR

- GitHub Container Registry (ghcr.io) 国内拉取慢且不稳定
- 阿里云 ACR 个人版免费，国内线路速度快
- 与 `docker_image_pusher` 方案同源（参考 https://github.com/bigbrother666sh/docker_image_pusher）

### 4.2 与 docker_image_pusher 的区别

`docker_image_pusher` 的方案是"拉国外镜像 → tag → push 阿里云"，适用于转存已构建好的镜像。

我们的方案是"在 GH Action 里直接 build + push 阿里云"，避免双跳：
- GH Action runner 直接 `docker build` 我们的 Dockerfile
- `docker login` 阿里云 ACR
- `docker push` 直推阿里云

### 4.3 阿里云 ACR 配置

**前置准备**（在阿里云控制台）：
1. 登录阿里云容器镜像服务：https://cr.console.aliyun.com/
2. 启用个人实例，创建一个命名空间（如 `wiseflow`）
3. 在"访问凭证"获取用户名、密码、仓库地址

**GitHub Secrets 配置**（在 GitHub 仓库 Settings → Secrets and variables → Actions）：

| Secret 名 | 含义 | 示例值 |
|-----------|------|--------|
| `ALIYUN_REGISTRY` | 阿里云仓库地址 | `registry.cn-hangzhou.aliyuncs.com` |
| `ALIYUN_NAME_SPACE` | 阿里云命名空间 | `wiseflow` |
| `ALIYUN_REGISTRY_USER` | 阿里云用户名 | `your-aliyun-account` |
| `ALIYUN_REGISTRY_PASSWORD` | 阿里云密码 | `your-password` |

配置完成后，PR merge 时自动构建并推送，无需手动操作。

### 4.4 镜像命名规则

```
registry.cn-hangzhou.aliyuncs.com/<namespace>/wiseflow-client:<version>
registry.cn-hangzhou.aliyuncs.com/<namespace>/wiseflow-client:latest
```

例如：
```
registry.cn-hangzhou.aliyuncs.com/wiseflow/wiseflow-client:v5.6.0
registry.cn-hangzhou.aliyuncs.com/wiseflow/wiseflow-client:latest
```

### 4.5 阿里云仓库创建

阿里云 ACR 个人版**不支持自动创建仓库**，需先在控制台手动创建 `wiseflow-client` 仓库（命名空间下）。

创建步骤：
1. 阿里云容器镜像服务控制台 → 个人实例 → 镜像仓库
2. 创建镜像仓库 → 命名空间选 `wiseflow` → 仓库名 `wiseflow-client` → 类型公开或私有
3. 创建完成后，GH Action push 时自动匹配到该仓库

> ⚠️ 若未先创建仓库，`docker push` 会报 `repository does not exist` 错误。

---

## 五、用户使用方式

### 5.1 从阿里云拉取（推荐）

```bash
# 拉取最新版本
docker pull registry.cn-hangzhou.aliyuncs.com/<namespace>/wiseflow-client:latest

# 拉取指定版本
docker pull registry.cn-hangzhou.aliyuncs.com/<namespace>/wiseflow-client:v5.6.0

# 运行
docker run -d \
  -e OFB_KEY=<your-key> \
  -e AWK_API_KEY=<your-api-key> \
  -p 18789:18789 \
  -v wiseflow-logins:/root/.openclaw \
  -v wiseflow-camoufox:/root/.camoufox-cli \
  registry.cn-hangzhou.aliyuncs.com/<namespace>/wiseflow-client:latest
```

### 5.2 使用 docker-compose

```bash
# 编辑 docker-compose.yml，取消注释 image: 行，替换 <namespace>
# 然后运行
OFB_KEY=<your-key> docker compose up -d
```

### 5.3 本地构建（开发调试）

```bash
# 一键构建（自动 clone openclaw）
bash scripts/build-image.sh

# 或手动
source openclaw.version
git clone https://github.com/openclaw/openclaw openclaw
git -C openclaw checkout $OPENCLAW_COMMIT
docker build -t wiseflow-client:local .

# 运行
docker run -d \
  -e OFB_KEY=<your-key> \
  -p 18789:18789 \
  wiseflow-client:local
```

---

## 六、CI 流程详解

### 6.1 release job 输出

release job 通过 `outputs.new_version` 把版本号传给 docker job：

```yaml
release:
  outputs:
    new_version: ${{ steps.version.outputs.new }}
```

docker job 通过 `needs.release.outputs.new_version` 拿到版本号用于镜像 tag。

### 6.2 docker job checkout 策略

docker job `checkout` 时指定 `ref: master`，确保拿到 release job 刚 commit 的最新 `version` 文件和 tag。这比 docker job 自己重新算版本号更可靠（避免并发 PR merge 时版本号不一致）。

### 6.3 docker job 完整流程

```
1. needs: release（等待 release job 完成）
2. checkout master（含 release job 提交的 version+tag）
3. 读 openclaw.version 拿到 OPENCLAW_COMMIT
4. clone openclaw 源码到 openclaw/ 目录
5. docker login 阿里云 ACR
6. docker build（多阶段，bake openclaw + skills + camoufox）
7. docker tag <version> + latest
8. docker push <version> + latest
```

---

## 七、故障排查

### 7.1 docker push 报 "repository does not exist"

阿里云 ACR 个人版不支持自动创建仓库。需先在阿里云控制台手动创建 `wiseflow-client` 仓库。

### 7.2 docker build 报 "COPY openclaw/ failed"

`openclaw/` 目录不存在。需先 clone：
```bash
source openclaw.version
git clone https://github.com/openclaw/openclaw openclaw
git -C openclaw checkout $OPENCLAW_COMMIT
```

CI 里由 docker job 的 "Clone openclaw at pinned commit" step 自动完成。

### 7.3 camoufox-cli install 失败

阶段 1 的 `camoufox-cli install --with-deps` 需要 apt 装系统依赖。若失败，检查 `node:24-bookworm` 基础镜像是否更新。

### 7.4 镜像太大

camoufox Firefox 二进制 + openclaw 源码 + node_modules 累计较大（~2-3GB）。这是多阶段构建的权衡：构建时大，运行时只保留必要产物。

---

## 八、与 D21 文档的关系

`docs/d21-symlink-skill.md` §3.2 描述了 Docker 镜像维持 COPY（不软链）的策略：

```dockerfile
COPY skills/ /root/.openclaw/skills/
COPY crews/main/skills/ /root/.openclaw/workspace-main/skills/
```

本方案在 Dockerfile `wiseflow-layer` 阶段落地了这些 COPY 指令，与 D21 文档保持一致。

D21 §4.3 还提到"容器内 `~/wiseflow` 不存在，软链失效；走 `COPY` 时把 wrapper 一并 COPY + 容器 entrypoint 自管 PATH"。本方案的 `docker-entrypoint.sh` 已预留 PATH 注入位（TODO(Phase 6) 标记处），后续 wrapper 暴露在此补完。

---

## 九、变更历史

- **2026-07-16**：初版。三层方案落地：Dockerfile 补齐 skills/crews COPY + skill npm 预装；release.yml 新增 docker job（PR merge → build → push 阿里云 ACR）；docker-compose.yml 支持阿里云镜像拉取；本文档。
