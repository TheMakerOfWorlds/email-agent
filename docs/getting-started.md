# Set up Google Workspace Agent, even if this is your first plugin

Google Workspace Agent lets Codex work with your Gmail and, if you choose, your Calendar, Meet, Drive, Docs, Sheets, and Google Contacts. You can connect several Google accounts and explain what each one is for. That helps the agent keep your personal life and different companies separate.

You do not need to understand programming to ask an agent to help. Setup does include some Google settings and a few computer commands. This guide explains what those steps mean, what you need to do yourself, and how to tell whether they worked.

## The easiest way: ask Codex to guide you

Open a Codex task and paste this:

> Help me install and set up Google Workspace Agent from https://github.com/TheMakerOfWorlds/google-workspace-agent. I am new to plugins. Read the README, docs/getting-started.md, and skills/email-agent/references/setup-assistant.md. Check what is already installed before changing anything. Explain each stage in plain language, do the parts you can, and guide me through the parts that require my sign-in. Start with one account and only the services I choose. Keep credentials out of this chat. Tell me what has actually been verified before moving on.

If you already downloaded the repository, open that folder in Codex and use the same request. If the plugin is already installed, you can simply say **“Help me set up Google Workspace Agent. I’m new to this.”**

The agent should help with the actual setup, rather than just hand you a long list of commands. It may need you to sign in, approve permissions, or use your fingerprint/passkey. Enter passwords directly into Google's own page, never into the chat. If the agent cannot control your browser, it should give you the next few clicks and the exact thing to look for.

## What you need before starting

- **A Mac.** The current credential storage uses macOS Keychain. Windows and Linux setup is not supported by this version.
- **Codex, signed in.** The plugin is free and open source. It does not include a Codex subscription or AI usage.
- **A Google account you can sign into.** Start with one; add more after it works. Company accounts may have administrator restrictions.
- **Access to Google Cloud Console.** This is where you create the Google connection owned by you. The setup does not ask you to buy a server or give the maintainer access to your account.

If you do not know whether your Mac has Python, Git, or the Codex command-line tool, ask the agent to check. These are tools the installer uses. Do not install random software or sign up for a paid service just because a command is missing.

## A few words you will see

| Word | What it means here |
| --- | --- |
| Repository or repo | The GitHub folder containing the plugin's code and guides. |
| Terminal | The Mac app where you run text commands. The agent can often run them for you. |
| Google Cloud project | A container in your Google account for this app's settings. It is not your email inbox. |
| API | The connection the plugin uses to ask Google to do something. Enabling an API does not sign in to your account. |
| OAuth / consent | Google's sign-in and permission process. You approve access without giving the plugin your password. |
| Desktop client | The Google app configuration for a program running on your Mac. |
| Scope | A permission, such as reading/editing calendar events. |
| Keychain | macOS's storage for private credentials. |
| Account ID | A short local nickname such as `personal` or `acme`; it is not your email address. |

## Your route through setup

| Stage | What you are doing | How you know it worked |
| --- | --- | --- |
| 1 | Get the plugin files and check your Mac | The folder and required commands are available. |
| 2 | Choose an account and its purpose | The exact address and company/personal context are clear. |
| 3 | Create your own Google app | The correct project, APIs, permissions, and Desktop client are configured. |
| 4 | Connect the account | The terminal confirms the correct identity and a working credential refresh. |
| 5 | Install the plugin into Codex | Codex lists the plugin as enabled and the update job is configured. |
| 6 | Try a small read-only request | It returns a result from the intended account, or a valid empty result. |
| 7 | Add more services/accounts | Each additional connection is verified separately. |

You can pause between stages. Tell the agent where you stopped; it should inspect the current state and resume. You should not have to recreate a working Google app or reconnect accounts that already work.

## 1. Get the files

