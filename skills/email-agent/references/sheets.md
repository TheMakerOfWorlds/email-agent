# Sheets

Use `python3 <plugin-root>/scripts/google_agent.py sheets ACCOUNT ACTION --input FILE`.
Find a spreadsheet with [Drive](drive.md), or open an explicit ID. Check the spreadsheet title and tab names before selecting a range. Keep the company/account and typed sheet ref throughout the task.

| Action | Input JSON |
| --- | --- |
| `open` | `{"id":"SPREADSHEET_ID"}` |
| `get` | `{"ref":"SHEET_REF"}`; returns title, URL and tab properties; follow `next_tabs_offset` using `tabs_offset` |
| `read` | `{"ref":"SHEET_REF","range":"'Expenses'!A1:F20","formulas":false}` |
| `create` | `{"title":"Company expense tracker"}` |
| `write` | `{"ref":"SHEET_REF","range":"Expenses!A2:C2","values":[["2026-10-01","Example",12.5]]}` |
| `append` | `{"ref":"SHEET_REF","range":"Expenses!A1:C100","values":[["2026-10-01","Example",12.5]]}` |
| `clear` | `{"ref":"SHEET_REF","range":"Expenses!A2:C2"}` |
| `add-tab` | `{"ref":"SHEET_REF","title":"October"}` |
| `format` | `{"ref":"SHEET_REF","sheet_id":0,"start_row":0,"end_row":1,"start_column":0,"end_column":3,"cell_format":{"textFormat":{"bold":true}}}` |

Writes require `--request-id STABLE_ID`; optional `--preview` stays local. Ranges must have explicit row/column bounds and at most 2,000 cells. Start with small ranges, and narrow further if output says truncated. Sheet names with spaces need single quotes within the A1 range. Formatting uses zero-based, end-exclusive numeric indexes and the actual sheet ID returned by get, not its position.

Writes default to RAW. Only pass `"interpret":"USER_ENTERED"` when intentionally asking Google to interpret formulas/dates. Untrusted imported strings can be formulas; do not evaluate them merely because they start with `=`. `read` with formulas true returns formulas instead of displayed values.

Append's range locates a logical table; Google inserts rows after its detected end, which can lie beyond the supplied search range. It is not a fixed-cell update. Use write to target exact cells. Read the returned updated range when verifying an append, and never repeat an uncertain append with a new request ID.

Format accepts backgroundColor, textFormat, numberFormat, horizontalAlignment, verticalAlignment, wrapStrategy and borders. Sharing, deleting tabs and arbitrary batch operations are not exposed. Concurrent collaborators can edit sheets; values operations do not provide a document revision precondition, so read current cells before an intended replacement and verify the resulting range.
