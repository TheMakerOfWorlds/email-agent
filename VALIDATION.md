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

## Live connection verification

The dedicated Google Cloud project has Gmail API enabled, a Desktop OAuth client named Email Agent Desktop, and an External audience. The publishing status was verified as **In production** before either mailbox was connected. Google's unverified-app notice remains for this personal-use application; production status does not imply Google verification.

Both locally configured accounts, `personal` and `work`, are authenticated. For each account:

- The initial token exchange returned exactly `gmail.readonly` and `gmail.send`.
- The Gmail profile matched the configured email address before the refresh token was stored.
- Credentials were saved in macOS Keychain, and a real refresh exchange succeeded.
- Google did not return a fixed refresh-token expiration interval. This does not guarantee perpetual access; Google revocation and policy rules still apply.
- A fresh process successfully searched for one inbox message and read it through the normal client. The personal result contained 1,214 body characters; the work result contained 1,000. Both stayed within the 4,000-character default, and both search/read results were marked untrusted. No message content was included in the verification report or repository.

The client secret was captured from Google's one-time display directly into Keychain without printing it or placing it in source, command arguments, or a secret file. Account notes remain in owner-only local configuration. The generic public privacy notice required for app branding contains no mailbox data or credentials.

No real email has been sent. Send permission is granted, and native MIME/send behavior is covered by automated tests; actual message delivery remains untested until the user requests a message to a specified recipient.