If the agent is doing this, let it check for an existing installation first. If doing it yourself, open **Terminal** from Applications → Utilities and follow [Before you start](../setup.md#before-you-start). Run one command at a time and read the result before continuing.

The documented download command is:

```bash
mkdir -p "$HOME/plugins"
git clone https://github.com/TheMakerOfWorlds/google-workspace-agent.git "$HOME/plugins/email-agent"
cd "$HOME/plugins/email-agent"
```

If Terminal says the destination already exists, do not delete it: it may be your working installation. Ask the agent to inspect it.

The folder is still named `email-agent` for compatibility. That is expected even though the GitHub repository and Codex display name are **Google Workspace Agent**. A command beginning `python3 scripts/...` must be run from inside that folder. `No such file or directory` often means Terminal is in the wrong folder.

**Checkpoint:** The agent should confirm the source folder and that Python, Git, and the Codex plugin command are available.

## 2. Decide which account to connect first

Tell the agent the exact email address and what it is for. For example:

> Connect my personal Gmail for friends, shopping, and appointments. Keep company business out of it.

Or:

> Connect my Acme company account for Acme customers and operations. I also own another company, so don’t call this account just “work.”

The agent saves this description in a private local account file. It should not put your real addresses into the repository's example file or publish them to GitHub. The [account-purpose instructions](../setup.md#account-purposes) include the exact file format for manual setup. You can ask the agent to write it instead of editing JSON yourself.

Use separate company nicknames, such as `acme` and `other-company`. Addresses such as `team@...` or `contact@...` may be shared with other people; explain that to the agent. They are not automatically separate Google accounts or meeting organizers. Shared sending addresses are an optional later setup step.

**Checkpoint:** Running the account-list command should show only your intended identities and correct purposes. This lists configuration; it does not prove Google is connected yet.

## 3. Create the Google app that belongs to you

Follow [Google project and desktop client](../setup.md#google-project-and-desktop-client) with your agent. That section contains the actual permission names and import commands, so you do not have to guess them.

There are five parts:

1. **Create/select a dedicated project.** Check the Google account shown in the browser. Use your own project, or the appropriate company-owned project if that is intentional.
2. **Enable Gmail API.** This allows your app to use Google's mail connection. It does not grant mailbox access by itself.
3. **Configure the consent screen.** This is the name and information Google shows when you connect an account. If Google asks for a privacy notice, the guide includes a template to adapt for your own installation. Ask the agent for help; do not copy someone else's identity or claim a domain you do not own.
4. **Select the documented Gmail permissions and publishing status.** The guide explains the difference between Testing, In production, and Google verification. “In production” does not publish your emails or credentials. Correct setup avoids the short-lived Testing grants described in the technical guide, though Google can still require reconnection later.
5. **Create a Desktop app client and import its private configuration into Keychain.** The download is a credential file. Keep it out of chat, GitHub, and shared folders. The agent should verify successful import without printing its contents.

A Google prompt to start a Cloud trial or attach a payment method is not part of this Gmail setup. If the screen differs from the guide, have the agent identify the current page and next step rather than guess.

**Checkpoint:** You have your own project with the intended API/permissions, and the client importer confirms storage in macOS Keychain. You still need to connect the mailbox next.

## 4. Sign in and connect the first account

Follow [Connect and verify](../setup.md#connect-and-verify). The agent starts a connection command for the selected account nickname. Open its Google sign-in link in the matching browser profile **on the same Mac**, and leave the command running.

Check the full email address on Google's permission screen. If it is the wrong account, switch before approving. Read the requested access and compare it with the services you chose. Complete your password, passkey, or verification directly with Google.

If Google shows a warning or an organization block, tell the agent the warning text without copying private codes. A warning about your own unverified app is different from an administrator denying access. The detailed guide explains the supported personal-app case; an organization restriction must be resolved with that organization.

After the browser accepts the connection, return to the terminal. **A browser success page alone is not the final check.** The command should confirm `authenticated: true` and `refresh_verified: true`, with the intended account. The agent should then run the small read-only checks in the guide. No test email needs to be sent just to connect the account.

**Checkpoint:** Correct identity, successful credential refresh, and a successful read-only Gmail check. An empty inbox can be a valid result.

## 5. Make the plugin available in Codex

Follow [Codex installation](../setup.md#codex-installation). First register the local plugin through the documented marketplace helper; then run:

```bash
python3 scripts/install.py
```

The installer expects that registration to exist. If it fails, the agent should inspect the error and resume from the missing prerequisite—not tell you to repeatedly run the same command.

The standard installer enables automatic GitHub updates on first setup. Your Mac checks hourly and at login without using agent tokens. This means trusting future code published to the selected repository. To install without automatic updates, use `python3 scripts/install.py --no-auto-update`. If you previously disabled updates, reinstalling preserves that choice. [Update controls and recovery](auto-updates.md) explain how to check or change it.

Start a **new Codex task** after installation so it picks up the plugin instructions. Try:

> Use Google Workspace Agent to list my configured accounts and verify my personal Gmail. Don’t send anything.

Replace “personal” with the account you actually connected. If the task cannot find the plugin, ask it to check installation and enabled state rather than reconnect Google immediately.

**Checkpoint:** The plugin is enabled in Codex, the new task finds it, and it verifies the intended mailbox. Check automatic-update status separately; plugin installation and Google authorization are different things.

## 6. Add the other Google services you want

Once Gmail works, follow [Workspace setup](workspace-setup.md) for Calendar, Meet, Drive, Docs, Sheets, and Contacts. This uses a separate Desktop client and separate consent, so Gmail-only access stays separate.

Tell the agent which account and services you want. You do not need to enable all six on every account. For example:

> Add Calendar and Contacts to my personal account. Add Calendar, Meet, Drive, Docs, and Sheets to Acme.

Drive permission in this implementation covers accessible existing files; it is not limited to one document you pick. Ask the agent to explain the requested permissions before connecting. Installing the modules is not proof that those permissions have been granted.

The agent should verify each selected service with a small read-only request. It should not send invitations, create contacts, or edit a real document just to prove sign-in worked. Meet recordings/transcripts are available only when they already exist and the account has access; the plugin does not join or record calls.

**Checkpoint:** A clear per-account list of which services are connected and which are still pending. If only Gmail works, the summary should say so.

## 7. Add another account or Mac later

For another email address, add its purpose notes and authorize that exact account. Do not replace the first account's working credentials. For a second company, choose a separate nickname and explain its boundaries.

For another Mac, use [the second-Mac guide](../setup.md#another-mac-and-later-updates). Code installation and credential transfer are separate. A transfer of this plugin's grants should only go to your intended Mac over the documented verified connection. Both machines must be checked independently; “files copied” is not the same as “account works there.”

## If you get stuck

Tell the agent: **“I’m on [page or step]. I expected [result], but I see [error]. Help me continue.”** You do not need to diagnose it yourself. Share the wording of the error, not tokens, credential files, callback URLs, or authorization codes.

| What you see | What to ask the agent to check |
| --- | --- |
| `command not found` | Which prerequisite is missing, and the supported way to install it. |
| Wrong Google address | Browser profile and the account selected for this connection. |
| Browser succeeded but command did not | Whether the local callback and final identity/refresh checks completed. |
| “Not connected” | Whether this specific account has authorized this specific service. |
| Permission denied / 403 | API enablement, granted permissions, and organization policy for that account. |
| Plugin is missing in a task | Installed/enabled state and whether a new task is needed. |
| Update failed | The updater's status receipt and local source changes; do not delete your work. |

At the end, ask for a short completion checklist: installed plugin, each connected account, verified services, update status, and anything still blocked. That gives you a reliable starting point for everyday use.
