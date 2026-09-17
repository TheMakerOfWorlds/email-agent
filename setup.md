# Setup

**First time setting up a plugin?** Start with the [beginner walkthrough](docs/getting-started.md). It explains the terminology, what each stage does, and how to ask an agent to guide you. This page is the detailed command/settings reference; you do not need to understand it all before starting.

This is a bring-your-own-Google-app setup: you own the Cloud project, consent screen, desktop OAuth client, and connected mailboxes. You do not sign into the maintainer's OAuth app or send the maintainer any credentials. Read [ownership and privacy](docs/security.md) for the actual access boundaries.

This page covers the **Gmail connection**. For Calendar, Meet, Drive, Docs, Sheets, or Contacts, follow the [optional Workspace setup](docs/workspace-setup.md) after installing the base plugin. Those permissions are isolated from Gmail and require separate consent.

Follow the sections in order through connection, Codex installation, and verification. Aliases and the second Mac are optional. Commands run in the cloned repository unless stated otherwise. Google console labels can change; official links below were checked September 16, 2026.

## Before you start

- A Mac with Python 3.9+, Git, and an accessible login Keychain. Windows/Linux credential storage is not implemented.
- Codex installed and signed in, with its CLI available and local plugins supported. Run `codex plugin --help` to check. Codex/AI usage is separate from this plugin; the plugin does not supply an AI subscription.
- Access to the Google accounts you intend to connect, including their passwords/passkeys/MFA. Workspace administrators may restrict third-party apps.
- A Google account permitted to create a dedicated Cloud project. For an independently owned personal installation, use an account and project you control. A project inside an employer's organization remains subject to its administrators and policies.

```bash
python3 --version
git --version
codex plugin --help
mkdir -p "$HOME/plugins"
git clone https://github.com/TheMakerOfWorlds/google-workspace-agent.git "$HOME/plugins/email-agent"
cd "$HOME/plugins/email-agent"
```

If the repository is private, GitHub must grant your account access; a `Repository not found` error can mean missing access. If you have a fork, substitute its clone URL. Do not put GitHub tokens in clone URLs. If `~/plugins/email-agent` already exists, inspect it and use the existing checkout instead of overwriting it. To keep a checkout elsewhere, use a symlink at `~/plugins/email-agent` pointing to that checkout; this path is what the default personal marketplace resolves.

