#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any


def redacted_accounts(accounts: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "accountId": account["accountId"],
            "name": account.get("name", account["accountId"]),
            "appId": account.get("appId", ""),
            "appSecret": "***" if account.get("appSecret") else "",
            "dmPolicy": account.get("dmPolicy", "open"),
            "groupPolicy": account.get("groupPolicy", "open"),
        }
        for account in accounts
    ]


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a redacted work channel binding plan.")
    parser.add_argument("--channel", required=True, choices=["feishu", "wecom"])
    parser.add_argument("--plan-file", required=True)
    parser.add_argument("--account-id", action="append", default=[])
    parser.add_argument("--agent-id", action="append", default=[])
    parser.add_argument("--app-id", action="append", default=[])
    parser.add_argument("--app-secret", action="append", default=[])
    parser.add_argument("--account-name", action="append", default=[])
    parser.add_argument("--dm-policy", action="append", default=[])
    parser.add_argument("--group-policy", action="append", default=[])
    args = parser.parse_args()

    expected = len(args.account_id)
    for label, values in {
        "--agent-id": args.agent_id,
        "--app-id": args.app_id,
        "--app-secret": args.app_secret,
    }.items():
        if len(values) != expected:
            raise SystemExit(f"{label} must appear the same number of times as --account-id")
    if args.account_name and len(args.account_name) != expected:
        raise SystemExit("--account-name must appear the same number of times as --account-id when provided")
    if args.dm_policy and len(args.dm_policy) != expected:
        raise SystemExit("--dm-policy must appear the same number of times as --account-id when provided")
    if args.group_policy and len(args.group_policy) != expected:
        raise SystemExit("--group-policy must appear the same number of times as --account-id when provided")

    accounts: list[dict[str, str]] = []
    bindings: list[dict[str, str]] = []
    for index, account_id in enumerate(args.account_id):
        name = args.account_name[index] if args.account_name else account_id
        dm_policy = args.dm_policy[index] if args.dm_policy else "open"
        group_policy = args.group_policy[index] if args.group_policy else "open"
        accounts.append(
            {
                "accountId": account_id,
                "name": name,
                "appId": args.app_id[index],
                "appSecret": args.app_secret[index],
                "dmPolicy": dm_policy,
                "groupPolicy": group_policy,
            }
        )
        bindings.append(
            {"agentId": args.agent_id[index], "accountId": account_id, "channel": args.channel}
        )

    plan = {
        "version": 1,
        "channel": args.channel,
        "accounts": accounts,
        "bindings": bindings,
        "requiresGatewayRestart": True,
    }
    plan_path = Path(args.plan_file).expanduser()
    atomic_write_json(plan_path, plan)
    print(
        json.dumps(
            {
                "planFile": str(plan_path),
                "channel": args.channel,
                "accounts": redacted_accounts(accounts),
                "bindings": bindings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
