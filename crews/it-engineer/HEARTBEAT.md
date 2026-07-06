# IT Engineer Agent — Heartbeat

## Health Check
- Status: operational
- Last updated: (auto-maintained)
- Watching: xiaobei system（部署方式见下「环境判定」）

## 环境判定（每次心跳先做一次）

- 容器内 `/.dockerenv` 存在 → **Docker 部署**：`PROJECT_ROOT=/opt/openclaw`、`OPENCLAW_HOME=/root/.openclaw`、无 systemd、gateway 为 PID 1。
- 否则 → **源码部署**：路径读 `OFB_ENV.md`，gateway 由 `systemctl --user` 管。

## 定期巡检任务

每次心跳执行以下检查，发现异常立即告知用户：

1. **gateway 进程存活**
   - Docker：`ps -p 1 -o comm=` 应为 `node`（entrypoint exec node）；或 `pgrep -f 'openclaw.mjs gateway'`
   - 源码：`systemctl --user is-active openclaw-gateway.service` 应为 `active`
2. **近期运行日志是否有新的 ERROR/FATAL**：通过 session-logs 技能或直接读日志文件（`$OPENCLAW_HOME/logs/gateway-error.log`；Docker 亦可 `docker logs <容器>` 于宿主侧）
3. **系统安全加固状态**（防火墙/SSH/更新状态）：调用 healthcheck 技能执行
4. **Docker 专属**（仅 Docker 部署时）：容器内无法自重启，若 gateway 不存活 → 告知宿主用户 `docker restart <容器名>`，不要尝试容器内重启

## 异常处置边界

- 容器内**禁止**尝试 `systemctl` / `service`（Docker 无 systemd）
- 容器内**禁止**尝试重启自身进程（PID 1 退出 = 容器退出）；重启交由宿主用户
- 源码部署下重启 gateway 前必须告知用户并征得同意（断所有 session）
