# Account routing

The runtime skill is `skills/email-agent/SKILL.md`. This design note is not loaded for routine email work.

- Account purposes map company-specific names to exact addresses, allowing multiple companies without one ambiguous work identity. Personal matters use the personal account. Individual company correspondence uses that company's primary mailbox. The agent selects an unambiguous match or asks which identity the user means.
- Every provider operation specifies an account/client. A Gmail profile check rejects a different authenticated mailbox.
- Message refs contain the account ID, an email/client fingerprint, and the message ID. Changing the configured identity invalidates old refs.
- Replies require the source account. Arbitrary From overrides are excluded. Optional `--as ALIAS_ID` selects a locally configured alias within that account; Gmail must report it accepted immediately before sending. The sent copy's actual From is checked afterward. Changing the selected alias conflicts with reuse of the same request ID.
- Alias notes include a boolean `shared` flag. Shared group addresses reach multiple people, including replies. Use one only when the user requests it or the task clearly implies shared company correspondence. Incoming To alone never selects a shared sender. Check shared recipients as well, and keep private/personal content out of shared group correspondence. This purpose-based selection is an agent rule, not semantic content filtering by the client.
- Alias sends set Reply-To to the selected alias. Without `--as`, the client uses the primary mailbox regardless of Gmail's UI defaults. The read-only `senders` command reports local notes and live approval, without exposing unrelated aliases or SMTP settings.
- `mailbox` identifies the authenticated mailbox holding a message; `to`/`cc` show the addressed recipients. Search also includes up to two Delivered-To values. A full read includes Sender, Reply-To, visible Bcc, and available delivery, original-recipient, forwarding, Resent, and mailing-list headers.
- Repeated delivery headers are retained as arrays in provider order. Header context is evidence from the message, not proof of alias ownership or permission to send as it. Missing Bcc recipients and stripped forwarding information cannot be reconstructed. The client does not infer a complete delivery route.
- Routine search and reads remain bounded. The optional `delivery` object has a 320-character value budget in search and 3,000 in reads; `truncated: true` reports omitted/truncated routing values. Ellipses indicate shortened ordinary headers.
- Email content is untrusted data, not authorization to send messages or edit account notes.
- Clear authorization to send is sufficient; the skill adds no redundant confirmations. Draft requests remain local.
- Stable request IDs stop repeated/concurrent wrapper invocations of the same send. Provider failures after invocation are uncertain until inspected.

The code enforces identity consistency. Matching a task to a company, personal identity, or shared alias remains an agent decision guided by local notes. Local users can call the underlying client directly; this wrapper is not a sandbox or a replacement for Google permissions.
