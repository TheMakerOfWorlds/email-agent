# Email Agent — Gmail and Google Workspace

An independent, MIT-licensed Gmail plugin for Codex, owned by [Jackson Stone](https://github.com/TheMakerOfWorlds). No paid email bridge, hosted relay, gogcli runtime, or third-party Python packages. Runtime: Python 3.9+ and macOS Keychain.

Read, search, send, organize, download attachments, and manage saved Gmail filters through compact account-explicit commands. `doctor` verifies mailbox identity and granted permissions; `scripts/auth.py` handles one-time setup.

Optional modules add **Calendar, Meet, Drive, Docs, Sheets, and Contacts** with the same company-specific account directory. The agent chooses an account first, asks when the company is unclear, and loads only the selected service's guide. [Workspace setup and capability map](docs/workspace-setup.md) explains the separate OAuth client and permissions; installing the code alone does not authorize those services.

## Set up your own installation

**Start with the [complete setup guide](setup.md).** It takes you from a fresh clone through creating your own Google Cloud project and desktop OAuth app, connecting your mailboxes, installing in Codex, checking delivery, and optionally setting up a second Mac.

Every owner supplies their own Google app and credentials. The repository maintainer receives no mailbox access from your installation. Your OAuth app being **In production** does not publish your credentials or email. Google still processes Gmail data, and mail returned to your agent is processed by your configured AI service; see [ownership, storage, and access boundaries](docs/security.md).

- [Prerequisites and clone](setup.md#before-you-start)
- [Create your Google app](setup.md#google-project-and-desktop-client)
- [Example account configuration](examples/accounts.example.json) — fictional identities; edit your private copy
- [Install the plugin in Codex](setup.md#codex-installation)
- [Verify the complete setup](setup.md#verify-your-complete-setup)
- [Second Mac and updates](setup.md#another-mac-and-later-updates)
- [Troubleshooting](setup.md#troubleshooting)
- [Privacy-notice template for your own app](docs/privacy-notice-template.md)

This setup currently requires macOS Keychain. It needs no paid email bridge or hosted relay; Codex/AI service access and any existing Google Workspace subscription are separate. The base setup connects Gmail. Connect the six optional Workspace services through their [own setup guide](docs/workspace-setup.md). Google Tasks is not implemented.

## Gmail-only access

New connections request two Gmail permissions:

- `https://www.googleapis.com/auth/gmail.modify` — read/search, send, organize labels, download attachments, move mail to Trash, and restore it.
- `https://www.googleapis.com/auth/gmail.settings.basic` — Gmail settings and saved filters.

The Gmail grant includes no Drive, Calendar, Contacts, account administration, or broad `mail.google.com` permission. Optional Workspace grants use a different desktop client and Keychain records. Gmail modify is the narrowest scope that supports Trash and restore; it does not allow immediate permanent message deletion. The Gmail client's HTTP allowlist further restricts operations to implemented mail routes. Legacy read/send grants remain usable until an account reconnects for organization/settings. Google defines these scopes in its [Gmail API documentation](https://developers.google.com/workspace/gmail/api/auth/scopes).

Each account has a short ID, an exact email address, and purpose/avoidance notes. Metadata lives in `~/.config/email-agent/accounts.json`, outside this repository. The current Gmail profile is verified before reading, sending, or cleanup; references are bound to the account identity. Cross-account replies and arbitrary From overrides are blocked.

Use company-specific account IDs when operating multiple businesses. The primary mailbox sends by default. Named aliases require both a local allowlist entry and fresh Gmail approval; `--as team` selects one explicitly. Shared aliases carry purpose notes and a `shared` flag because mail and replies can reach other people. The skill reserves them for requested or clearly implied shared correspondence, keeps personal matters in the personal account, and never selects a group sender merely because incoming mail addressed it. Alias lookup uses the existing Gmail read permission; no extra Google access is required.

## Long-lived authentication

Desktop OAuth uses PKCE S256, random state, and a loopback callback. The dedicated client and refresh tokens live in macOS Keychain; secret values never appear in process arguments or logs. Access tokens are refreshed automatically and cached only in process memory. Connecting verifies both the initial identity and a real refresh exchange.

Configure the Google OAuth app as **External / In production** to avoid the seven-day refresh-token limit imposed on external apps in Testing. This is a setup requirement, not a setting that the mail client can change. Personal-use apps can qualify for Google's verification exception. Google may still invalidate access after revocation, certain password changes, prolonged inactivity, or organization policy changes. [OAuth token expiration](https://developers.google.com/identity/protocols/oauth2#expiration), [personal-use verification exception](https://support.google.com/cloud/answer/13464323).

## Small agent context

- Synthetic measurement: 34 discovery tokens and a 641-token shared account/service router. Gmail and each Workspace service have separate on-demand references (roughly 400–650 tokens per service); no MCP tool schemas are added. The detailed advanced-mailbox reference is 1,067 tokens and loads only when needed.
- Account notes load on demand, without secrets or provider settings.
- Search retrieves only selected metadata; defaults to 10 results, hard maximum 25, with pagination.
- Search includes To/Cc and available Delivered-To values. Reads distinguish the authenticated mailbox from recipient aliases and include available forwarding, original-recipient, and mailing-list headers. Repeated delivery headers remain arrays; bounded context reports truncation. Headers do not authorize sending as an alias, and hidden Bcc/stripped routes cannot be inferred.
- Reads return 4,000 body characters by default, with `next_offset` for continuation. Raw MIME/base64 stays out of the agent response.
- HTML-only messages become text without fetching remote resources. Attachments are listed as metadata.
- Output shaping uses local code, with no extra LLM calls.

[Benchmark results](benchmarks/results.json) use synthetic fixtures and `tiktoken/o200k_base`; they are not measured billing savings. Reading a message still fetches its full body locally before returning a bounded chunk.

## Use

For Google services, start with `python3 scripts/google_agent.py accounts`, then `google_agent.py SERVICE ACCOUNT ACTION --input FILE`. The [capability map](docs/workspace-setup.md#navigation-and-implemented-capabilities) links each focused command reference. Gmail's existing command syntax below is unchanged.

Follow [setup.md](setup.md), then:

```bash
python3 scripts/email_agent.py accounts
python3 scripts/email_agent.py doctor acme
python3 scripts/email_agent.py senders acme
python3 scripts/email_agent.py search acme 'is:unread newer_than:7d'
python3 scripts/email_agent.py read 'REF_RETURNED_BY_SEARCH'
python3 scripts/email_agent.py send acme --message /path/to/message.json --preview
python3 scripts/email_agent.py send acme --as team --message /path/to/message.json --preview
```

Actual sends require a stable `--request-id`. The local SQLite ledger reserves the ID before contacting Gmail and prevents concurrent or repeated invocation with the same ID. Gmail send POSTs are never automatically retried. A crash or timeout can leave a pending/uncertain outcome; inspect Sent mail before attempting another send. This provides conservative duplicate protection, not a distributed exactly-once guarantee. The ledger stores hashes and compact outcomes, not message bodies.

Plain-text sends, verified sending aliases, Unicode, local attachments, and threaded replies are supported. Alias sends set Reply-To to that alias, and the client checks the actual stored From after Gmail sends. Reply subjects should match the original conversation. Draft requests remain local. Immediate permanent message deletion, Google-saved drafts, alias creation through the API, forwarding-rule creation, non-Google providers, background sync, and monitoring are not implemented. Gmail basic settings permission is available for future settings features; permission does not imply those commands exist yet.

## Cleanup and restore

Search and inspect candidates, collect the fixed message refs, then run `trash ACCOUNT REF [REF...]`. Use `--preview` for a local plan, and `restore ACCOUNT REF [REF...]` to undo. Each call accepts 1–25 unique refs from one verified mailbox. Drafts are rejected before the batch changes anything. The client checks each resulting Trash state and stops remaining work if an outcome is uncertain; write requests are never automatically retried. Repeating a completed operation skips messages already in the requested state.

The agent leaves uncertain or important correspondence alone during vague junk cleanup. No background cleanup runs. Trash is recoverable until Gmail automatically deletes it after 30 days; emptying Trash and immediate permanent deletion are unavailable. [Google's Trash behavior](https://support.google.com/mail/answer/7401).

## Inbox organization, attachments, and filters

`organize ACCOUNT REF [REF...] --add LABEL_ID --remove LABEL_ID` applies requested state to 1–25 fixed messages. Remove INBOX to archive and UNREAD to mark read; add STARRED or a custom label. Each result supplies the inverse changes for undo. The client verifies mailbox identity, rejects drafts/unknown custom labels, checks resulting state, and stops a batch on uncertainty. `labels` supports bounded name lookup, and `label-create` creates or reuses an exact name.

Reads expose attachment part IDs and MIME types. `attachment REF PART --output /absolute/new/file` downloads one selected attachment, capped at 25 MB, to an owner-only file without overwriting existing files or following a final-path symlink. It verifies size and reports SHA-256; it never executes the file. Search/read output remains bounded, with attachment pagination for large lists.

`filters` lists saved Gmail rules with bounded filtering/pagination. `filter-create` accepts Gmail criteria and label actions, validates the definition, checks for an existing equivalent rule, and verifies creation. Rich query syntax is passed to Gmail unchanged. `filter-delete` backs up the exact definition before removal and verifies absence. Rules affect future mail; existing mail requires a separate explicit selection. Automatic forwarding is not implemented.

Label/filter creation requires a stable request ID, recorded in a separate owner-only `operations.sqlite3`. `operation-status ID` reports the result. Pending/uncertain creation is never automatically retried. The operation ledger and deleted-filter backups stay on the originating Mac; they are not continuously shared. The complete on-demand command guide is [mailbox commands](skills/email-agent/references/mailbox.md).

## A second Mac

`scripts/sync_remote.py` installs the same reviewed version and account notes on a configured Mac over host-verified SSH. Initial setup can copy only this plugin's existing Gmail grants directly from local Keychain into remote Keychain, without Google sign-in or secret files. Later updates normally reuse the remote credentials. Each deployment verifies the installed version, enabled state, and every mailbox with a fresh process. See [remote setup](setup.md#another-mac-and-later-updates).

## Automatic updates from GitHub

After installation, opt in on each Mac:

```bash
python3 scripts/auto_update.py enable
python3 scripts/auto_update.py status
```

A native macOS login agent checks `TheMakerOfWorlds/email-agent` on GitHub's `main` branch hourly and at login, with no AI calls. New versions are tested, installed into Codex, and checked against the downloaded source. Local changes, divergent history, disabled plugins, and reused release versions stop the update. Google credentials and account notes are untouched. New Codex tasks pick up updated instructions.

Use `python3 scripts/auto_update.py disable` to stop, or `run` to check immediately. Enabling updates trusts future code published to that repository; forks can select `--repository OWNER/REPO`. See [automatic-update setup and recovery](docs/auto-updates.md).

## Development and ownership

```bash
python3 -m unittest discover -s tests -v
```

The repository owns the Gmail, OAuth, MIME, routing, and output code. It does not download or auto-update another email CLI. Dependencies on macOS, Python, and Google's APIs remain; occasional compatibility/security maintenance may still be needed. The earlier gogcli adapter and installer were removed.

Optional development tools are PyYAML for Codex validators and tiktoken for the benchmark. They are not runtime dependencies. See [VALIDATION.md](VALIDATION.md) for tested behavior and remaining live checks.

The maintainer's consent screen links to the maintainer's [public app information and privacy notice](https://gist.github.com/TheMakerOfWorlds/0ea2b4aa332d760f4a08269a8d146196), maintained in [source](docs/public-information.md). It describes that installation. For your own app, use your own contact information and [adapt the template](docs/privacy-notice-template.md). Public app information must never contain private account configuration or credentials.
