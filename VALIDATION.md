# Validation — September 4, 2026

The independent client uses Python standard library and macOS Keychain. No gogcli runtime remains.

## Completed

- 52 Python tests cover routing, wrong-account blocking, identity-bound references, bounded Unicode reads, HTML conversion, header injection, attachment changes, request reuse/conflict, concurrent sends, and uncertain outcomes. Recipient tests cover addressed aliases versus authenticated mailboxes, repeated delivery headers, forwarding/group context, metadata-only search, visible versus absent Bcc, and bounded routing output.
- OAuth tests cover exact Gmail-only scopes, PKCE/offline authorization, state validation, wrong-mailbox rejection before storage, refresh verification, cached access, excess-scope rejection on refresh, and foreign client endpoints.
- Transport tests verify three bounded attempts for transient GET failures, redacted provider errors, and no automatic retry of a send POST.
- Native MIME tests cover Unicode, To/Bcc/From, reply headers/thread IDs, and attachments. Alias tests cover local allowlists, account-specific selection, live accepted/pending/missing approval, shared-purpose metadata, invalid shared flags, display-name injection, read-only settings access, selected From/Reply-To, actual stored sender verification, and replay protection across aliases.
- A real macOS Keychain write/read/delete round trip passed using a temporary random test record. No secret values were printed; the test record was removed.
- Codex plugin and skill validation passed; the standalone plugin was installed from the personal marketplace.
- The three requested account-purpose entries were saved in owner-only local configuration outside Git.
- Synthetic benchmark with recipient/delivery context: 23 discovery tokens, 451 full-skill tokens, zero MCP schemas; ten headers 1,033 to 827 tokens; a long-message first chunk 21,955 to 776 tokens. The chunk returns 4,000 of 21,400 characters and preserves continuation. These are fixture measurements, not live mail or billing savings.

## Live connection verification

The dedicated Google Cloud project has Gmail API enabled, a Desktop OAuth client named Email Agent Desktop, and an External audience. The publishing status was verified as **In production** before any mailbox was connected. Google's unverified-app notice remains for this personal-use application; production status does not imply Google verification.

All three locally configured accounts, `personal`, `dittodub` (previously `work`), and `maker`, are authenticated. For each account:

- The initial token exchange returned exactly `gmail.readonly` and `gmail.send`.
- The Gmail profile matched the configured email address before the refresh token was stored.
- Credentials were saved in macOS Keychain, and a real refresh exchange succeeded.
- Google did not return a fixed refresh-token expiration interval. This does not guarantee perpetual access; Google revocation and policy rules still apply.
- A fresh process successfully searched for one inbox message and read it through the normal client. The initial personal result contained 1,214 body characters; work contained 1,000; maker contained 2,831. All stayed within the 4,000-character default, and search/read results were marked untrusted. Private message content was not included in the verification report or repository.

The client secret was captured from Google's one-time display directly into Keychain without printing it or placing it in source, command arguments, or a secret file. Account notes remain in owner-only local configuration. The generic public privacy notice required for app branding contains no mailbox data or credentials.

## Live send and recipient-context verification

At the user's request, one clearly labeled delivery-test email was sent from the `work` account to the `personal` account using the installed plugin and a stable request ID. The plugin recorded a successful send. A recipient-side search returned exactly one matching message. The sent and received copies matched in sender, recipient, subject, and body after normalizing transport whitespace, including a Unicode check mark. The received message's Delivered-To header matched the authenticated personal mailbox.

The updated client also searched and read existing messages addressed to the user's team and contact addresses but delivered to the work mailbox. Both live examples preserved the original To address and the separate Delivered-To/mailbox identity. Account addresses, message references, and private message content remain outside this repository. Reading recipient/forwarding context required no additional Google scopes.


## Shared sender setup and verification

The company mailbox now uses a company-specific account ID instead of the generic work ID. Its primary address remains the default. Local Team and Contact notes explicitly mark them shared: mail and replies reach other people. The installed skill uses shared senders only when requested or clearly implied by shared company correspondence, never solely because incoming mail addressed the group. Personal matters use the personal mailbox, and individual company correspondence uses the primary company address.

Team was added and verified through Gmail's normal Send mail as UI. The installed plugin sent one clearly labeled Team test to the user's personal mailbox with a stable request ID. Exactly one copy arrived; its From was the verified Team identity, Reply-To was Team, To and Delivered-To matched the personal mailbox, and the body matched the sent copy after transport whitespace normalization. No reply was sent to the shared group.

Contact is configured in local notes but Gmail still reports it not configured, so the client blocks it from sending. Its Gmail setup form was filled, but Chrome's automation tool reports an open extension UI blocking further interaction. The user has been asked to dismiss that popup; Contact verification and its live sender test remain pending. Repeated state checks confirm the same blocker. Neither alias requires additional OAuth scopes, settings-write permission, or a new token grant.
