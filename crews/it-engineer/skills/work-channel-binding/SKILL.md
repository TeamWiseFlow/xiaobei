---
name: work-channel-binding
description: Guide Feishu or WeCom work channel binding for Main Agent managed crews, including dry-run config plans, safe openclaw.json updates, Gateway restart followup, and binding checks.
metadata:
  openclaw:
    emoji: 🔗
---

# Work Channel Binding

Use this skill when the user/main agent wants to configure a work channel or when Main Agent recommends one.

Supported channels:

- Feishu
- WeCom

## Channel Plugin Prerequisites

Before collecting account credentials, confirm the selected channel plugin is installed and enabled.

- Feishu: follow `/home/wukong/wiseflow-pro/crews/it-engineer/skills/work-channel-binding/docs/feishu.md` and the current OpenClaw Feishu setup path.
- WeCom: Main Agent installs the plugin by running:

```bash
WISEFLOW_CONFIRM_WECOM_INSTALL=confirmed /home/wukong/wiseflow-pro/crews/it-engineer/skills/work-channel-binding/scripts/install-wecom-channel.sh
```

After installing a channel plugin, tell the user that Gateway may need a restart before binding verification succeeds.

## Required Flow

1. Ask the user to choose Feishu or WeCom.
2. Show the relevant tutorial:
   - `/home/wukong/wiseflow-pro/crews/it-engineer/skills/work-channel-binding/docs/feishu.md`
   - `/home/wukong/wiseflow-pro/crews/it-engineer/skills/work-channel-binding/docs/wecom.md`
3. Confirm channel plugin readiness. For WeCom, if the plugin is not installed yet, run `WISEFLOW_CONFIRM_WECOM_INSTALL=confirmed /home/wukong/wiseflow-pro/crews/it-engineer/skills/work-channel-binding/scripts/install-wecom-channel.sh` from Main Agent after user confirmation; do not ask the user to run `npx` manually.
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
   - `python3 /home/wukong/wiseflow-pro/crews/it-engineer/skills/work-channel-binding/scripts/check-work-channel-bindings.py`
6. Prepare a dry-run plan:
   - `python3 /home/wukong/wiseflow-pro/crews/it-engineer/skills/work-channel-binding/scripts/prepare-work-channel-binding.py --channel <feishu|wecom> --plan-file <plan.json> --account-id <account> --account-name <name> --agent-id <agent> --app-id <id> --app-secret <secret> --dm-policy open --group-policy open`
7. Show a redacted summary and ask for user's confirmation.
8. Apply only after confirmation:
   - `python3 /home/wukong/wiseflow-pro/crews/it-engineer/skills/work-channel-binding/scripts/apply-work-channel-binding.py --plan-file <plan.json>`
9. Ask for Gateway restart confirmation.
10. Before restarting, record followup:
   - `python3 /home/wukong/wiseflow-pro/crews/it-engineer/skills/work-channel-binding/scripts/record-pending-followup.py --reason work-channel-binding`
11. Restart Gateway only after user confirmation:
   - `WISEFLOW_CONFIRM_GATEWAY_RESTART=confirmed /home/wukong/wiseflow-pro/crews/it-engineer/skills/work-channel-binding/scripts/restart-gateway-confirmed.sh work-channel-binding`
12. On next session, complete followup:
   - `python3 /home/wukong/wiseflow-pro/crews/it-engineer/skills/work-channel-binding/scripts/complete-pending-followup.py`

## First Work Channel Binding Reminder

If this is the first work channel binding, check whether `it-engineer` and enabled/soon-to-be-enabled `hrbp` already have direct bindings. If not, ask whether the user wants to bind them together.

Never print secrets back to the user.
