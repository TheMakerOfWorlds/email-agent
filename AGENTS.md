# Email Agent delivery

Keep credentials and personal account metadata outside Git. Use company-specific account IDs and preserve shared-address purpose notes.

After changing this plugin, run the relevant tests and Codex validators, update its cachebuster with the plugin-creator helper, install locally, and commit the reviewed changes. If `~/.config/email-agent/remote.json` exists, run `python3 scripts/sync_remote.py` to update the configured remote Mac and verify it. Report an unavailable remote explicitly; never claim both copies are current without a successful result. Add `--copy-credentials` only when the user authorizes transferring this plugin's Gmail grants or adding a newly authorized mailbox there. Never print/export credential values to files or logs.

Deployment is on demand. Do not install a background timer or transfer other services' credentials. Pending or uncertain sends must be investigated on the machine that attempted them; the send ledger is not continuously shared between Macs.

Workspace modules use a separate OAuth client and `workspace.token.*` Keychain records. `--copy-credentials` still copies Gmail only; use `--copy-workspace-credentials` only for explicitly authorized Workspace transfer. Ordinary code updates reuse whatever grants the destination already has. Keep service instructions in on-demand references, account selection explicit, and resource refs bound to the account/client. Clarify ambiguous company identity rather than falling back to personal. Workspace operation receipts stay on the machine that attempted them.
