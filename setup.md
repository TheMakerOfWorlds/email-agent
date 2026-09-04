# Setup

Requires Python 3.10+ on macOS. No Python package installation is needed. Use a dedicated Google Cloud project and OAuth client for Email Agent so permission grants remain isolated from other Google tools.

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
  {"id":"work","email":"you@your-company.com","purpose":"Company operations and clients","avoid":"Personal correspondence"},
  {"id":"personal","email":"you@gmail.com","purpose":"Friends, family, shopping, personal appointments","avoid":"Company business"}
]}
```

`EMAIL_AGENT_HOME` can choose a different metadata/ledger directory. The default named OAuth client is `default`; a separate client may be selected in each account's `client` field. Notes are at most 500 characters. Fictional examples must not be mistaken for real authentication.

## Connect and verify

```bash
python3 scripts/auth.py connect work
python3 scripts/auth.py connect personal
```

Open the URL printed by each command in a normal browser. Select the exact intended account and grant the two Gmail permissions. The callback listens only on `127.0.0.1` on a random port and expires after 15 minutes. Passwords, passkeys, MFA, or Workspace restrictions may require the account owner. A dedicated client may show Google's unverified-app warning under the personal-use exception.

Connection checks the exact scopes, verifies the Gmail profile, stores the refresh token in Keychain, and verifies a real token refresh. No email is sent. Confirm afterward:

```bash
python3 scripts/email_agent.py doctor work
python3 scripts/email_agent.py doctor personal
python3 scripts/email_agent.py search work 'in:inbox' --limit 1
python3 scripts/email_agent.py search personal 'in:inbox' --limit 1
```

Then read one returned reference from each account to validate message parsing. Access refresh happens automatically during normal commands. If Google revokes a grant or applies an expiry policy, reconnect only the affected account. No periodic consent is intentionally required by this client. [Google's refresh-token expiration rules](https://developers.google.com/identity/protocols/oauth2#expiration).

## Recipients, aliases, and forwarding

Search results include the authenticated `mailbox`, To/Cc, and available Delivered-To values. A full read adds available original-recipient, forwarding, Resent, and mailing-list context in `delivery`; repeated headers remain arrays. It also exposes Sender, Reply-To, and Bcc if Gmail actually includes them. For example, a message can have `to: team@example.com` while `mailbox` and `delivery.delivered_to` show `you@your-company.com`.

Use Gmail searches such as `to:team@example.com`, `cc:contact@example.com`, `deliveredto:you@your-company.com`, or `list:team@example.com`. These are message searches, not alias-directory lookups. Headers can be absent, stripped, or supplied by senders; do not infer unseen Bcc recipients, a complete forwarding route, or permission to send as an alias. The existing Gmail read permission covers this metadata. [Gmail search operators](https://support.google.com/mail/answer/7190), [message metadata API](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get).

## Sending

A local JSON file supplies the requested message:

```json
{"to":["recipient@example.com"],"subject":"Meeting follow-up","body":"The requested message."}
```

Optional: `cc`/`bcc` address arrays, `reply_to` containing the source message REF, and `attachments` containing absolute file paths. Limits: 10 attachments, 18 MB total. From is fixed by the chosen account. Keep a reply's subject consistent with the original thread. `--message -` reads JSON from stdin.

```bash
python3 scripts/email_agent.py send work --message /private/path/message.json --preview
python3 scripts/email_agent.py send work --message /private/path/message.json --request-id meeting-followup-001
python3 scripts/email_agent.py status meeting-followup-001
```

Send only when the user has authorized the message and recipients. A preview stays local. Reusing an ID with changed content is rejected; a completed ID returns its saved outcome. Pending/uncertain IDs are never resent. Inspect Sent mail before choosing a new ID. After fixing a `not_sent` failure, use a new ID only for the still-authorized message.

## Codex installation

When listed in your personal marketplace, install with `codex plugin add email-agent@personal`. Start a new Codex task after installation or an update so its skill is discovered. Credentials and account notes remain outside the plugin cache.
