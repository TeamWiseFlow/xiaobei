#!/usr/bin/env python3
import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_CHANNELS = {"feishu", "wecom"}


def config_path() -> Path:
    return Path(
        os.environ.get(
            "OPENCLAW_CONFIG_PATH",
            Path.home() / ".openclaw" / "openclaw.json",
        )
    ).expanduser()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {label} {path}: {exc}") from exc
    except OSError as exc:
        raise SystemExit(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} must be a JSON object: {path}")
    return payload


def ensure_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if value is None:
        value = {}
        parent[key] = value
    if not isinstance(value, dict):
        raise SystemExit(f"config.{key} must be an object")
    return value


def ensure_list(parent: dict[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if value is None:
        value = []
        parent[key] = value
    if not isinstance(value, list):
        raise SystemExit(f"config.{key} must be an array")
    return value


def validated_plan(plan: dict[str, Any]) -> tuple[str, list[dict[str, str]], list[dict[str, str]]]:
    version = plan.get("version")
    if version != 1:
        raise SystemExit("plan.version must be 1")
    channel = plan.get("channel")
    if channel not in VALID_CHANNELS:
        raise SystemExit("plan.channel must be feishu or wecom")

    raw_accounts = plan.get("accounts")
    if not isinstance(raw_accounts, list):
        raise SystemExit("plan.accounts must be an array")
    accounts: list[dict[str, str]] = []
    for index, item in enumerate(raw_accounts):
        if not isinstance(item, dict):
            raise SystemExit(f"plan.accounts[{index}] must be an object")
        account_id = item.get("accountId")
        app_id = item.get("appId")
        app_secret = item.get("appSecret")
        name = item.get("name") or account_id
        dm_policy = item.get("dmPolicy") or "open"
        group_policy = item.get("groupPolicy") or "open"
        for field, value in {
            "accountId": account_id,
            "appId": app_id,
            "appSecret": app_secret,
            "name": name,
            "dmPolicy": dm_policy,
            "groupPolicy": group_policy,
        }.items():
            if not isinstance(value, str) or not value.strip():
                raise SystemExit(f"plan.accounts[{index}].{field} must be a non-empty string")
        accounts.append(
            {
                "accountId": account_id.strip(),
                "name": name.strip(),
                "appId": app_id.strip(),
                "appSecret": app_secret,
                "dmPolicy": dm_policy.strip(),
                "groupPolicy": group_policy.strip(),
            }
        )

    raw_bindings = plan.get("bindings")
    if not isinstance(raw_bindings, list):
        raise SystemExit("plan.bindings must be an array")

    account_ids = {account["accountId"] for account in accounts}
    bindings: list[dict[str, str]] = []
    for index, item in enumerate(raw_bindings):
        if not isinstance(item, dict):
            raise SystemExit(f"plan.bindings[{index}] must be an object")
        agent_id = item.get("agentId")
        account_id = item.get("accountId")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise SystemExit(f"plan.bindings[{index}].agentId must be a non-empty string")
        if not isinstance(account_id, str) or not account_id.strip():
            raise SystemExit(f"plan.bindings[{index}].accountId must be a non-empty string")
        if account_id.strip() not in account_ids:
            raise SystemExit(f"plan.bindings[{index}].accountId has no matching account")
        bindings.append({"agentId": agent_id.strip(), "accountId": account_id.strip()})
    return channel, accounts, bindings


def binding_exists(
    bindings: list[Any],
    agent_id: str,
    channel: str,
    account_id: str,
) -> bool:
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        match = binding.get("match")
        if not isinstance(match, dict):
            continue
        if (
            binding.get("agentId") == agent_id
            and match.get("channel") == channel
            and match.get("accountId") == account_id
        ):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply a confirmed work channel binding plan."
    )
    parser.add_argument("--plan-file", required=True)
    args = parser.parse_args()

    plan_path = Path(args.plan_file).expanduser()
    plan = load_json_object(plan_path, "plan")
    channel, plan_accounts, plan_bindings = validated_plan(plan)

    path = config_path()
    config = load_json_object(path, "openclaw config")
    backup = path.with_suffix(
        path.suffix
        + ".bak-"
        + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    )
    shutil.copy2(path, backup)

    channels = ensure_dict(config, "channels")
    channel_config = channels.setdefault(channel, {"enabled": True, "accounts": {}})
    if not isinstance(channel_config, dict):
        raise SystemExit(f"config.channels.{channel} must be an object")
    channel_config["enabled"] = True
    accounts_config = channel_config.setdefault("accounts", {})
    if not isinstance(accounts_config, dict):
        raise SystemExit(f"config.channels.{channel}.accounts must be an object")
    for account in plan_accounts:
        account_id = account["accountId"]
        accounts_config[account_id] = {
            **(accounts_config.get(account_id) if isinstance(accounts_config.get(account_id), dict) else {}),
            "name": account["name"],
            "appId": account["appId"],
            "appSecret": account["appSecret"],
            "dmPolicy": account["dmPolicy"],
            "groupPolicy": account["groupPolicy"],
        }

    plugins = ensure_dict(config, "plugins")
    plugin_entries = ensure_dict(plugins, "entries")
    plugin_config = plugin_entries.setdefault(channel, {"enabled": True})
    if not isinstance(plugin_config, dict):
        raise SystemExit(f"config.plugins.entries.{channel} must be an object")
    plugin_config["enabled"] = True

    bindings = ensure_list(config, "bindings")
    for item in plan_bindings:
        agent_id = item["agentId"]
        account_id = item["accountId"]
        if binding_exists(bindings, agent_id, channel, account_id):
            continue
        bindings.append(
            {
                "agentId": agent_id,
                "comment": f"{channel}:{account_id} -> {agent_id}",
                "match": {"channel": channel, "accountId": account_id},
            }
        )

    atomic_write_json(path, config)
    print(
        json.dumps(
            {"updated": str(path), "backup": str(backup), "channel": channel},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
