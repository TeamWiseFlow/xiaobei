#!/usr/bin/env python3
import json
import os
from pathlib import Path
from typing import Any


WORK_CHANNELS = {"feishu", "wecom"}


def config_path() -> Path:
    return Path(
        os.environ.get(
            "OPENCLAW_CONFIG_PATH",
            Path(os.environ.get("OPENCLAW_STATE_DIR") or Path.home() / ".openclaw")
            / "openclaw.json",
        )
    ).expanduser()


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"openclaw config not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in openclaw config {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"openclaw config must be a JSON object: {path}")
    return payload


def configured_accounts(channels: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for channel in WORK_CHANNELS:
        channel_config = channels.get(channel)
        if not isinstance(channel_config, dict):
            continue
        accounts = channel_config.get("accounts")
        if not isinstance(accounts, dict):
            continue
        result[channel] = []
        for account_id, value in sorted(accounts.items()):
            account = value if isinstance(value, dict) else {}
            credentials = (
                {"hasBotId": bool(account.get("botId")), "hasSecret": bool(account.get("secret"))}
                if channel == "wecom"
                else {"hasAppId": bool(account.get("appId")), "hasAppSecret": bool(account.get("appSecret"))}
            )
            result[channel].append({
                "accountId": account_id,
                "name": account.get("name"),
                **credentials,
                "dmPolicy": account.get("dmPolicy"),
                "groupPolicy": account.get("groupPolicy"),
            })
    return result


def main() -> None:
    path = config_path()
    config = load_config(path)
    raw_agents = config.get("agents")
    raw_agents_entries = raw_agents.get("entries") if isinstance(raw_agents, dict) else None
    raw_agents_list = raw_agents.get("list", []) if isinstance(raw_agents, dict) else []
    agents = set(raw_agents_entries) if isinstance(raw_agents_entries, dict) else {
        agent.get("id")
        for agent in raw_agents_list
        if isinstance(agent, dict) and agent.get("id")
    }
    bindings = config.get("bindings") if isinstance(config.get("bindings"), list) else []
    channels = config.get("channels") if isinstance(config.get("channels"), dict) else {}

    agent_bindings: dict[str, list[dict[str, Any]]] = {}
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        agent_id = binding.get("agentId")
        match = binding.get("match")
        if not isinstance(match, dict):
            continue
        channel = match.get("channel")
        account_id = match.get("accountId")
        if not agent_id or not channel:
            continue
        agent_bindings.setdefault(agent_id, []).append(
            {"channel": channel, "accountId": account_id}
        )

    summary = {
        "configPath": str(path),
        "agents": sorted(agents),
        "enabledChannels": sorted(
            name
            for name, value in channels.items()
            if isinstance(value, dict) and value.get("enabled") is not False
        ),
        "workChannelsConfigured": sorted(name for name in WORK_CHANNELS if name in channels),
        "workChannelAccounts": configured_accounts(channels),
        "bindings": agent_bindings,
        "itEngineerHasWorkBinding": any(
            item["channel"] in WORK_CHANNELS
            for item in agent_bindings.get("it-engineer", [])
        ),
        "hrbpEnabled": "hrbp" in agents,
        "hrbpHasWorkBinding": any(
            item["channel"] in WORK_CHANNELS for item in agent_bindings.get("hrbp", [])
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
