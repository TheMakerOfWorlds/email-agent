# Optional Google Workspace services

Email Agent now also provides Calendar, Meet, Drive, Docs, Sheets, and Contacts commands. Each is loaded only when used. Existing Gmail credentials and commands stay independent. Adding code does **not** grant Google access: each intended account must authorize the Workspace client separately.

Start with the [base installation](../setup.md). Reuse the private `accounts.json` and company-specific purpose notes. Do not create one generic “work” account for multiple companies. The plugin retains its `email-agent` repository/package name for installation compatibility.

## Navigation and implemented capabilities

```text
accounts → select company / personal / secondary identity
    ├── Gmail       search → selected message → reply / organize / filters
    ├── Calendar    list calendars → select calendar → availability / events / scheduling
    ├── Meet        create a link, or read accessible meeting records / artifacts
    ├── Drive       search metadata → selected file/folder → download / upload / organize
    ├── Docs        selected document → selected tab → bounded text / targeted edit
    ├── Sheets      selected spreadsheet → selected tab/range → read / write / format
    └── Contacts    search within account → select person → read / create / update
```

| Service | Commands | Agent reference |
| --- | --- | --- |
| Calendar | List calendars/events, availability, get, create, update, cancel; optional unique Meet conference and explicit guest notifications | [Calendar](../skills/email-agent/references/calendar.md) |
| Meet | Create/open/get spaces; list conference records, participants, recordings, transcripts, transcript entries | [Meet](../skills/email-agent/references/meet.md) |
| Drive | Search/open/get files, download/export, upload, folder creation, rename/description, move, Trash/restore | [Drive](../skills/email-agent/references/drive.md) |
| Docs | Open/get text and tab/index metadata, create, append, replace text within a tab, format selected text with a revision check | [Docs](../skills/email-agent/references/docs.md) |
| Sheets | Open/get metadata, read bounded ranges, create, write/append/clear cells, format ranges, add tabs | [Sheets](../skills/email-agent/references/sheets.md) |
| Contacts | List/search/get saved contacts, create, update selected fields, delete a selected contact | [Contacts](../skills/email-agent/references/contacts.md) |

This is a focused command surface, not every method in every Google API. No administrative directory changes, file sharing/ownership changes, permanent Drive deletion, live Meet participation/recording, or new background monitoring is implemented. Meet artifacts must already exist and be accessible; Google account features and policies still apply.

## 1. Enable APIs in your own project

Select the dedicated Google Cloud project from the base setup. Enable only the APIs for the services you intend to use, through **APIs & Services → Library**:

- Google Calendar API (`calendar-json.googleapis.com`)
- Google Meet API (`meet.googleapis.com`)
- Google Drive API (`drive.googleapis.com`)
- Google Docs API (`docs.googleapis.com`)
- Google Sheets API (`sheets.googleapis.com`)
- People API (`people.googleapis.com`)

Gmail API remains enabled for mail. Do not enable Cloud administration, billing, domain-wide delegation, or service-account access for this plugin. API enablement is separate from per-account OAuth permission. Existing Codex/Google subscription costs and service quotas still apply; no additional email/Workspace relay is required.

## 2. Choose permissions deliberately

