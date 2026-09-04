# Email Agent

An independent, MIT-licensed Gmail plugin for Codex, owned by [Jackson Stone](https://github.com/TheMakerOfWorlds). No paid email bridge, hosted relay, gogcli runtime, or third-party Python packages. Runtime: Python 3.10+ and macOS Keychain.

Five everyday commands: `accounts`, `search`, `read`, `send`, and `status`. The `doctor` command verifies authentication; `scripts/auth.py` handles one-time setup.

## Gmail-only access

The OAuth client requests exactly these two permissions:

- `https://www.googleapis.com/auth/gmail.readonly` — read/search mail.
- `https://www.googleapis.com/auth/gmail.send` — send mail.

No Drive, Calendar, Contacts, account administration, broad `mail.google.com`, or Gmail modification permission. Scope validation rejects extra or missing permissions at initial connection and refresh. Google defines the scopes in its [Gmail API documentation](https://developers.google.com/workspace/gmail/api/auth/scopes).

Each account has a short ID, an exact email address, and purpose/avoidance notes. Metadata lives in `~/.config/email-agent/accounts.json`, outside this repository. The current Gmail profile is verified before reading or sending; references are bound to the account identity. Cross-account replies and arbitrary From overrides are blocked.

## Long-lived authentication

Desktop OAuth uses PKCE S256, random state, and a loopback callback. The dedicated client and refresh tokens live in macOS Keychain; secret values never appear in process arguments or logs. Access tokens are refreshed automatically and cached only in process memory. Connecting verifies both the initial identity and a real refresh exchange.

Configure the Google OAuth app as **External / In production** to avoid the seven-day refresh-token limit imposed on external apps in Testing. This is a setup requirement, not a setting that the mail client can change. Personal-use apps can qualify for Google's verification exception. Google may still invalidate access after revocation, certain password changes, prolonged inactivity, or organization policy changes. [OAuth token expiration](https://developers.google.com/identity/protocols/oauth2#expiration), [personal-use verification exception](https://support.google.com/cloud/answer/13464323).

## Small agent context

- Skill-based discovery: 23 tokens of name/description in the current synthetic measurement; the full 296-token instruction loads when relevant. No MCP tool schemas added.
- Account notes load on demand, without secrets or provider settings.
- Search retrieves only selected metadata; defaults to 10 results, hard maximum 25, with pagination.
- Reads return 4,000 body characters by default, with `next_offset` for continuation. Raw MIME/base64 stays out of the agent response.
- HTML-only messages become text without fetching remote resources. Attachments are listed as metadata.
- Output shaping uses local code, with no extra LLM calls.

[Benchmark results](benchmarks/results.json) use synthetic fixtures and `tiktoken/o200k_base`; they are not measured billing savings. Reading a message still fetches its full body locally before returning a bounded chunk.

## Use

Follow [setup.md](setup.md), then:

```bash
python3 scripts/email_agent.py accounts
python3 scripts/email_agent.py doctor work
python3 scripts/email_agent.py search work 'is:unread newer_than:7d'
python3 scripts/email_agent.py read 'REF_RETURNED_BY_SEARCH'
python3 scripts/email_agent.py send work --message /path/to/message.json --preview
```

Actual sends require a stable `--request-id`. The local SQLite ledger reserves the ID before contacting Gmail and prevents concurrent or repeated invocation with the same ID. Gmail send POSTs are never automatically retried. A crash or timeout can leave a pending/uncertain outcome; inspect Sent mail before attempting another send. This provides conservative duplicate protection, not a distributed exactly-once guarantee. The ledger stores hashes and compact outcomes, not message bodies.

Plain-text sends, Unicode, local attachments, and threaded replies are supported. Reply subjects should match the original conversation. Draft requests remain local. Gmail labels/archive/delete, Google-saved drafts, aliases, attachment downloads, non-Google providers, background sync, and monitoring are not implemented.

## Development and ownership

```bash
python3 -m unittest discover -s tests -v
```

The repository owns the Gmail, OAuth, MIME, routing, and output code. It does not download or auto-update another email CLI. Dependencies on macOS, Python, and Google's APIs remain; occasional compatibility/security maintenance may still be needed. The earlier gogcli adapter and installer were removed.

Optional development tools are PyYAML for Codex validators and tiktoken for the benchmark. They are not runtime dependencies. See [VALIDATION.md](VALIDATION.md) for tested behavior and remaining live checks.

Google's consent screen links to the owner's [public app information and privacy notice](https://gist.github.com/TheMakerOfWorlds/0ea2b4aa332d760f4a08269a8d146196). Its [source](docs/public-information.md) is maintained here. The notice is public; private account configuration and credentials are not part of the repository or plugin package.
