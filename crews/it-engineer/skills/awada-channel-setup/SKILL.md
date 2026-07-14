---
name: awada-channel-setup
description: >
  启用并配置 awada channel，使对外 crew（如 sales-cs）能以企业微信联系人的形态
  连接外部用户。当用户或 main agent 要求启用 sales-cs 时使用本技能：建议配置 awada
  channel → 获得确认 → 按 SOP 完成安装依赖、写 openclaw.json、重启 Gateway。
---

# awada-channel-setup

## 背景

awada extension 是专为对外 crew（如 sales-cs）打造的消息通道，可令 sales-cs 以
企业微信联系人的形态连接外部用户。配置默认直接启用 customerDB hook（自动记录客户
来访、更新状态），因此整个配置过程是一个可机械执行的 SOP。

## 何时使用

- 用户或 main agent 要求启用 sales-cs / 任何对外 crew → 建议配置 awada channel
- 用户明确要求绑定/修复 awada channel

## SOP（按顺序执行）

### 1. 确认 awada 依赖已就位（通常已预装，跳过）

awada 走 relay 网关 HTTP/WS 传输，运行时依赖 `ws` + `zod`，已在以下场景预装，正常无需手动操作：

- **Docker 部署**：镜像 build 时已 `npm install --omit=dev` 进 `/opt/openclaw/awada/node_modules`
- **源码部署**：`apply-addons.sh` 已自动装进 `<PROJECT_ROOT>/awada/node_modules`（哈希守卫，幂等）

仅当 `node_modules` 被清理、`package.json` 变更、或日志报 `Cannot find module 'ws'`（plugin=awada）时，才手动补装：

```bash
cd <WISEFLOW_PROJECT_ROOT>/awada && pnpm install --prod
```

工作目录 = `<WISEFLOW_PROJECT_ROOT>/awada/`（单层结构）。

### 2. 写 openclaw.json

读取同目录 `openclaw-awada-sample.json` 拿到最小配置片段，然后用本技能脚本把它
合并进运行中的 `~/.openclaw/openclaw.json`：

```bash
awada-channel-setup
```

脚本行为：
- 读 `openclaw-awada-sample.json` 作为模板
- 提示输入 `relayBaseUrl` / `ofbKey` / `lane` / `platform`（带默认值，可回车接受）
- 合并进 `~/.openclaw/openclaw.json` 的 `channels.awada` 与 `plugins`（customerDB
  hook 默认 `enabled: true`，agentId=`sales-cs`）
- 原子写回（temp + os.replace），先备份 `.bak-<ts>`
- 不重启 Gateway（由步骤 3 人工确认）

> `relayBaseUrl` / `ofbKey` 由 relay admin 签发（OFB_KEY 须含 `awada:lane:<laneId>` scope）。客户端不持 Redis 凭据。

### 3. 建议重启 Gateway

改 binding/channel 路由后必须完整重启（hot-reload 不重置 routing 缓存，见
it-engineer MEMORY「binding routing 坑 2」）：

> 重启会断所有 session，**执行前必须告知用户并征得同意**。

按部署方式二选一：

- **Docker 部署**（容器内 IT engineer 检测到 `/.dockerenv` 存在）：告知宿主用户执行
  `docker restart <容器名>`（容器内无法自重启自身）。
- **源码部署**（systemd）：`systemctl --user restart openclaw-gateway.service`。

### 4. 验证

- Channel 状态显示 connected
- 用外部账号给 sales-cs 发一条消息，确认收发闭环
- customerDB：`~/.openclaw/workspace-sales-cs/db/` 出现新来访记录

## 排障检查单

1. `Cannot find module 'ws'` → 步骤 1 预装未就位（Docker 镜像 build 漏装 / 源码部署 apply-addons.sh 没跑）；手动 `cd <PROJECT_ROOT>/awada && pnpm install --prod` 补装
2. 网关连接失败 / 401 → 检查 `relayBaseUrl` 可达性 + `ofbKey` 是否含 `awada:lane:<lane>` scope
3. awada-server（relay 侧）进程存活 + Redis 连通性（relay 内部，客户端不直接碰）
4. webhook 回调地址与平台后台一致
5. `channels.awada` 的 `lane/platform` 与 relay 侧 bot 配置匹配
6. binding 写了但消息仍走 default agent → 见 it-engineer MEMORY「binding routing 坑 1」：
   binding 必须写 `accountId`（通配用 `"*"`）
