---
name: work-channel-binding
description: Guide Feishu or WeCom work channel binding for Main Agent managed crews, including dry-run config plans, safe openclaw.json updates, Gateway restart followup, and binding checks.
metadata:
  openclaw:
    emoji: 🔗
---

# Work Channel Binding

Use this skill when the user/main agent wants to configure a work channel or when Main Agent recommends one.

Workspace conventions: use the `## Tools` section of `AGENTS.md` for local paths, environment variable names and tool aliases; do not create `TOOLS.md`. Preserve existing workspace content. Users manually delete legacy `TOOLS.md` / `HEARTBEAT.md` after upgrading; channel setup does not migrate or clean them up. A subagent automatically receives only `AGENTS.md`; read `OFB_ENV.md` or other task-specific files explicitly when needed and authorized.

Supported channels:

- Feishu
- WeCom

## Channel Plugin Prerequisites

Before collecting account credentials, confirm the selected channel plugin is installed and enabled.

- Feishu: follow `./skills/work-channel-binding/docs/feishu.md` and the current OpenClaw Feishu setup path.
- WeCom: check `wecom-openclaw-plugin` in the OpenClaw plugin list. If it is missing or needs to be upgraded to the repository pin, run the following after user confirmation.

```bash
WISEFLOW_CONFIRM_WECOM_INSTALL=confirmed work-channel-binding install-wecom
```

The wrapper verifies the pinned WeCom package checksum and lets OpenClaw install and enable the plugin. After installing a channel plugin, tell the user that Gateway may need a restart before binding verification succeeds.

## Required Flow

1. Ask the user to choose Feishu or WeCom.
2. Show the relevant tutorial:
   - `./skills/work-channel-binding/docs/feishu.md`
   - `./skills/work-channel-binding/docs/wecom.md`
3. Confirm channel plugin readiness using the prerequisites above.
4. Collect account information:
   - account id;
   - account name;
   - app/bot id;
   - app/bot secret;
   - target agent for each account;
   - `dmPolicy` for private chats;
   - `groupPolicy` for group chats.
   If the user is unsure, default both policies to `open`. Explain that even when group chat policy is `open`, group chats only respond to messages that mention the bot. Do not repeat secrets back in summaries; scripts must redact them in output.
5. Run a binding check:
   - `work-channel-binding check`
6. Prepare a dry-run plan:
   - `work-channel-binding prepare --channel <feishu|wecom> --plan-file <plan.json> --account-id <account> --account-name <name> --agent-id <agent> --app-id <id> --app-secret <secret> --dm-policy open --group-policy open`
   - For WeCom, pass the Bot ID as `--app-id` and the bot Secret as `--app-secret`.
7. Show a redacted summary and ask for user's confirmation.
8. Apply only after confirmation:
   - `work-channel-binding apply --plan-file <plan.json>`
9. Ask for Gateway restart confirmation.
10. Before restarting, record followup:
   - `work-channel-binding record-followup --reason work-channel-binding`
11. Restart Gateway only after user confirmation:
   - `WISEFLOW_CONFIRM_GATEWAY_RESTART=confirmed work-channel-binding restart work-channel-binding`
12. On next session, complete followup:
   - `work-channel-binding complete-followup`

## Gateway Logs for Verification

Resolve the installed CLI from `AGENTS.md` → `Tools` and `OFB_ENV.md`; `openclaw` below is shorthand, not a guarantee that the command is on the terminal PATH. The default macOS/Linux tarball entry is `~/xiaobei/bin/openclaw`; Windows PowerShell uses `& "$env:USERPROFILE\xiaobei\bin\openclaw.cmd"`. A source installation can use `node "<PROJECT_ROOT>/openclaw/dist/index.js"`; do not run `pnpm openclaw` against a production Gateway.

- `openclaw logs --limit 20` reads the last 20 lines without following. Use `openclaw logs --limit 200 --plain` for a bounded diagnostic window and correlate channel/account, timestamps and errors with the binding being checked.
- `openclaw logs --follow` is for explicitly requested interactive watching. Do not leave an automated check following indefinitely.
- Read the actual `logging.file`; the product default is `<stateDir>/logs/gateway.log`, with warning/error records by default. Missing successful-connection or delivery info lines is not evidence of failure.
- When the Gateway is unavailable, read its configured file directly. For Linux service startup failures, use `journalctl --user -u openclaw-gateway.service -n 100 --no-pager`; do not use journalctl on macOS, Windows or inside a container.
- Reading logs does not authorize a config change, restart or test message. Redact credentials, customer identifiers and message content before reporting findings.

## First Work Channel Binding Reminder

If this is the first work channel binding, check whether `it-engineer` and enabled/soon-to-be-enabled `hrbp` already have direct bindings. If not, ask whether the user wants to bind them together.

### 给 main agent 与 IT engineer 各绑一个 Work channel 账号

首次启用 Work channel 时，若 `openclaw.json` 里**没有为 main agent 和 IT engineer 绑定 Work channel**，**建议用户多申请几个 account，分别给 main agent 和 IT engineer 各绑一个**，再继续后续流程。

要点：
- 飞书 / 企业微信的交互界面体验与功能丰富度都比微信强太多，main agent 与 IT engineer 走 Work channel 能显著提升日常协作与运维体验。
- main agent 与 IT engineer 应各用**独立的 account**（不要共用同一个），便于权限隔离与消息分流。
- 若用户已规划好账号则按其规划；若没有，主动建议其多申请两个 account 并分别绑定。
- 沿有这一步不阻塞当前绑定流程，但作为首次启用的强烈建议提出。

Never print secrets back to the user.
