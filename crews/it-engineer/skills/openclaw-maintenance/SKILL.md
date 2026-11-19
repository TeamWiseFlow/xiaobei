---
name: openclaw-maintenance
description: 维护 xiaobei 的 OpenClaw 运行控制面：按时间窗审计日志、管理心跳与 Automations、排查 exec 审批拒绝、核对插件生效，以及定位或重置指定会话。渠道开通用 awada-channel-setup 或 work-channel-binding；浏览器网页操作用 browser-guide。
metadata:
  openclaw:
    emoji: 🛠️
---

# OpenClaw 运行维护

按故障或任务只读对应手册，不把全部参考文档加载到每次派工中。

| 任务 | 手册 |
|---|---|
| 今天/某时间段有什么问题、升级后巡检、研发 issue 取证 | [日志审计](references/logs.md) |
| 建立/调整业务定时任务、心跳、scratch、核对报告交付 | [Automations](references/automations.md) |
| allowlist miss、软链脚本拒绝、审批声明与运行策略不一致 | [exec 审批](references/exec.md) |
| 插件或命令改了是否生效、热重载排队、浏览器 BROKER_REQUIRED | [插件生效](references/plugins.md) |
| 查指定 agent 的会话、静默删除单个联系人历史 | [会话维护](references/sessions.md) |

## 共同约束

- 先按 workspace AGENTS.md 的 Tools 节及 OFB_ENV.md 确认程序、配置和 stateDir。源码版本见仓库 `openclaw.version`，运行版本用已安装的 CLI 核实。
- 优先用当前会话可用且获授权的 `automations`、`gateway`、`sessions_*`、`plugins` 等原生工具。CLI 表中的 `openclaw` 指已安装入口；源码部署用已构建的 `node <PROJECT_ROOT>/openclaw/dist/index.js`，生产中不运行 `pnpm openclaw` 或开发构建入口。
- 维护范围沿用本次已有授权。只查日志不自动重启、改配置或发测试消息；不重复索取已获得的授权。管理权限不等于聊天 allowlist，权限不足交可信管理员，不直接写 SQLite 绕过。
- 不手改活动 SQLite、旧 sessions.json、cron JSON 或 exec-approvals.json。数据库备份用原生备份或 SQLite 一致性快照，不对打开的数据库做 Git checkout/rebase 或复制单个主文件当作完整备份。
- 变更先保留可回退的原值，保存后回读，再按实际业务结果核验。配置写入、插件加载、渠道连接、消息交付与业务成功分别报告。

## 配套命令

`openclaw-maintenance` wrapper 提供有界日志汇总与 scratch 快照/CAS 写回；不编辑运行数据库、不重启服务、不触发业务任务。先读对应手册再使用。脚本只用 Python 标准库；CLI 路径不在 PATH 时设置 `XIAOBEI_OPENCLAW_CLI` 为已安装入口，或 `XIAOBEI_OPENCLAW_ENTRY` 为已构建的 `dist/index.js` 绝对路径，不在变量中拼 shell 参数。
