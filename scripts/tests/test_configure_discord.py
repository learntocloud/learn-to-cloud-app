from __future__ import annotations

import unittest
from typing import Any

from scripts.configure_discord import Provisioner


class FakeDiscordClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append((method, path, payload))
        if path == "/guilds/guild":
            return {
                "features": [],
                "verification_level": 0,
                "explicit_content_filter": 0,
            }
        if path == "/guilds/guild/roles":
            return [{"id": "guild", "name": "@everyone"}]
        if path == "/guilds/guild/channels":
            return []
        if path == "/guilds/guild/auto-moderation/rules":
            return []
        raise AssertionError(f"Unexpected request: {method} {path}")


class ProvisionerTests(unittest.TestCase):
    def test_plan_includes_managed_resources_without_writes(self) -> None:
        client = FakeDiscordClient()
        config = {
            "server": {"description": "Community"},
            "roles": [{"name": "Community Helper"}],
            "categories": [
                {
                    "name": "START HERE",
                    "channels": [
                        {"name": "start-here", "type": "text"},
                        {"name": "announcements", "type": "text"},
                    ],
                },
                {
                    "name": "LEARN",
                    "channels": [
                        {
                            "name": "curriculum-help",
                            "type": "forum",
                            "require_tag": True,
                            "tags": ["phase-0"],
                        }
                    ],
                },
                {
                    "name": "STAFF",
                    "private": True,
                    "allowed_roles": ["Community Helper"],
                    "channels": [
                        {"name": "community-updates", "type": "text"},
                        {"name": "mod-log", "type": "text"},
                    ],
                },
            ],
            "automod": [
                {
                    "name": "Block mention spam",
                    "trigger": "mention_spam",
                    "mention_limit": 5,
                    "raid_protection": True,
                    "block_message": "Too many mentions.",
                    "alert_channel": "mod-log",
                }
            ],
        }

        actions = Provisioner(client, "guild", config, apply=False).run()

        resources = {action.resource for action in actions}
        self.assertIn("role Community Helper", resources)
        self.assertIn("category START HERE", resources)
        self.assertIn("text channel start-here", resources)
        self.assertIn("forum channel curriculum-help", resources)
        self.assertIn("Community server features", resources)
        self.assertIn("AutoMod rule Block mention spam", resources)
        self.assertFalse(
            any(method != "GET" for method, _, _ in client.calls),
            "plan must not write to Discord",
        )

    def test_equivalent_forum_values_do_not_trigger_update(self) -> None:
        client = FakeDiscordClient()
        client.request = lambda method, path, payload=None: {
            "/guilds/guild": {
                "features": ["COMMUNITY"],
                "description": "Community",
                "verification_level": 1,
                "explicit_content_filter": 2,
                "rules_channel_id": "start",
                "public_updates_channel_id": "community-updates",
            },
            "/guilds/guild/roles": [{"id": "guild", "name": "@everyone"}],
            "/guilds/guild/channels": [
                {"id": "category", "name": "LEARN", "type": 4},
                {
                    "id": "start",
                    "name": "start-here",
                    "type": 0,
                    "parent_id": "category",
                    "topic": None,
                },
                {
                    "id": "community-updates",
                    "name": "community-updates",
                    "type": 0,
                    "parent_id": "category",
                    "topic": None,
                },
                {
                    "id": "forum",
                    "name": "curriculum-help",
                    "type": 15,
                    "parent_id": "category",
                    "topic": None,
                    "rate_limit_per_user": None,
                    "available_tags": [
                        {"id": "2", "name": "resolved"},
                        {"id": "1", "name": "phase-0"},
                    ],
                    "flags": 16,
                },
            ],
            "/guilds/guild/auto-moderation/rules": [],
        }[path]
        config = {
            "server": {"description": "Community"},
            "roles": [],
            "categories": [
                {
                    "name": "LEARN",
                    "channels": [
                        {"name": "start-here", "type": "text"},
                        {"name": "community-updates", "type": "text"},
                        {
                            "name": "curriculum-help",
                            "type": "forum",
                            "require_tag": True,
                            "tags": ["phase-0", "resolved"],
                        },
                    ],
                }
            ],
            "automod": [],
        }

        actions = Provisioner(client, "guild", config, apply=False).run()

        self.assertEqual(actions, [])


if __name__ == "__main__":
    unittest.main()
