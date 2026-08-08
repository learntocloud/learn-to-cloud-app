#!/usr/bin/env python3
"""Plan and apply the Learn to Cloud Discord server configuration."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

API_BASE = "https://discord.com/api/v10"
CONFIG_PATH = Path(__file__).resolve().parents[1] / "discord" / "community.yaml"

CHANNEL_TYPES = {"text": 0, "category": 4, "forum": 15}
PERMISSIONS = {
    "view_channel": 1 << 10,
    "send_messages": 1 << 11,
    "manage_messages": 1 << 13,
    "manage_threads": 1 << 34,
    "create_public_threads": 1 << 35,
    "create_private_threads": 1 << 36,
    "send_messages_in_threads": 1 << 38,
    "moderate_members": 1 << 40,
}
REQUIRE_TAG = 1 << 4
READ_ONLY_DENY = sum(
    PERMISSIONS[name]
    for name in (
        "send_messages",
        "create_public_threads",
        "create_private_threads",
        "send_messages_in_threads",
    )
)


class DiscordError(RuntimeError):
    """An unsuccessful Discord API response."""


class DiscordClient:
    """Minimal Discord REST API client."""

    def __init__(self, token: str) -> None:
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            f"{API_BASE}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bot {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "LearnToCloudCommunityManager/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise DiscordError(
                f"{method} {path} failed with HTTP {error.code}: {detail}"
            ) from error
        except urllib.error.URLError as error:
            raise DiscordError(f"{method} {path} failed: {error.reason}") from error
        return json.loads(body) if body else None


@dataclass(frozen=True)
class Action:
    """A planned Discord configuration change."""

    verb: str
    resource: str


class Provisioner:
    """Reconcile managed Discord resources without deleting unmanaged resources."""

    def __init__(
        self,
        client: DiscordClient,
        guild_id: str,
        config: dict[str, Any],
        *,
        apply: bool,
    ) -> None:
        self.client = client
        self.guild_id = guild_id
        self.config = config
        self.apply = apply
        self.actions: list[Action] = []

    def run(self) -> list[Action]:
        guild = self.client.request("GET", f"/guilds/{self.guild_id}")
        roles = self.client.request("GET", f"/guilds/{self.guild_id}/roles")
        channels = self.client.request("GET", f"/guilds/{self.guild_id}/channels")

        roles_by_name = {role["name"]: role for role in roles}
        self._reconcile_roles(roles_by_name)

        channels_by_name = {channel["name"]: channel for channel in channels}
        self._reconcile_non_forum_channels(channels_by_name, roles_by_name)
        if self.apply:
            channels = self.client.request("GET", f"/guilds/{self.guild_id}/channels")
            channels_by_name = {channel["name"]: channel for channel in channels}

        self._reconcile_community(guild, channels_by_name)
        self._reconcile_forum_channels(channels_by_name, roles_by_name)
        if self.apply:
            channels = self.client.request("GET", f"/guilds/{self.guild_id}/channels")
            channels_by_name = {channel["name"]: channel for channel in channels}

        self._reconcile_automod(channels_by_name)
        return self.actions

    def _record(self, verb: str, resource: str) -> None:
        self.actions.append(Action(verb, resource))

    def _reconcile_roles(self, roles_by_name: dict[str, dict[str, Any]]) -> None:
        for role_config in self.config["roles"]:
            name = role_config["name"]
            payload = {
                "name": name,
                "permissions": str(
                    sum(
                        PERMISSIONS[permission]
                        for permission in role_config.get("permissions", [])
                    )
                ),
                "hoist": role_config.get("hoist", False),
                "mentionable": role_config.get("mentionable", False),
            }
            existing = roles_by_name.get(name)
            if existing is None:
                self._record("create", f"role {name}")
                if self.apply:
                    created = self.client.request(
                        "POST", f"/guilds/{self.guild_id}/roles", payload
                    )
                else:
                    created = {
                        **payload,
                        "id": f"planned:{name}",
                    }
                roles_by_name[name] = created
            elif any(
                str(existing.get(key)) != str(value) for key, value in payload.items()
            ):
                self._record("update", f"role {name}")
                if self.apply:
                    self.client.request(
                        "PATCH",
                        f"/guilds/{self.guild_id}/roles/{existing['id']}",
                        payload,
                    )

    def _reconcile_non_forum_channels(
        self,
        channels_by_name: dict[str, dict[str, Any]],
        roles_by_name: dict[str, dict[str, Any]],
    ) -> None:
        for category in self.config["categories"]:
            category_channel = self._ensure_category(
                category, channels_by_name, roles_by_name
            )
            for channel in category["channels"]:
                if channel["type"] == "forum":
                    continue
                self._ensure_channel(channel, category_channel, channels_by_name)

    def _reconcile_forum_channels(
        self,
        channels_by_name: dict[str, dict[str, Any]],
        roles_by_name: dict[str, dict[str, Any]],
    ) -> None:
        for category in self.config["categories"]:
            category_channel = self._ensure_category(
                category, channels_by_name, roles_by_name
            )
            for channel in category["channels"]:
                if channel["type"] != "forum":
                    continue
                self._ensure_channel(channel, category_channel, channels_by_name)

    def _ensure_category(
        self,
        config: dict[str, Any],
        channels_by_name: dict[str, dict[str, Any]],
        roles_by_name: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        name = config["name"]
        existing = channels_by_name.get(name)
        if existing is not None:
            if existing["type"] != CHANNEL_TYPES["category"]:
                raise DiscordError(
                    f"Cannot manage category {name}: that name is used by "
                    "a different channel type"
                )
            return existing

        payload: dict[str, Any] = {
            "name": name,
            "type": CHANNEL_TYPES["category"],
        }
        if config.get("private"):
            overwrites = [
                {
                    "id": self.guild_id,
                    "type": 0,
                    "allow": "0",
                    "deny": str(PERMISSIONS["view_channel"]),
                }
            ]
            for role_name in config.get("allowed_roles", []):
                role = roles_by_name.get(role_name)
                if role is None:
                    raise DiscordError(
                        f"Cannot create private category {name}: "
                        f"role {role_name} does not exist"
                    )
                overwrites.append(
                    {
                        "id": role["id"],
                        "type": 0,
                        "allow": str(PERMISSIONS["view_channel"]),
                        "deny": "0",
                    }
                )
            payload["permission_overwrites"] = overwrites

        self._record("create", f"category {name}")
        if self.apply:
            created = self.client.request(
                "POST", f"/guilds/{self.guild_id}/channels", payload
            )
        else:
            created = {
                "id": f"planned:{name}",
                "name": name,
                "type": CHANNEL_TYPES["category"],
            }
        channels_by_name[name] = created
        return created

    def _ensure_channel(
        self,
        config: dict[str, Any],
        category: dict[str, Any],
        channels_by_name: dict[str, dict[str, Any]],
    ) -> None:
        name = config["name"]
        payload: dict[str, Any] = {
            "name": name,
            "type": CHANNEL_TYPES[config["type"]],
            "parent_id": category["id"],
            "topic": config.get("topic"),
        }
        if "rate_limit_per_user" in config:
            payload["rate_limit_per_user"] = config["rate_limit_per_user"]
        if config.get("read_only"):
            payload["permission_overwrites"] = [
                {
                    "id": self.guild_id,
                    "type": 0,
                    "allow": "0",
                    "deny": str(READ_ONLY_DENY),
                }
            ]
        if config["type"] == "forum":
            payload.update(
                {
                    "available_tags": [
                        {"name": tag, "moderated": False}
                        for tag in config.get("tags", [])
                    ],
                    "default_auto_archive_duration": config.get(
                        "default_auto_archive_duration", 4320
                    ),
                    "default_forum_layout": 1,
                    "default_sort_order": 0,
                    "flags": REQUIRE_TAG if config.get("require_tag") else 0,
                }
            )

        existing = channels_by_name.get(name)
        if existing is None:
            self._record("create", f"{config['type']} channel {name}")
            if self.apply:
                created = self.client.request(
                    "POST", f"/guilds/{self.guild_id}/channels", payload
                )
            else:
                created = {
                    **payload,
                    "id": f"planned:{name}",
                    "available_tags": payload.get("available_tags", []),
                    "flags": payload.get("flags", 0),
                }
            channels_by_name[name] = created
            return
        if existing["type"] != CHANNEL_TYPES[config["type"]]:
            raise DiscordError(
                f"Cannot manage channel {name}: its existing type does not match "
                f"{config['type']}"
            )

        current_tags = [tag["name"] for tag in existing.get("available_tags", [])]
        desired_tags = config.get("tags", [])
        differences: list[str] = []
        if existing.get("parent_id") != category["id"]:
            differences.append("category")
        if (existing.get("topic") or None) != (payload["topic"] or None):
            differences.append("topic")
        if (existing.get("rate_limit_per_user") or 0) != payload.get(
            "rate_limit_per_user", 0
        ):
            differences.append("slowmode")
        if set(current_tags) != set(desired_tags):
            differences.append("tags")
        if config["type"] == "forum" and bool(
            existing.get("flags", 0) & REQUIRE_TAG
        ) != config.get("require_tag", False):
            differences.append("required-tag")
        everyone_overwrite = next(
            (
                overwrite
                for overwrite in existing.get("permission_overwrites", [])
                if overwrite["id"] == self.guild_id and overwrite["type"] == 0
            ),
            None,
        )
        current_deny = int(everyone_overwrite["deny"]) if everyone_overwrite else 0
        if config.get("read_only") and current_deny & READ_ONLY_DENY != READ_ONLY_DENY:
            differences.append("read-only")
            preserved_overwrites = [
                dict(overwrite)
                for overwrite in existing.get("permission_overwrites", [])
                if not (
                    overwrite["id"] == self.guild_id and overwrite["type"] == 0
                )
            ]
            preserved_overwrites.append(
                {
                    "id": self.guild_id,
                    "type": 0,
                    "allow": (
                        everyone_overwrite["allow"] if everyone_overwrite else "0"
                    ),
                    "deny": str(current_deny | READ_ONLY_DENY),
                }
            )
            payload["permission_overwrites"] = preserved_overwrites
        if differences:
            detail = ", ".join(differences)
            self._record(
                "update", f"{config['type']} channel {name} ({detail})"
            )
            if self.apply:
                payload.pop("type")
                self.client.request("PATCH", f"/channels/{existing['id']}", payload)

    def _reconcile_community(
        self,
        guild: dict[str, Any],
        channels_by_name: dict[str, dict[str, Any]],
    ) -> None:
        start_here = channels_by_name.get("start-here")
        community_updates = channels_by_name.get("community-updates")
        if start_here is None or community_updates is None:
            if self.apply:
                raise DiscordError(
                    "start-here and community-updates are required before "
                    "Community setup"
                )
            self._record("enable", "Community server features")
            return

        payload: dict[str, Any] = {
            "description": self.config["server"]["description"],
            "verification_level": max(guild.get("verification_level", 0), 1),
            "explicit_content_filter": 2,
        }
        community_enabled = "COMMUNITY" in guild.get("features", [])
        if not community_enabled:
            payload.update(
                {
                    "rules_channel_id": start_here["id"],
                    "public_updates_channel_id": community_updates["id"],
                    "features": sorted(
                        set(guild.get("features", [])) | {"COMMUNITY"}
                    ),
                }
            )
        differences = [
            key
            for key, value in payload.items()
            if key != "features" and guild.get(key) != value
        ]
        if not community_enabled:
            self._record("enable", "Community server features")
            if self.apply:
                self.client.request("PATCH", f"/guilds/{self.guild_id}", payload)
        elif differences:
            detail = ", ".join(differences)
            self._record("update", f"Community server settings ({detail})")
            if self.apply:
                payload.pop("features")
                self.client.request("PATCH", f"/guilds/{self.guild_id}", payload)

    def _reconcile_automod(
        self, channels_by_name: dict[str, dict[str, Any]]
    ) -> None:
        existing_rules = self.client.request(
            "GET", f"/guilds/{self.guild_id}/auto-moderation/rules"
        )
        rules_by_name = {rule["name"]: rule for rule in existing_rules}
        for config in self.config.get("automod", []):
            if config["trigger"] != "mention_spam":
                raise DiscordError(f"Unsupported AutoMod trigger: {config['trigger']}")
            alert_channel = channels_by_name.get(config["alert_channel"])
            if alert_channel is None:
                if self.apply:
                    raise DiscordError(
                        f"AutoMod alert channel {config['alert_channel']} is missing"
                    )
                continue
            payload = {
                "name": config["name"],
                "event_type": 1,
                "trigger_type": 5,
                "trigger_metadata": {
                    "mention_total_limit": config["mention_limit"],
                    "mention_raid_protection_enabled": config["raid_protection"],
                },
                "actions": [
                    {
                        "type": 1,
                        "metadata": {"custom_message": config["block_message"]},
                    },
                    {"type": 2, "metadata": {"channel_id": alert_channel["id"]}},
                ],
                "enabled": True,
            }
            existing = rules_by_name.get(config["name"])
            if existing is None:
                self._record("create", f"AutoMod rule {config['name']}")
                if self.apply:
                    self.client.request(
                        "POST",
                        f"/guilds/{self.guild_id}/auto-moderation/rules",
                        payload,
                    )
            elif any(existing.get(key) != value for key, value in payload.items()):
                self._record("update", f"AutoMod rule {config['name']}")
                if self.apply:
                    self.client.request(
                        "PATCH",
                        (
                            f"/guilds/{self.guild_id}/auto-moderation/rules/"
                            f"{existing['id']}"
                        ),
                        payload,
                    )


def load_config(path: Path) -> dict[str, Any]:
    """Load the declarative server configuration."""
    with path.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    if not isinstance(config, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return config


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "apply", "inventory"))
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    return parser.parse_args()


def print_inventory(channels: list[dict[str, Any]]) -> None:
    """Print categories and channels without exposing credentials."""
    type_names = {
        0: "text",
        2: "voice",
        4: "category",
        5: "announcement",
        13: "stage",
        15: "forum",
        16: "media",
    }
    categories = sorted(
        (channel for channel in channels if channel["type"] == 4),
        key=lambda channel: channel.get("position", 0),
    )
    grouped: dict[str | None, list[dict[str, Any]]] = {}
    for channel in channels:
        if channel["type"] != 4:
            grouped.setdefault(channel.get("parent_id"), []).append(channel)

    def print_channels(children: list[dict[str, Any]]) -> None:
        for channel in sorted(
            children, key=lambda item: item.get("position", 0)
        ):
            type_name = type_names.get(channel["type"], f"type-{channel['type']}")
            print(f"  {type_name:12} {channel['name']}")

    for category in categories:
        print(f"CATEGORY {category['name']}")
        print_channels(grouped.pop(category["id"], []))
    if ungrouped := grouped.pop(None, []):
        print("UNCATEGORIZED")
        print_channels(ungrouped)
    for parent_id, children in grouped.items():
        print(f"UNKNOWN CATEGORY {parent_id}")
        print_channels(children)


def main() -> int:
    """Run the Discord configuration reconciliation."""
    args = parse_args()
    token = os.environ.get("DISCORD_BOT_TOKEN")
    guild_id = os.environ.get("DISCORD_GUILD_ID")
    if not token or not guild_id:
        print(
            "Set DISCORD_BOT_TOKEN and DISCORD_GUILD_ID before running this command.",
            file=sys.stderr,
        )
        return 2

    try:
        client = DiscordClient(token)
        bot = client.request("GET", "/users/@me")
        if args.command == "inventory":
            channels = client.request("GET", f"/guilds/{guild_id}/channels")
            print(f"Authenticated as {bot['username']} ({bot['id']}).")
            print_inventory(channels)
            return 0
        actions = Provisioner(
            client,
            guild_id,
            load_config(args.config),
            apply=args.command == "apply",
        ).run()
    except (DiscordError, OSError, ValueError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"Authenticated as {bot['username']} ({bot['id']}).")
    if not actions:
        print("No changes required.")
        return 0
    for action in actions:
        print(f"{action.verb.upper():7} {action.resource}")
    if args.command == "plan":
        print("Plan only; run with 'apply' to make these changes.")
    else:
        print(f"Applied {len(actions)} change(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
