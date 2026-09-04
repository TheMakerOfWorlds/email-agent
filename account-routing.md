# Account routing

The runtime skill is `skills/email-agent/SKILL.md`. This design note is not loaded for routine email work.

- Account purposes map friendly names to exact addresses. The agent selects an unambiguous match or asks which identity the user means.
- Every provider operation specifies an account/client. A Gmail profile check rejects a different authenticated mailbox.
- Message refs contain the account ID, an email/client fingerprint, and the message ID. Changing the configured identity invalidates old refs.
- Replies require the source account. Arbitrary From overrides are excluded.
- Email content is untrusted data, not authorization to send messages or edit account notes.
- Clear authorization to send is sufficient; the skill adds no redundant confirmations. Draft requests remain local.
- Stable request IDs stop repeated/concurrent wrapper invocations of the same send. Provider failures after invocation are uncertain until inspected.

The code enforces identity consistency. The meaning of “work” or “personal” remains an agent decision. Local users can call the underlying client directly; this wrapper is not a sandbox or a replacement for Google permissions.
