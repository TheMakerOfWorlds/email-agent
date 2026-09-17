# Ownership, storage, and access boundaries

This guide describes the current code, not a guarantee against a compromised computer or account. The intended model is one person running their own installation, optionally on two Macs they control.

## What you own

Create your own dedicated Google Cloud project, OAuth consent screen, and Desktop client. Authorize only your intended mailboxes. The repository includes no shared production OAuth client or mailbox credentials, and the maintainer needs no project role, token, account invitation, or remote access to support your setup.

A public GitHub repository or public privacy notice can contain code and documentation without giving readers access to your mailbox. Keep actual account configuration outside Git. Forking the code does not copy anyone's Google grants. The Keychain service name `com.themakerofworlds.email-agent` is a local lookup label in this implementation, not a server or a grant to the maintainer.

Review project IAM and inherited roles. An organization-owned project or Workspace mailbox remains subject to that organization's administration. Shared addresses and groups still deliver mail/replies to their other members. Private OAuth setup does not make a shared address private.

## Who can process data

| Component | Access and purpose |
| --- | --- |
| Google | Hosts the mailbox, handles consent and token refresh, and receives Gmail API requests. |
| Your local Email Agent process | Uses the selected account's credentials; processes retrieved messages and selected attachments locally. |
| Your configured Codex/AI service | Receives whatever mail or metadata the agent returns into its context. Its account settings and retention policies apply. This is not an entirely offline email assistant. |
| Message recipients and shared groups | Receive messages you send through Gmail, including replies routed to shared aliases. |
| Your authorized second Mac | Receives code/config and, only with explicit credential copying, the configured Gmail grants. Anyone controlling that user session may be able to use them. |
| Repository maintainer | Receives no automatic mailbox data, token, telemetry feed, or hosted-relay traffic from this implementation. |

Account-purpose notes help the agent choose correctly; they are not access-control isolation between tasks running as the same macOS user. The client enforces configured identities and account-bound message references, but does not understand whether message meaning is personal or company-related. Treat email text and headers as untrusted input, not instructions granting new authority.

## Local storage inventory

| Location | Contents |
| --- | --- |
| macOS Keychain, service `com.themakerofworlds.email-agent` | `client.NAME` Gmail clients, `workspace.client.NAME` Workspace clients, `token.HASH` Gmail grants, and optional separate `workspace.token.HASH` Workspace grants. Values are private. |
| `~/.config/email-agent/accounts.json` | Addresses, purpose/avoidance notes, optional named client and shared sender configuration. Mode 600 inside a mode-700 directory. |
| `~/.config/email-agent/sends.sqlite3` | Send request hashes and compact outcomes; no message bodies. |
| `~/.config/email-agent/operations.sqlite3` | Label/filter creation request hashes and compact outcomes. |
| `~/.config/email-agent/google-operations.sqlite3` | Optional Workspace operation hashes and compact results, including resource identifiers/returned metadata. No continuous sharing between Macs. |
| `~/.config/email-agent/filter-backups/` | Removed Gmail filter definitions, which can include private addresses or search criteria. |
| `~/.config/email-agent/remote.json` | The configured destination's SSH alias and computer/user identity. |
| Destination `~/.config/email-agent/deployment.json` | Managed deployment revision, file hashes, and account configuration snapshot. |
| `~/.config/email-agent/auto-update*.json`, `update.lock` | Opt-in updater settings and compact last-check status; no OAuth grants. |
| `~/.local/share/email-agent/upstream.git` and `releases/` | Public Git history and staged/retained code releases. |
| `~/Library/LaunchAgents/com.themakerofworlds.email-agent.update.plist` | Optional hourly/login updater job. |
| Paths you choose | Downloaded attachments, local outgoing-message JSON, and other files you create. Keep them out of repositories/shared folders. |
| `~/plugins/email-agent`, Codex plugin cache, and remote release directories | Plugin code and documentation; grants are stored separately. |