No Python package installation, API key, service account, paid email bridge, or hosted server is needed for the runtime. Do not activate a Cloud trial or attach billing as part of this Gmail-only setup. Google still applies [Gmail API quotas](https://developers.google.com/workspace/gmail/api/reference/quota).

## Google project and desktop client

### 1. Create a project you own

Open [Google Cloud Console](https://console.cloud.google.com/), check the signed-in owner account, then use the project selector → **New project**. Name it something recognizable, such as **My Email Agent**. Select **No organization** if offered and appropriate for your personal installation. A Workspace account may require its organization instead. Keep this project selected for all following steps. Under **IAM & Admin → IAM**, review who can administer the project, including inherited access. You do not need to add the repository maintainer. [Google project instructions](https://developers.google.com/workspace/guides/create-project).

Open **APIs & Services → Library**, search **Gmail API**, and enable it for this project. Leave unrelated APIs alone. Enabling an API does not connect a mailbox; each mailbox is authorized later.

### 2. Configure the consent screen

Open **Google Auth Platform → Branding** (older interfaces call this **OAuth consent screen**). If prompted, select **Get started**. Enter your app name, your support email, and your developer contact email. Choose **External** to connect your own personal Gmail and accounts from multiple companies. **Internal** only suits accounts within one eligible Workspace organization.

Use your own app homepage and privacy notice if required. Adapt [this template](docs/privacy-notice-template.md), publish the completed notice at a stable public URL you control, and enter that URL in Branding. A public documentation page must contain no credentials or mailbox details. If Google requires domain ownership verification, use a domain you control and follow its verification flow; do not claim ownership of `github.com` or copy the maintainer's branding. Save the configuration. [Google consent-screen instructions](https://developers.google.com/workspace/guides/configure-oauth-consent).

### 3. Request exactly the Gmail permissions used here

In **Google Auth Platform → Data Access → Add or remove scopes**, add the following full scope URLs, save, and confirm no unrelated scope was selected:

| Scope | Used for |
| --- | --- |
| `https://www.googleapis.com/auth/gmail.modify` | Reading, searching, sending, organizing, attachments, Trash, and restore |
| `https://www.googleapis.com/auth/gmail.settings.basic` | Saved Gmail filters and basic settings access |

Do not add Drive, Calendar, Contacts, `gmail.settings.sharing`, or `https://mail.google.com/`. The backend also restricts which API operations can be called. These permissions do not mean every Gmail setting has an implemented command. [Google's Gmail scope definitions](https://developers.google.com/workspace/gmail/api/auth/scopes).

### 4. Set durable publishing status

Under **Audience**, change publishing status from **Testing** to **In production** using **Publish app** and its confirmation. Do this before connecting accounts. For this External app's Gmail scopes, Testing grants normally expire after seven days. If you already connected in Testing, publish first and reconnect the affected accounts. [Google refresh-token expiration rules](https://developers.google.com/identity/protocols/oauth2#expiration).

**In production is a Google OAuth status, not publication of your code, tokens, or email.** It is also not Google verification. Google's personal-use exception can allow an unverified app with fewer than 100 users; an unverified warning and user cap may remain. This guide is for each person operating their own installation, not distributing one shared OAuth client as a public service. [Google's verification exceptions](https://support.google.com/cloud/answer/13464323).

An External production app is not restricted to you by a Testing test-user list. Keeping control depends on your Google account, project permissions, device security, and private grants—not a secret client ID. The project/client ID identifies an app; it is not a mailbox token. Only connect intended mailboxes and do not distribute your client configuration.

### 5. Create and import the desktop client

Open **Google Auth Platform → Clients → Create client**, select **Desktop app**, and name it **My Email Agent Desktop**. Create it and download the JSON. Use the Desktop type, not Web application, API key, or service account. There is no public callback server or authorized-JavaScript-origin configuration for this client; the code handles a loopback callback. [Google credential creation](https://developers.google.com/workspace/guides/create-credentials), [desktop OAuth flow](https://developers.google.com/identity/protocols/oauth2/native-app).

Keep the JSON outside the checkout, restrict its permissions, and import it. Replace the example path with the actual downloaded file path:

```bash
chmod 600 /private/path/client_secret_download.json
python3 scripts/auth.py client /private/path/client_secret_download.json
```

Expected result: `{"client":"default","stored":"macOS Keychain"}`. Approve any legitimate macOS Keychain prompt in your desktop session. The importer validates Google endpoints and stores the client under this plugin's Keychain service. After successful import, remove the downloaded copy and any duplicates if you do not need a separate secure backup. Never commit it, paste it into chat, or attach it to a GitHub issue. Avoid shell tracing (`set -x`) and recording the credential-import session.

## Account purposes

Create `~/.config/email-agent/accounts.json` with only intended identities. The following copies the fictional example only when no configuration already exists:

```bash
umask 077
mkdir -p "$HOME/.config/email-agent"
chmod 700 "$HOME/.config/email-agent"
if [ ! -e "$HOME/.config/email-agent/accounts.json" ]; then
  cp examples/accounts.example.json "$HOME/.config/email-agent/accounts.json"
fi
chmod 600 "$HOME/.config/email-agent/accounts.json"
nano "$HOME/.config/email-agent/accounts.json"
```

Replace every `.example` address with an actual Google mailbox you control. Delete accounts and aliases you do not use. Keep addresses and purpose notes in this private copy, never the tracked example. Choose a different ID for each company. A minimal two-account configuration is:

```json
{"accounts":[
  {"id":"acme","email":"you@your-company.com","purpose":"Acme company operations and clients only; other companies use their own account","avoid":"Personal correspondence"},
  {"id":"personal","email":"you@gmail.com","purpose":"Friends, family, shopping, personal appointments","avoid":"Company business"}
]}
```

`EMAIL_AGENT_HOME` can choose a different metadata/ledger directory for direct CLI use. It does not create a separate Keychain namespace; the remote helper always uses the destination's default configuration path. Keep the default for the documented two-Mac setup. The default named OAuth client is `default`; a separate client may be selected in each account's `client` field. Notes are at most 500 characters. Check syntax and the selected identities locally:

```bash
python3 scripts/email_agent.py accounts
```

This command does not contact Google. Multiple accounts can use your one dedicated desktop client, but each account needs its own consent. For separate company-owned projects, import each client with `auth.py client FILE --name acme-client` and set `"client":"acme-client"` on its account entry. Never replace a working `default` client just to add another company.

## Connect and verify

```bash
python3 scripts/auth.py connect acme
python3 scripts/auth.py connect personal
```

Run one connection at a time. Keep the terminal running and open its printed URL in a normal browser **on that same Mac**, using the intended Chrome/browser profile. The URL suggests the account but does not force it: verify the exact address Google shows before consent. Grant both Gmail permissions. The callback listens only on `127.0.0.1` on a random port and expires after 15 minutes. Passwords, passkeys, MFA, or Workspace restrictions may require the account owner. Do not send the callback URL or authorization code to anyone.

A dedicated client may show Google's unverified-app warning under the personal-use exception. Proceed through **Advanced → Go to [your app]** only when it is your own app/client and the requested permissions match the table. An administrator block is different and requires that organization's permission. The browser saying “Authorization received” means return to the terminal; wait for `authenticated: true` and `refresh_verified: true` before calling the connection complete.

Connection checks the exact scopes, verifies the Gmail profile, stores the refresh token in Keychain, and verifies a real token refresh. No email is sent. Confirm afterward:

```bash
python3 scripts/email_agent.py doctor acme
python3 scripts/email_agent.py doctor personal
python3 scripts/email_agent.py search acme 'in:inbox' --limit 1
python3 scripts/email_agent.py search personal 'in:inbox' --limit 1
```

Then read one returned reference from each account to validate message parsing. Access refresh happens automatically during normal commands. If Google revokes a grant or applies an expiry policy, reconnect only the affected account. No periodic consent is intentionally required by this client. [Google's refresh-token expiration rules](https://developers.google.com/identity/protocols/oauth2#expiration).

## Upgrade existing Gmail connections

Reconnect each account once with `python3 scripts/auth.py connect ACCOUNT` to add Gmail settings. New grants request `gmail.modify` and `gmail.settings.basic`; old read/send or modify-only grants remain usable for their existing capabilities until upgraded. `doctor ACCOUNT` reports refreshed scopes, `cleanup: true`, and `settings: true`. To keep an authorized second Mac identical, transfer the updated Email Agent grants with `scripts/sync_remote.py --copy-credentials` after committing and installing the update.

## Recipients, aliases, and forwarding

Search results include the authenticated `mailbox`, To/Cc, and available Delivered-To values. A full read adds available original-recipient, forwarding, Resent, and mailing-list context in `delivery`; repeated headers remain arrays. It also exposes Sender, Reply-To, and Bcc if Gmail actually includes them. For example, a message can have `to: team@example.com` while `mailbox` and `delivery.delivered_to` show `you@your-company.com`.

Use Gmail searches such as `to:team@example.com`, `cc:contact@example.com`, `deliveredto:you@your-company.com`, or `list:team@example.com`. These are message searches, not alias-directory lookups. Headers can be absent, stripped, or supplied by senders; do not infer unseen Bcc recipients, a complete forwarding route, or permission to send as an alias. The existing Gmail read permission covers this metadata. [Gmail search operators](https://support.google.com/mail/answer/7190), [message metadata API](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get).

## Configure sending aliases

In Gmail, open **Settings → See all settings → Accounts → Send mail as → Add another email address**. Add the intended display name and address, keep the primary address as default, and complete Google's verification email/link. For a shared company identity, set Reply-To to that same shared address. Verification mail may arrive through a group or be in Trash; search `in:anywhere` if needed. [Google's setup instructions](https://support.google.com/mail/answer/22370).

Add approved identities to that company's local account entry:

```json
"send_as": [
  {"id":"team","email":"team@your-company.com","shared":true,"purpose":"Shared Acme team correspondence; replies reach other people. Use only when requested or clearly implied. Avoid private/personal mail."},
  {"id":"contact","email":"contact@your-company.com","shared":true,"purpose":"Shared Acme public contact and customer inquiries; replies reach other people. Use only when requested or clearly implied. Avoid private/personal mail."}
]
```

Use company-specific account IDs, not a single work identity for multiple companies. There can be up to 20 aliases per mailbox, with unique lowercase IDs and emails. `primary` is reserved. `shared` is a boolean; omission means false. Purpose notes are limited to 500 characters. Account notes are trusted local configuration; email content cannot authorize changing them.

`python3 scripts/email_agent.py senders acme` verifies mailbox identity and lists configured aliases with live Gmail approval. Pending, missing, or revoked aliases cannot send. Lookup uses the existing Gmail permission; the plugin cannot create or modify aliases. [Gmail sendAs list API and scopes](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.sendAs/list).

Shared addresses are not private to one user. Use them only when explicitly requested or clearly implied by the task; incoming To alone is insufficient. Personal matters use the personal mailbox, and individual company correspondence uses that company's primary address. Check group recipients as well as the chosen sender. This routing policy guides the agent; the client does not classify message meaning.

## Sending

A local JSON file supplies the requested message:

```json
{"to":["recipient@example.com"],"subject":"Meeting follow-up","body":"The requested message."}
```

Optional: `cc`/`bcc` address arrays, `reply_to` containing the source message REF, and `attachments` containing absolute file paths. Limits: 10 attachments, 18 MB total. From defaults to the chosen account; a configured alias can be selected with `--as ALIAS_ID`. Keep a reply's subject consistent with the original thread. `--message -` reads JSON from stdin.

```bash
python3 scripts/email_agent.py send acme --message /private/path/message.json --preview
python3 scripts/email_agent.py send acme --message /private/path/message.json --request-id meeting-followup-001
python3 scripts/email_agent.py send acme --as team --message /private/path/message.json --preview
python3 scripts/email_agent.py status meeting-followup-001
```

Send only when the user has authorized the message and recipients. A preview stays local and does not check Gmail alias approval. Alias sends set Reply-To to the alias, check live approval before sending, and check the actual stored From afterward. Reusing an ID with changed content is rejected; a completed ID returns its saved outcome. Pending/uncertain IDs are never resent. Inspect Sent mail before choosing a new ID. After fixing a `not_sent` failure, use a new ID only for the still-authorized message.

## Cleanup

```bash
python3 scripts/email_agent.py search personal 'category:promotions older_than:90d -is:starred -is:important' --limit 10
python3 scripts/email_agent.py trash personal 'SELECTED_REF' --preview
python3 scripts/email_agent.py trash personal 'SELECTED_REF'
python3 scripts/email_agent.py restore personal 'SELECTED_REF'
```

A query selects candidates, not authorization to discard every result. Inspect messages and use explicit refs within the user's requested scope. A batch accepts 1–25 unique refs from one account and preflights all selected messages. Drafts are blocked. Preview is local and does not check permission. Each actual result is verified; a partial result lists completed, unchanged, uncertain, and unattempted messages. Inspect uncertain results before continuing. The plugin cannot empty Trash or permanently delete mail. Gmail normally removes Trash after 30 days.

## Organization, downloads, and saved rules

Read the [mailbox command reference](skills/email-agent/references/mailbox.md) for organization, label creation, attachment downloads, full Gmail query syntax, and saved filters. Actual label/filter creation uses a stable `--request-id`; previews stay local. Use `operation-status ID` for these creation results. A filter changes future matching mail, so inspect its criteria and keep company-specific account routing. No organization or saved rules are installed automatically during account connection.

## Codex installation

First register the checkout in your personal marketplace. This workflow requires Codex's bundled **plugin-creator** skill at `~/.codex/skills/.system/plugin-creator`. Confirm the helper exists:

```bash
test -f "$HOME/.codex/skills/.system/plugin-creator/scripts/create_basic_plugin.py"
```

If missing, use a Codex installation that includes that system skill; do not download a random replacement installer or improvise a marketplace schema. The mail CLI can still be verified before plugin registration.

For a fresh marketplace entry, run the supported scaffold helper into a temporary directory. It creates the marketplace entry without overwriting the real cloned manifest. The marketplace resolves Email Agent at `~/plugins/email-agent`, where the earlier clone step placed it.

```bash
EMAIL_AGENT_STAGE=$(mktemp -d)
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/create_basic_plugin.py" \
  email-agent --path "$EMAIL_AGENT_STAGE" --with-marketplace
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/read_marketplace_name.py"
```

Do not run the scaffolder over your checkout or use `--force` to suppress an existing-entry conflict. If it says the entry already exists, inspect `codex plugin list --marketplace personal --json` and `~/.agents/plugins/marketplace.json`; reuse it only if it points at this checkout. The temporary scaffold contains no secrets and can be removed after registration.

For the default marketplace name `personal` returned above:

```bash
python3 scripts/install.py
codex plugin list --marketplace personal --json
```

The installer enables hourly GitHub updates by default on first installation. Use `python3 scripts/install.py --no-auto-update` to opt out; reinstalls preserve a saved opt-out. It trusts future code published to the configured upstream. For a fork, pass `--repository OWNER/REPO`.

If your marketplace already has another name, install with `codex plugin add email-agent@YOUR_MARKETPLACE` and use that name in the list command; the default updater supports only `personal`. The remote installer currently requires `personal`; do not rename an existing marketplace just to fit it. The default `~/.agents/plugins/marketplace.json` is discovered implicitly; it does not need `codex plugin marketplace add`.

Verify the installed entry has `enabled: true`, the version from `.codex-plugin/plugin.json`, and the expected source path. Credentials and notes remain outside the plugin cache. Start a **new Codex task** and say:

> Use Email Agent to list my configured account purposes, then verify my personal account. Do not send or change mail.

The skill loads when relevant and uses the same local configuration across tasks. Do not add a separate broad Google connector or paste credentials into a task. A task may still request tool access according to your Codex settings.

## Verify your complete setup

For each real account ID, run these read-only checks; substitute your IDs for `acme` and `personal`:

```bash
python3 scripts/email_agent.py doctor acme
python3 scripts/email_agent.py doctor personal
python3 scripts/email_agent.py senders acme
python3 scripts/email_agent.py labels acme --limit 1
python3 scripts/email_agent.py filters acme --limit 1
python3 scripts/email_agent.py search acme 'in:inbox' --limit 1
```

Confirm each `doctor` identity matches your configuration and reports `cleanup: true` and `settings: true`. An empty labels/filter/search result is not an authentication failure. Read a returned message ref to prove body parsing; empty mailboxes have nothing to read. These commands display private metadata/content locally, so do not post their complete output publicly.

To test actual sending, deliberately send **one** clearly labeled message between two mailboxes you own. Use a unique subject and a stable request ID of 8–100 letters, digits, underscores, or hyphens. For example, create an owner-only `~/.config/email-agent/setup-message.json` containing:

```json
{"to":["YOUR_OTHER_ACTUAL_EMAIL"],"subject":"Email Agent setup check 2026-09-16-01","body":"One delivery check between my own accounts."}
```

Replace the recipient and choose a subject/ID unique to your test. Then:

```bash
python3 scripts/email_agent.py send acme --message "$HOME/.config/email-agent/setup-message.json" --preview
python3 scripts/email_agent.py send acme --message "$HOME/.config/email-agent/setup-message.json" --request-id setup-check-20260916-01
python3 scripts/email_agent.py status setup-check-20260916-01
python3 scripts/email_agent.py search personal 'in:anywhere subject:"Email Agent setup check 2026-09-16-01"' --limit 5
```

The second command actually sends. Inspect the recipient-side message: expected From, To, body, and available Delivered-To; confirm there is one matching message. Delivery can take a moment. If the send result is pending/uncertain, inspect Sent and the receiving mailbox before any new send. Do not generate a new request ID simply to retry an ambiguous result.

Optional feature checks use only that setup message: read it, add STARRED and remove it afterward, or Trash and restore it. For attachments, download one known attachment to a new private path and check the reported size/hash. Use the [mailbox reference](skills/email-agent/references/mailbox.md) for exact commands and inverse changes. Filter creation is a separate deliberate action affecting future mail; a successful `filters` read proves settings access without creating a rule. Setup does not install background jobs or automatically organize your inbox.

Your installation is ready when:

- Every intended mailbox passes identity and refresh checks with both Gmail permissions.
- Purpose notes distinguish companies/personal/secondary accounts, and shared aliases are marked and Gmail-approved.
- Search and a message read succeed where mail exists; labels and filters can be listed.
- The optional delivery check arrives once with the intended sender.
- Codex reports the plugin enabled and a new task can use it.
- If using two Macs, repeat the installed-plugin check on the second Mac; a local success alone does not prove remote setup.

## Another Mac and later updates

For automatic updates from GitHub, follow [automatic-update setup](docs/auto-updates.md) after the initial installation on each Mac. The manual development/deployment workflow below remains available.

The destination must be your own intended Mac/user, with Python 3.9+, Codex CLI, the bundled plugin-creator helper, and an accessible login Keychain. Log into its graphical desktop; a headless SSH session alone is insufficient for the session helper. Set up macOS Remote Login for the intended user and SSH key authentication. Keep SSH on a trusted network or your own secure network connection.

On the destination, obtain the exact values:

```bash
/usr/sbin/scutil --get ComputerName
python3 -c 'from pathlib import Path; print(Path.home())'
python3 --version
codex plugin --help
```

On the source, establish and verify the SSH host key through a trusted channel. Do not disable host-key checking. An SSH alias in `~/.ssh/config` can specify the destination hostname, username, and your existing SSH identity file. The helper uses batch mode, so interactive password login is not enough. Check from the source:

```bash
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes YOUR_SSH_ALIAS /usr/sbin/scutil --get ComputerName
```

Do not clone this repository into `~/plugins/email-agent` on the destination when using managed sync: the helper owns that path and refuses to replace an unrelated checkout. Preserve/reconcile any existing installation first. It also refuses conflicting remote account notes. Initial setup, using the exact values verified above:

```bash
python3 scripts/sync_remote.py --host YOUR_SSH_ALIAS --computer-name 'Your Remote Mac' --remote-home /Users/YOUR_USER --copy-credentials
```

This explicitly copies the configured Gmail client and refresh grants over encrypted, host-verified SSH. Secrets travel through subprocess stdin and memory directly into the destination Keychain, never command arguments, source files, temporary credential files, or output. Only records derived from the configured accounts are read; unrelated Keychain entries are excluded. Both Macs use the same Google grants, so revoking a shared grant affects both copies. On macOS, a one-time process runs in the logged-in desktop session so Keychain access does not depend on SSH session permissions. A private mode-600 Unix socket carries the in-memory payload; temporary files contain public receiver code and launch metadata only. The process is removed when deployment finishes.

The helper copies committed regular source files into a versioned release under `~/.local/share/email-agent/releases`, points `~/plugins/email-agent` at it, and registers/enables it through Codex's personal marketplace commands. Account notes remain in mode-600 local configuration. A successful initial deployment saves only the SSH target's identity in local `~/.config/email-agent/remote.json`.

After reviewing and committing later changes, update both installations:

```bash
git status --short
git pull --ff-only
codex plugin add email-agent@personal
python3 scripts/sync_remote.py
```

These update commands are for a source checkout following its reviewed upstream; if `git status` shows changes, preserve/reconcile them before pulling. When maintaining your own fork, follow its review process. For your own source edits, first run the tests and Codex validators, use the plugin-creator `update_plugin_cachebuster.py` helper on the checkout, commit the reviewed changes, and reinstall. Upstream releases already carry a version; do not change it merely to install a published update. Never edit the installed cache as the source of truth.

Initial remote deployment enables hourly GitHub updates by default. Pass `--no-auto-update` to `sync_remote.py` to opt out; later deployments preserve an existing opt-out. Normal updates reuse the remote credentials, copy current notes and code, and verify every mailbox through a fresh process. Use `--copy-credentials` again only when authorized to transfer newly connected or replaced Gmail grants. Local source must be clean and committed; remote source/notes edited outside deployment must be reconciled first. Releases are retained for recovery. A failure preserves completed steps, reports its phase without secret output, and can be retried with the same command. Success requires `status: ready`, `enabled: true`, the intended version/revision, and the per-account verification results. Current sync supports one saved destination and always uses the destination's default config directory.

The source machine's compact send history is merged without replacing remote outcomes. This is a snapshot, not a continuously shared ledger: investigate pending/uncertain sends on the original machine, and do not move an unresolved send to the other Mac as a retry. No email sync loop is installed. Code updates can run hourly by default after standard installation on each Mac; see [GitHub auto-updates](docs/auto-updates.md) for opt-out and recovery.

The plugin is enabled at user level on each Mac. Start a new Codex task after installation to load its skill; existing tasks created before installation may need a new task. Ordinary prompts such as “Use Email Agent to check my company mail” can select the skill. Mailbox notes load from local configuration when needed.

## Troubleshooting

| Symptom | Check and recovery |
| --- | --- |
| Clone says `Repository not found` | Verify the URL, GitHub sign-in, and repository access. Use your accessible fork if applicable. |
| `codex` missing or no `plugin` subcommand | Install/update the supported Codex CLI and ensure the terminal can find it. Verify the bundled plugin-creator helper separately. |
| Marketplace entry already exists | Inspect its source and name; reuse a matching entry. Do not force-overwrite unrelated plugins or your checkout. |
| New task cannot find Email Agent | Check enabled state/version/source with `codex plugin list`; reinstall from the intended marketplace and start a new task. |
| JSON/account validation fails | Edit the private `accounts.json`, replace sample addresses, remove trailing commas, and ensure IDs/emails are unique. Run `accounts` before OAuth. |
| Wrong Google mailbox selected | Start `auth.py connect ACCOUNT` again and use that mailbox's browser profile. A mismatched Gmail identity is rejected before saving its grant. |
| Google says access blocked / admin approval needed | Check the selected project, audience, and Workspace policy. In Testing, add the exact test user if testing intentionally. An organization block needs its administrator; do not evade it with another identity. |
| Callback fails or times out | Keep the command alive, use the browser on the same Mac, and restart the connection for a fresh URL. Old callback URLs cannot complete a new attempt. |
| JSON importer rejects client | Download a **Desktop app** client from your project; do not use a Web client, service-account file, or OAuth file from another tool. |
| Keychain locked / user interaction unavailable | Unlock the intended login Keychain in that Mac's desktop session and handle its prompt. For remote sync, ensure that user has a logged-in GUI session. Never put a Keychain password in a command. |
| Reconnect required about every seven days | Verify the project's Audience is **In production**, then reconnect grants issued during Testing. Publishing alone does not renew old grants. |
| Gmail permissions missing | Reconnect the affected account with the dedicated client and select both Gmail permissions. Verify `doctor` afterward. |
| Google revoked access / refresh fails | Check Google Account connections and organization policy; reconnect only the affected account. Frequent reconnects/client churn are not a substitute for diagnosis. |
| Alias not sendable | Complete Gmail's Send mail as verification for the exact address, then check `senders ACCOUNT`. Receiving group mail alone does not authorize sending as that group. |
| Search finds nothing | Check account and query; use `in:anywhere` to include Spam/Trash when appropriate. An empty result is not proof that mail never arrived. |
| Send/creation outcome uncertain | Use `status ID` or `operation-status ID`, inspect Gmail, and investigate on the originating Mac before retrying. |
| Remote host/account mismatch | Recheck the pinned host key, SSH alias, exact ComputerName and `/Users/...` home. The helper checks identity before transferring credentials. |
| Remote fails during `desktop_session` / `keychain_storage` | Check GUI login and Keychain access on that destination. Retry after fixing it; do not export secrets into temporary files as a workaround. |
| Remote fails during `source_install` / `account_validation` | Reconcile an unmanaged checkout or independently edited source/notes. Do not delete conflicting data to make deployment pass. |
| Remote fails during `marketplace_install` / `installed_verification` | Check the destination helper, CLI, `personal` marketplace, plugin source/version, and connectivity. A partial install is not verified success. |

For support, report the command name, plugin version, macOS/Python version, and sanitized fixed error/phase. Never upload downloaded OAuth JSON, Keychain contents, authorization/callback URLs, refresh tokens, account files, private email, or unredacted command output. See [disconnecting and removing local data](docs/security.md#disconnect-or-remove-an-installation).
