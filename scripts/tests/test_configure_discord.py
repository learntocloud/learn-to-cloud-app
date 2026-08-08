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
                    "channels": [{"name": "mod-log", "type": "text"}],
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


if __name__ == "__main__":
    unittest.main()