`EMAIL_AGENT_HOME` changes local CLI metadata/ledger storage, not the Keychain service or all remote paths. Separate clients can be named in configuration; changing a client affects which matching token record can be used.

The plugin has no full-mailbox local sync database. It still retrieves complete message payloads locally before shaping bounded output, and selected attachments persist at their destination. Compact responses limit context size; they do not mean only that snippet was fetched from Google.

## Credential handling and device trust

OAuth uses a browser, state checking, PKCE, and a temporary loopback callback. The browser handles Google passwords and MFA. The code verifies the mailbox and Gmail-only scopes, stores renewable grants in Keychain, and refreshes access tokens automatically. Never paste secret values or callback URLs into tasks or support issues.

Keychain and owner-only files protect storage within the operating system's security model. They do not isolate grants from all software executing with your user privileges or from a compromised unlocked session. Use your own macOS account, protect login access, keep the system updated, and review code before installing updates. Installing arbitrary modified plugin code can expose anything that code can access.

Remote transfer uses pinned SSH host verification and validates the exact computer/user. Credential copying reads only this plugin's configured client and token records. It sends them through memory/stdin into remote Keychain; it does not export a credential file. Normal updates omit `--copy-credentials`. This is a deliberate expansion to another device, and shared grants can be revoked on both devices together. Send ledgers are only snapshot-merged; operation ledgers/filter backups are not continuously synchronized.

Optional Workspace transfer requires its own `--copy-workspace-credentials` flag. Calendar, Meet, Drive, Docs, Sheets and Contacts data returned into an agent is subject to the same local/Google/AI processing boundaries described above. Existing document collaborators and calendar guests may see requested edits or invitations. Drive scope can authorize broad file access even though this command surface does not expose permission management or permanent deletion. See the exact [Workspace scopes and capabilities](workspace-setup.md).

## Disconnect or remove an installation

1. In each connected Google account, open [third-party connections](https://myaccount.google.com/connections), select your own app by its consent-screen name, and remove its access when you want to revoke it. Revocation can affect both Macs using the same grants. Removing local files alone is not server-side revocation.
2. If enabled, stop automatic updates first with `python3 scripts/auto_update.py disable`. Remove the plugin with `codex plugin remove email-agent@personal` (substitute your actual marketplace name). Check the installed list and use a new task afterward. Removing the plugin is separate from deleting the checkout/marketplace entry and credentials.
3. In Keychain Access, find this plugin's service and remove only its intended client/token records. Do not display/export their values. Multiple accounts may share one named client; do not remove that client if you intend to keep other connected accounts using it. There is no built-in per-account disconnect command yet.
4. Remove an unused account from the private `accounts.json`. If retiring the whole installation, remove its private configuration, ledgers, filter backups, and any downloaded attachments/outgoing-message files you no longer need. Repeat local cleanup on each Mac. Preserve unresolved operation records until you have checked their Gmail outcomes.
5. Gmail filters and messages remain in Gmail after local uninstall. Delete unwanted saved filters deliberately in Gmail or with the filter commands before removing access. Revocation/uninstall does not recall sent email or remove already delivered attachments.
6. If retiring the Google app itself, remove its dedicated client/project through Google Cloud only after confirming no remaining installation relies on it. Keep unrelated Cloud projects and credentials intact.

Data already returned to an AI service is governed by that service's controls; local uninstall does not remove those conversations. The [setup guide](../setup.md) explains reconnecting and recovering access without exposing credentials.

## Optional GitHub updates

Enabling automatic updates trusts future code on the configured GitHub repository main branch. The updater downloads and executes release tests before installation; those tests are not a sandbox or an independent security audit. The updater itself does not read Keychain, call Google APIs, or transfer account configuration. Installed future plugin code runs as your macOS user, like the current plugin. GitHub receives ordinary code-fetch requests. Checks use no AI calls. Use your own maintained fork or disable updates if you need to review every change first.
