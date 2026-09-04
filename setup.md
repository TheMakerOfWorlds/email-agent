# Setup

Requires Python 3.9+ on macOS. No Python package installation is needed. Use a dedicated Google Cloud project and OAuth client for Email Agent so permission grants remain isolated from other Google tools.

## Google project and desktop client

1. Sign into Google Cloud with the intended owner account. Create a dedicated project named Email Agent. Do not attach billing or enable unrelated services.
2. Enable **Gmail API** only.
3. Configure Google Auth Platform branding as **Email Agent**, with your support/contact email. Use **External** audience because both a personal Gmail and a Workspace account will connect. Complete any homepage, privacy-policy, and authorized-domain fields Google requires before publishing. This installation uses the owner's [public app information and privacy notice](https://gist.github.com/TheMakerOfWorlds/0ea2b4aa332d760f4a08269a8d146196); its source is [docs/public-information.md](docs/public-information.md). The notice contains no mailbox data or credentials. A different owner should publish their own accurate notice and use their own contact information.
4. Add only `gmail.readonly` and `gmail.send` on the Data Access page.
5. Set the publishing status to **In production** before issuing durable refresh tokens. External apps left in Testing normally receive seven-day refresh tokens. Publishing status and Google's verification process are separate; [personal-use apps with fewer than 100 users may be exempt from verification](https://support.google.com/cloud/answer/13464323).
6. Create an OAuth client of type **Desktop app**, named **Email Agent Desktop**. Download its JSON into a private location outside this repository, with file mode 600.
7. Import the downloaded file into Keychain:

```bash
python3 scripts/auth.py client /private/path/client_secret_download.json
```

The importer validates Google endpoints and stores the client in macOS Keychain. After successful import, remove the downloaded copy if you do not need a separate secure backup. Never commit it or paste the secret into chat. Setup intentionally does not reuse broad credentials from other apps.

## Account purposes

Create `~/.config/email-agent/accounts.json` with only intended identities. Use directory mode 700 and file mode 600. Example:

```json
{"accounts":[
  {"id":"acme","email":"you@your-company.com","purpose":"Acme company operations and clients only; other companies use their own account","avoid":"Personal correspondence"},
  {"id":"personal","email":"you@gmail.com","purpose":"Friends, family, shopping, personal appointments","avoid":"Company business"}
]}
```

`EMAIL_AGENT_HOME` can choose a different metadata/ledger directory. The default named OAuth client is `default`; a separate client may be selected in each account's `client` field. Notes are at most 500 characters. Fictional examples must not be mistaken for real authentication.

## Connect and verify

```bash
python3 scripts/auth.py connect acme
python3 scripts/auth.py connect personal
```

Open the URL printed by each command in a normal browser. Select the exact intended account and grant the two Gmail permissions. The callback listens only on `127.0.0.1` on a random port and expires after 15 minutes. Passwords, passkeys, MFA, or Workspace restrictions may require the account owner. A dedicated client may show Google's unverified-app warning under the personal-use exception.

Connection checks the exact scopes, verifies the Gmail profile, stores the refresh token in Keychain, and verifies a real token refresh. No email is sent. Confirm afterward:

```bash
python3 scripts/email_agent.py doctor acme
python3 scripts/email_agent.py doctor personal
python3 scripts/email_agent.py search acme 'in:inbox' --limit 1
python3 scripts/email_agent.py search personal 'in:inbox' --limit 1
```

Then read one returned reference from each account to validate message parsing. Access refresh happens automatically during normal commands. If Google revokes a grant or applies an expiry policy, reconnect only the affected account. No periodic consent is intentionally required by this client. [Google's refresh-token expiration rules](https://developers.google.com/identity/protocols/oauth2#expiration).

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

`python3 scripts/email_agent.py senders acme` verifies mailbox identity and lists configured aliases with live Gmail approval. Pending, missing, or revoked aliases cannot send. Lookup requires only the existing `gmail.readonly` permission; the plugin cannot create or modify aliases. [Gmail sendAs list API and scopes](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.sendAs/list).

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

## Codex installation

When listed in your personal marketplace, install with `codex plugin add email-agent@personal`. Start a new Codex task after installation or an update so its skill is discovered. Credentials and account notes remain outside the plugin cache.


## Another Mac and later updates

The destination must be the user's intended Mac with a known SSH host key, Python 3.9+, Codex CLI, the bundled plugin-creator helper, and an accessible login Keychain. Confirm the exact computer name and remote account home first. Initial setup:

```bash
python3 scripts/sync_remote.py --host YOUR_SSH_ALIAS --computer-name 'Your Remote Mac' --remote-home /Users/YOUR_USER --copy-credentials
```

This explicitly copies the configured Gmail client and refresh grants over encrypted, host-verified SSH. Secrets travel through subprocess stdin and memory directly into the destination Keychain, never command arguments, source files, temporary credential files, or output. Only records derived from the configured accounts are read; unrelated Keychain entries are excluded. Both Macs use the same Google grants, so revoking a shared grant affects both copies.

The helper copies committed regular source files into a versioned release under `~/.local/share/email-agent/releases`, points `~/plugins/email-agent` at it, and registers/enables it through Codex's personal marketplace commands. Account notes remain in mode-600 local configuration. A successful initial deployment saves only the SSH target's identity in local `~/.config/email-agent/remote.json`.

After reviewing and committing later changes, update both installations:

```bash
codex plugin add email-agent@personal
python3 scripts/sync_remote.py
```

Normal updates reuse the remote credentials, copy current notes and code, and verify every mailbox through a fresh process. Use `--copy-credentials` again only when authorized to transfer newly connected or replaced Gmail grants. Local source must be clean and committed; remote source/notes edited outside deployment must be reconciled first. Releases are retained for recovery. A failure preserves completed steps, reports its phase without secret output, and can be retried with the same command.

The source machine's compact send history is merged without replacing remote outcomes. This is a snapshot, not a continuously shared ledger: investigate pending/uncertain sends on the original machine, and do not move an unresolved send to the other Mac as a retry. No background timer or email sync loop is installed.

The plugin is enabled at user level on each Mac. Start a new Codex task after installation to load its skill; existing tasks created before installation may need a new task. Ordinary prompts such as “Use Email Agent to check my company mail” can select the skill. Mailbox notes load from local configuration when needed.
