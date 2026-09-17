# Guided setup for a new or returning user

Use this mode for “set this up,” “connect my Google account,” first-time installation, or a missing-connection error. Assume no knowledge of plugins, OAuth, JSON, terminals, or Google Cloud unless the user demonstrates it. Help complete the work rather than only linking a manual.

## Find the current stage

Read [the beginner guide](../../../docs/getting-started.md), then only the relevant section of [technical setup](../../../setup.md) or [Workspace setup](../../../docs/workspace-setup.md). Use this repository's instructions even when the plugin is not installed yet. Source paths and installed cache paths are different: edit/register the source checkout, never treat a cache copy as the development source.

Inspect OS, available Python/Git/Codex commands, source/marketplace/installed state, and existing account configuration without exposing secrets. A missing accounts file is normal on first setup, not a reason to stop. Preserve working configuration, private purpose notes, client choices, and explicit update preferences. Do not recreate a Google project/client or reauthorize a working account merely because setup is requested.

Establish only what is missing: exact account, company/personal purpose, selected services, and appropriate project owner. Start with one requested account; Gmail is the beginner default when the user wants email, but do not force Gmail consent for someone who only requested Calendar/Docs. For a Workspace-only setup, use the base guide's prerequisites/account configuration/plugin installation and skip Gmail API/client/consent; use the separate Workspace guide instead. Ask when company identity is ambiguous. Never use the maintainer's accounts, project, or credentials for another person.

## Guide the human, do the agent work

Explain the current stage, why it exists, and what success looks like in plain language. Give the user one manageable screen or short group of related steps at a time. Do routine commands, configuration edits, and authorized browser work yourself when tools permit. Do not dump the whole manual into chat or ask for confirmation after every routine step. A longer explanation is appropriate when the user asks; avoid unexplained jargon.

If browser control is unavailable, give exact navigation, the field value or choice, and the expected result; do not invent the screen state. Have the user handle passwords, passkeys, and user-only verification directly in Google. Keep credentials, codes, and callback URLs out of conversation, logs, and Git. Tell them exactly which personal action remains and resume after it. Follow applicable tool confirmation rules for permission grants without repeatedly asking for authority already supplied.

If a command has placeholders, replace them using verified local context before running it. If the user must run it, clearly identify each replacement. Never execute fictional `.example` accounts. Store real notes in the private config; do not modify tracked examples with personal data. Shared aliases need shared-purpose notes and are distinct from authenticated Calendar/Meet identity.

Google setup order matters: correct owner/project, selected APIs and scopes, appropriate audience/publishing status, Desktop client, secure import, then account consent. Use the exact current scope tables and commands from the technical guides rather than reproducing them here. Explain the private-app model and that In production is not public mailbox access or Google verification. Do not activate billing or unrelated services as a shortcut.

## Verify before advancing

Use concrete checkpoints from the guides. A saved client is not an account connection; a browser callback is not final authentication; code installation is not consent; a general doctor check is not proof every service works. Verify exact account identity, refresh, and a minimal read-only operation for each requested service. Do not send messages/invites or modify user resources as an unrequested setup test. An empty successful result can be valid.

Register the personal marketplace using the supported helper before `scripts/install.py`. Explain that standard first installation enables hourly GitHub updates, and preserve an explicit opt-out. A direct Codex plugin-add command bypasses that installer behavior. Start a new task to test skill discovery after installation. Check the updater separately from account authentication.

When something fails, inspect the latest state and preserve successful stages. Distinguish a missing command, wrong working directory/profile, API disabled, missing scope, administrator block, and user-only sign-in. Do not solve permission failure by switching accounts. Never claim completion based only on an attempted command.

Close with a short per-account summary of verified services, plugin/update state on each intended Mac, and exact remaining blockers. Include a few examples using that person's account nicknames, without sending or changing anything. Keep unconnected Workspace services marked pending even when Gmail works.
