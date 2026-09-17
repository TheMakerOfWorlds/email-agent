# Privacy notice template for your own Email Agent app

Copy the notice below to a page you control. Replace every bracketed field, check it against your actual configuration and use, and remove these instructions before publishing. Use your own contact details and effective date. This is a starting point, not an assurance that Google will accept a particular URL or waive verification. If you add features, hosted processing, other users, or new scopes, revise the notice accordingly.

Publish only the notice, never account configuration, authorization URLs, OAuth JSON, tokens, email, or private logs. Use its public URL in your Google app's Branding settings if required. The maintainer's separate notice describes the maintainer's installation and is not your app's privacy policy.

---

# [Your app name]

Effective date: [YYYY-MM-DD]

Operator: [Your name or organization]

Contact: [Your support email or contact page]

This application is a personally operated desktop Gmail client using the open-source Email Agent code. It connects only the mailboxes its operator explicitly configures and authorizes. It is not a hosted email service.

## Permissions and use

The app requests `gmail.modify` for reading, searching, sending, organizing messages, retrieving selected attachments, and moving/restoring messages in Trash. It requests `gmail.settings.basic` for saved Gmail filters and basic settings access. It does not request Drive, Calendar, Contacts, or Google account administration access. Not every operation covered by these permissions has an implemented command.

The operator uses the app to search/read mail, send requested messages, organize selected messages, download selected attachments, and manage saved filters. Filters continue to affect future matching mail until removed. The client does not implement emptying Trash or immediate permanent deletion; Google applies its normal Trash retention rules.

[If enabling optional Workspace services, replace the Gmail-only statement above as appropriate and describe your exact selection from Calendar, Meet, Drive, Docs, Sheets and Contacts. List scopes from the Workspace setup guide. Explain verified-email identity access, calendar guest notifications, existing collaborator visibility, broad Drive access if selected, and access to existing Meet artifacts. Do not claim these permissions are enabled merely because the code is installed.]

## Storage and processing

Desktop OAuth client information and refresh grants are stored in macOS Keychain. Account addresses and purpose notes are stored in private local configuration. Local ledgers retain request hashes and compact outcomes; removed filter definitions are backed up locally. Selected attachments and locally prepared message files remain on the device until removed. The app does not maintain a complete local mailbox mirror.

The client communicates directly with Google's OAuth and Gmail APIs. Messages sent through Gmail are delivered to their specified recipients. Mail returned to [your configured agent/AI service] is processed under that service's settings and terms. [Describe your actual agent service and link its applicable privacy information.] If the operator configures another trusted Mac, the app can copy its Gmail grants directly into that Mac's Keychain over verified SSH.

[For Workspace use, also describe direct access to the selected Google APIs, separate Keychain grants, local Workspace operation receipts and selected local files. Explain that returned document text, contact data, calendar details and Meet artifacts are processed by your configured AI service too. Include any authorized second-Mac transfer and explain that uninstall does not undo cloud edits or retract invitations.]

This installation operates no separate mailbox relay, advertising system, data resale service, or analytics server. The upstream repository maintainer does not receive the installation's credentials or mailbox data. Shared mailbox/group recipients and organizational administrators retain their existing access under the operator's Google environment.

## Control and retention

The operator can revoke the app through Google Account third-party connections, remove the plugin, and delete its Keychain records and local files. Uninstalling alone does not revoke OAuth or remove separately stored credentials, Gmail messages, or saved Gmail filters. Access on another Mac may rely on the same grant. Google and the configured agent service have their own retention controls for information they process.

## Google user data

This application's use and transfer of information received from Google APIs will adhere to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), including Limited Use requirements.

## Changes and contact

The operator will update this notice when the application's data handling changes. Contact [your support email or contact page] about this installation.
