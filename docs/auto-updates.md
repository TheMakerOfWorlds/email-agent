# Automatic updates from GitHub

Complete the normal [installation](../setup.md) first. Automatic updates are optional and require macOS, Python 3.9+, Git, an enabled `email-agent@personal` installation, and the existing `~/plugins/email-agent` source. No paid service, agent turn, GitHub token, or additional Google permission is needed for this public repository.

## Enable on each Mac

From the source checkout:

```bash
python3 scripts/auto_update.py enable
python3 scripts/auto_update.py status
```

The command installs a per-user macOS LaunchAgent, checks immediately, then checks hourly while that user is logged in. It checks again at login. A sleeping, offline, or logged-out Mac cannot update until it runs again. Each Mac downloads independently from GitHub; it does not need the other Mac to be online. Setup does not automatically enable updates for people who only clone the repository.

The default trusted upstream is `TheMakerOfWorlds/google-workspace-agent`, branch `main`. To follow your own fork, configure that fork as the checkout's `origin` and enable with `--repository YOUR_NAME/google-workspace-agent`. Only a GitHub owner/repository slug is accepted. Do not put credentials in URLs. This implementation targets the existing `personal` local marketplace; a differently named marketplace needs adaptation before enabling.

Enabling updates authorizes installing and running future code from that upstream, including its tests. Tests are compatibility checks, not a security sandbox. No new Google scopes are automatically granted. A feature that needs new access still requires Google consent.

## What each check does

1. Acquire an exclusive local updater lock and check the configured source and enabled Codex installation.
2. Fetch GitHub `main` over HTTPS into a private local bare Git repository, with no interactive authentication or inherited Git overrides.
3. Require the current source revision to be an ancestor of the new revision. Stop for local tracked/untracked edits, detached checkouts, a mismatched origin, rewritten/divergent history, or a new revision reusing the installed version.
4. Stage a bounded archive of regular source files. Reject traversal paths and symlinks. Run the release's Python tests and compile check before promotion.
5. Fast-forward a developer checkout, or atomically point a managed second-Mac source at the staged release. Reinstall using `codex plugin add email-agent@personal`.
6. Verify the enabled version and every published file in the Codex cache, then write a compact status receipt. Existing account configuration, Google grants, and operation ledgers are not synchronized or edited by this updater.

The already-current path checks source/cache contents without reinstalling. A disabled or uninstalled plugin is not silently re-enabled. New Codex tasks pick up new instructions; this does not hot-reload an active task's context. Old managed releases are retained for recovery and are not automatically deleted.

## Check, pause, or disable

```bash
python3 scripts/auto_update.py status
python3 scripts/auto_update.py run
python3 scripts/auto_update.py disable
```

`status` shows enabled/loaded state, upstream, and the latest receipt: `current`, `updated`, or `failed`, with the revision/version when verified. A `busy` result means another updater holds the lock. `run` requires updates to be enabled. `disable` unloads/removes the LaunchAgent but leaves the installed plugin, credentials, source, and last status intact. Re-enable with the first command above.

The status receipt is at `~/.config/email-agent/auto-update-status.json`; settings are beside it in `auto-update.json`. The LaunchAgent is `~/Library/LaunchAgents/com.themakerofworlds.email-agent.update.plist`. No mailbox content, OAuth values, subprocess output, or continuously growing log is written by the updater.

## Recovery and maintenance

- **Local changes:** Commit, move, or reconcile your work deliberately; the updater never stashes or discards it. It retries on the next scheduled check.
- **Divergent history:** Reconcile your branch with the selected GitHub main branch manually. Force-pushed/rebased history is intentionally not adopted automatically.
- **Version reused:** The maintainer must publish a new cachebuster for changed source; readers should not edit the release version locally.
- **Failed tests/network/CLI:** The receipt remains failed; retry after fixing the cause with `run`. Subprocesses have timeouts and checks retry next hour, rather than looping rapidly.
- **Failed installation:** A managed-source link is restored and reinstall of the previous version is attempted. A developer checkout stays fast-forwarded to preserve any concurrent edits; its next check retries installation. Failure is never reported as success.
- **Mac power loss during promotion:** Inspect source, the receipt, and the installed version before retrying. A managed deployment metadata mismatch requires reconciling/restoring the known release; it is not silently reset.
- **Removing the plugin:** Disable updates first, then follow [removal instructions](security.md#remove-an-installation).

Maintainer workflow still runs tests and validators, updates the manifest with the plugin-creator cachebuster helper, commits, and publishes to `main`. Initial second-Mac setup and deliberate credential/account-note transfers still use `sync_remote.py`; auto-updates only distribute public code. Avoid simultaneous manual deployment and updater runs by disabling updates during a deliberate deployment, then re-enabling them afterward.

## Repository rename compatibility

The repository was renamed from `TheMakerOfWorlds/email-agent` to `TheMakerOfWorlds/google-workspace-agent`. Updated clients normalize the old official upstream to the new name and accept an existing checkout with the old official origin. Custom forks are unchanged. The installed plugin ID and local paths remain `email-agent`; keep the explicit destination in the clone command.
