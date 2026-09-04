# Validation — September 4, 2026

The independent client uses Python standard library and macOS Keychain. No gogcli runtime remains.

## Completed

- 35 Python tests cover routing, wrong-account blocking, identity-bound references, bounded Unicode reads, HTML conversion, header injection, attachment changes, request reuse/conflict, concurrent sends, and uncertain outcomes.
- OAuth tests cover exact Gmail-only scopes, PKCE/offline authorization, state validation, wrong-mailbox rejection before storage, refresh verification, cached access, excess-scope rejection on refresh, and foreign client endpoints.
- Transport tests verify three bounded attempts for transient GET failures, redacted provider errors, and no automatic retry of a send POST.
- Native MIME tests cover Unicode, To/Bcc/From, reply headers/thread IDs, and attachments.
- A real macOS Keychain write/read/delete round trip passed using a temporary random test record. No secret values were printed; the test record was removed.
- Codex plugin and skill validation passed; the standalone plugin was installed from the personal marketplace.
- The two requested account-purpose entries were saved in owner-only local configuration outside Git.
- Synthetic benchmark: 23 discovery tokens, 296 full-skill tokens, zero MCP schemas; ten headers 743 to 521 tokens; a long-message first chunk 21,929 to 739 tokens. The chunk returns 4,000 of 21,400 characters and preserves continuation. These are fixture measurements, not live mail or billing savings.

## Live authentication boundary

The intended personal owner account is signed into Google Cloud. The dedicated OAuth setup and publishing status are being configured. The two mailbox entries are **configured but not authenticated**. `doctor` correctly reports `Dedicated OAuth client is not configured`.

Real Gmail scopes, OAuth refresh, read access, and message delivery are not yet verified. No real email has been sent. The application verifies refresh and identity automatically when each account completes connection. A real send is deferred until the user requests a message to a specified recipient.
