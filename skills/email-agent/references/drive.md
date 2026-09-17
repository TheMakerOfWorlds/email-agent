# Drive

Use `python3 <plugin-root>/scripts/google_agent.py drive ACCOUNT ACTION --input FILE`.
Pick the account/company, search compact metadata, then open selected resources. Inspect owner information, parent folders, and purpose before writing to a shared file. Access does not make another company's file the right destination.

| Action | Input JSON |
| --- | --- |
| `search` | `{"query":"trashed = false and name contains 'invoice'"}` |
| `open` | `{"id":"ID_FROM_USER_LINK"}`; verifies access and returns a typed ref |
| `get` | `{"ref":"FILE_DOC_OR_SHEET_REF"}` |
| `download` | `{"ref":"FILE_REF","output":"/absolute/new/file.pdf"}` |
| `export` | `{"ref":"DOC_OR_SHEET_REF","output":"/absolute/new/export.pdf","mime_type":"application/pdf"}` |
| `folder-create` | `{"name":"Project files","parent":"OPTIONAL_FOLDER_REF"}` |
| `upload` | `{"path":"/absolute/local/file.pdf","parent":"OPTIONAL_FOLDER_REF","name":"optional filename"}` |
| `update` | `{"ref":"FILE_REF","name":"new name","description":"optional description"}` |
| `move` | `{"ref":"FILE_REF","parent":"DESTINATION_FOLDER_REF"}` |
| `trash` / `restore` | `{"ref":"FILE_REF"}` |

Remote writes require `--request-id STABLE_ID`; `--preview` validates a local plan. Upload preview reads the selected local file to hash its exact contents. Folder omission on creation means the selected account's root. Moving into a shared folder may affect inherited access; inspect the intended destination and the user's requested sharing context first. Direct sharing, permission changes, ownership transfer, and permanent deletion have no commands.

Drive query syntax is not Gmail syntax. Use `mimeType = 'application/vnd.google-apps.document'` for Docs, `application/vnd.google-apps.spreadsheet` for Sheets, `application/vnd.google-apps.folder` for folders, and `'FOLDER_ID' in parents` for children. `search` accepts optional `order_by`, and `--limit` 1–25 / `--cursor`. Keep the exact query when paging. Full Drive permission permits discovery across accessible files; each write still targets a selected ref.

Docs/Sheets results already have typed refs for those service commands. Exports support PDF, plain text, CSV, DOCX and XLSX MIME types where Google supports the file conversion. Downloads/uploads are capped at 25 MB; downloads create a new owner-only path, report a hash, and never execute the file. Native Google files use export. No bulk mailbox or Drive sync runs.