In **Google Auth Platform → Data Access**, declare the selected scopes below. Keep the audience and production-status guidance from [base setup](../setup.md#google-project-and-desktop-client). Update your app's privacy notice to reflect the services you actually enable.

All Workspace grants include `https://www.googleapis.com/auth/userinfo.email` to verify the authenticated account's email; the code requires Google's verified-email result. It does not request a password or use a Gmail alias as identity.

| Service selection | OAuth scope suffix after `https://www.googleapis.com/auth/` |
| --- | --- |
| Calendar | `calendar.events`, `calendar.calendarlist.readonly`, `calendar.events.freebusy` |
| Meet | `meetings.space.created`, `meetings.space.readonly` |
| Contacts | `contacts` |
| Drive | `drive` |
| Docs without Drive | `documents` |
| Sheets without Drive | `spreadsheets` |

When Drive is selected, its scope also authorizes Docs/Sheets operations, so the client omits redundant `documents`/`spreadsheets` scopes. Drive access here is broad enough to search/read/edit accessible existing files. It is **not** the selected-file-only `drive.file` model, which would need a separate picker/selection workflow. Google's Drive grant can authorize more operations than this plugin exposes; code-level restrictions are additional to OAuth scope boundaries. Do not enable Drive for an account if you only want isolated Docs or Sheets access, though those dedicated scopes also cover that account's accessible documents/spreadsheets rather than just one file.

Gmail permissions are absent from this Workspace grant. The existing Gmail client still enforces its own Gmail-only scope allowlist. There is no automatic permission expansion when you install an update.

Official scope references: [Calendar](https://developers.google.com/workspace/calendar/api/auth), [Meet](https://developers.google.com/workspace/meet/api/guides/authenticate-authorize), [Drive](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), [People](https://developers.google.com/people), [Docs](https://developers.google.com/workspace/docs/api/auth), [Sheets](https://developers.google.com/workspace/sheets/api/scopes).

## 3. Create a separate Desktop client

Under **Google Auth Platform → Clients**, create a **Desktop app** named **Email Agent Workspace Desktop**. Keep the existing Gmail desktop client. Import the new private JSON into Keychain under the distinct name `workspace`:

```bash
chmod 600 /private/path/client_secret_workspace.json
python3 scripts/google_auth.py client /private/path/client_secret_workspace.json
```

After import, remove the downloaded copy if you do not need a secure backup. Never commit or paste it. Do not import this client under the Gmail `default` name. Workspace clients use a separate `workspace.client.NAME` Keychain namespace. Import rejects reuse of a configured Gmail client and replacement of a different existing Workspace client under the same name.

By default, all account entries use the named `workspace` client. For separately owned company projects, import with `--name acme-workspace` and add `"workspace_client":"acme-workspace"` to that company's private account entry. `client` still selects the Gmail client. Both client names are local Keychain selectors, not credential values.

## 4. Connect each intended account

Connect all six services for one account:

```bash
python3 scripts/google_auth.py connect acme
```

Or select a smaller set, separately for each account:

```bash
python3 scripts/google_auth.py connect personal --services calendar contacts
python3 scripts/google_auth.py connect secondary --services drive docs sheets
```

Use the exact account IDs from `google_agent.py accounts`. Keep the command running, open its URL in that account's browser profile on the same Mac, verify the displayed Google identity, and complete consent. These commands request the stated services; rerunning with a different list is a deliberate grant replacement, so include all services you want retained for that Workspace connection. Gmail is separate. If Google displays broader/unexpected permissions, stop and inspect the selected client and project rather than accepting them blindly.

The code verifies both the initial identity and a real refresh exchange before saving a new grant. Expected success includes `authenticated:true` and `refresh_verified:true`. Workspace grants use `workspace.token.HASH` records under the same local Keychain service; existing `token.HASH` Gmail records are not replaced. Refresh happens automatically during use; Google can still revoke grants or enforce account policy.

## 5. Verify service access without sending anything

```bash
python3 scripts/google_agent.py accounts
python3 scripts/google_agent.py doctor acme
python3 scripts/google_agent.py calendar acme calendars --limit 1
python3 scripts/google_agent.py drive acme search --limit 1
python3 scripts/google_agent.py contacts acme list --limit 1
python3 scripts/google_agent.py meet acme records --limit 1
```

Run only the service checks you authorized. `doctor` proves identity/refresh and reports scopes; it does not prove every API is enabled. A 403 may mean missing OAuth scope, disabled API, or account/organization restrictions. Empty lists can be valid. Open one intended existing Doc/Sheet by ID or a typed ref returned from Drive to verify its service separately.

Do not create meetings, send invitations, modify contacts, or change existing documents merely to test login. If testing writes, use specifically authorized disposable resources and inspect returned receipts, exact account identity, and resulting state. Google Calendar creation with guests sends invitations only when `notify:all` is explicitly supplied; avoid guests in setup probes. Standalone Meet space creation does not invite anyone.

## 6. Use the commands in Codex

Reinstall the updated `email-agent` plugin from your existing marketplace and start a new task. The skill first loads account purposes, then only the requested service reference. Examples:

- “Using Acme's account, find a free half hour next week.”
- “Schedule this Acme meeting, include a Meet link, and invite these two people.”
- “Find the expense tracker in Other Company's Drive and add this row.”
- “Look up Alex in my personal Google Contacts.”

If the user says only “work” and multiple companies fit, the skill asks. Permission failures do not trigger a fallback to another account. Resource refs encode the selected account/client/type so accidentally mixing refs between accounts is rejected locally. `open` is an explicit way to resolve a user-provided resource ID through the selected account's access.

Read results default to ten items with a maximum of 25; queries/time windows and page cursors avoid broad collection. Docs return at most 4,000 text characters with continuation. Sheets require finite A1 ranges of at most 2,000 cells; oversized output asks for a smaller range rather than emitting a partial matrix. Small provider field selections and per-service instruction loading reduce context use without a separate LLM summarization step.

Writes use `--request-id` and a separate local `google-operations.sqlite3` ledger. Use `google_agent.py status ACCOUNT REQUEST_ID` after an uncertain result. A completed receipt prevents replay with the same ID, and conflicting content/accounts are rejected. Pending/uncertain writes are never blindly retried. A receipt is not a distributed exactly-once guarantee; investigate on the Mac that made the request. `--preview` is local and does not prove permissions or current provider state.

## 7. Optional second Mac

Complete the [base SSH/Mac setup](../setup.md#another-mac-and-later-updates). Source must be clean and committed. A code-only update remains:

```bash
python3 scripts/sync_remote.py
```

After deliberately authorizing Workspace grants on the destination too, use:

```bash
python3 scripts/sync_remote.py --copy-workspace-credentials
```

`--copy-credentials` still refers only to Gmail. Both flags are needed only if deliberately transferring both kinds of grants. The helper selects only configured account records, rejects unrelated keys, validates identities, and stores them in remote Keychain. It does not transfer other Google app credentials or write secret files. Connected Workspace accounts are refreshed and checked through the installed plugin. Accounts without a Workspace grant remain Gmail-only.

The remote workflow prepares source and Keychain state in the desktop session, installs/enables the plugin through SSH's CLI environment, and then verifies cache contents and fresh account access in the desktop session. This avoids relying on the CLI's behavior inside a background desktop job. A failure retains completed steps for retry. Workspace operation receipts are local to each machine and are not merged or continuously synchronized.

## Troubleshooting and removal

- **Workspace not connected:** Gmail may still work. Connect only the intended account/services with the Workspace client.
- **Unexpected Workspace permissions:** Check that you imported the dedicated desktop client; the Workspace allowlist rejects Gmail and unrelated scopes.
- **403:** Check both API enablement and actual scopes from doctor, then the account's policy. Do not switch identities to bypass a restriction.
- **Wrong company/file/calendar:** Stop; choose the correct account and rediscover its resource. Do not rewrite a ref by hand.
- **Pending Meet conference:** Read the Calendar event again; creating another event can duplicate invitations.
- **Contact update conflict / document revision changed:** Read current state and prepare the intended edit again, using a new ID only after resolving the prior receipt.
- **Missing transcripts/recordings:** They must exist and the account must have access; the API does not create historical artifacts.
- **More tabs or text:** Follow `next_tabs_offset`, `next_runs_offset`, or `next_offset` as appropriate, keeping the same account/ref.

To remove Workspace access, revoke your app in Google Account connections and remove the intended `workspace.token.*` records and unused `workspace.client.workspace` record locally. Google app-level revocation may affect other grants issued under that same project; check Gmail afterward. Uninstall alone does not revoke credentials or undo cloud edits. See [storage and privacy](security.md).
