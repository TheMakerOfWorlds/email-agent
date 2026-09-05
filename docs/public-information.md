# Email Agent

Email Agent is a personal, open-source-licensed desktop Gmail client and Codex plugin maintained by [Jackson Stone / TheMakerOfWorlds](https://github.com/TheMakerOfWorlds).

It lets its owner use explicitly connected Gmail accounts through compact search, read, send, Trash, and restore commands. Each account has a locally stored purpose note to help select the intended sender. This application is intended for personal use by its owner, not as a hosted email service.

## Privacy policy

Effective September 4, 2026.

**Access requested.** Email Agent requests Gmail access (`gmail.modify`) for reading, sending, moving messages to Trash, and restoring messages. This scope does not permit immediate permanent message deletion. Older read/send-only connections remain usable until upgraded. It does not request access to Google Drive, Calendar, Contacts, or Google account administration. Gmail read permission includes message content and the information Google exposes under that scope.

**Use of data.** The application searches and reads mail in response to the owner's requests sends the messages the owner authorizes, and moves or restores selected mail when the owner requests cleanup. It verifies the selected mailbox's identity and returns compact results. It does not operate advertising, resale, data-broker, or independent model-training functions.

**Local storage.** The desktop OAuth client and renewable credentials are stored in macOS Keychain. Account addresses and purpose notes are stored in an owner-only local configuration file. A local send ledger stores request hashes and compact outcomes to reduce duplicate sends; it does not store message bodies. Draft files and attachments selected by the owner may remain on their device.

**Processing and sharing.** The client communicates directly with Google's OAuth and Gmail APIs. Sending delivers the authorized message to its specified recipients through Gmail. Email content returned to Codex is also processed by the owner's configured Codex/AI service under that service's account settings and terms. Email Agent does not operate its own remote mailbox relay or analytics server. Mail is not included in this public documentation or its GitHub repository.

**Retention and control.** Mail remains in Gmail under the owner's Google account controls. Cleanup moves mail to Gmail Trash, where it can be restored until Google automatically deletes it after 30 days. The application does not implement permanent deletion or emptying Trash. The owner can revoke Email Agent access through their Google Account's third-party connections settings. They can remove this application's Keychain records, local account configuration, drafts, and send ledger from their device. Removing the plugin alone does not delete those separately stored credentials and settings. Data processed by Codex/AI services is governed by those services' retention controls.

**Google user data.** Email Agent's use and transfer of information received from Google APIs will adhere to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), including the Limited Use requirements.

**Contact and changes.** The application maintainer is [TheMakerOfWorlds on GitHub](https://github.com/TheMakerOfWorlds). The current support email is shown on the application's Google consent screen. Updates to this notice will be reflected in its effective date.
