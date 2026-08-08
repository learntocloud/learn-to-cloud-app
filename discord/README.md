# Discord community provisioning

`community.yaml` defines the roles, categories, channels, forum tags, Community
settings, and AutoMod rules managed by `scripts/configure_discord.py`.

The provisioner updates resources by name and does not delete unmanaged Discord
resources.

## Prerequisites

Create and install a private Discord application bot with these permissions:

- Manage Server
- Manage Channels
- Manage Roles
- Moderate Members

The first run also needs Administrator if the server does not have Community
mode enabled. Remove Administrator after the first successful apply.

Set credentials in the current terminal without committing them:

```bash
export DISCORD_GUILD_ID="your-server-id"
read -s DISCORD_BOT_TOKEN
export DISCORD_BOT_TOKEN
```

## Plan and apply

Run a read-only plan:

```bash
uv run --package learn-to-cloud-shared \
  python scripts/configure_discord.py plan
```

Apply the displayed changes:

```bash
uv run --package learn-to-cloud-shared \
  python scripts/configure_discord.py apply
```

Run `plan` again after applying. It should report that no changes are required.

Discord personal notification and DM settings are not server resources and
remain manual. Configure Rules Screening and review Community Onboarding in the
Discord UI after provisioning. For an existing Community server, also set:

- Rules or Guidelines Channel: `start-here`
- Community Updates Channel: `community-updates`

Discord accepts bot requests to change these assignments but does not persist
them on an already-enabled Community server.
