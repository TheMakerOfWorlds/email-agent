#!/usr/bin/env python3
"""Synthetic output-size measurement. Optional dev dependency: tiktoken."""
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import tiktoken

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("email_agent", ROOT / "scripts/email_agent.py")
ea = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ea)
encoding = tiktoken.get_encoding("o200k_base")


def count(value):
    return len(encoding.encode(value if isinstance(value, str) else ea.compact(value)))


body = "Please review the invoice and confirm the delivery date. This paragraph represents ordinary email history.\n" * 200
search = {"messages": [{"id": f"m{i}", "threadId": f"thread{i}", "date": "2026-09-04 10:00",
                       "internalDateIso": "2026-09-04T10:00:00-06:00", "from": "Vendor <vendor@example.com>",
                       "to": "Team <team@example.com>", "cc": "Contact <contact@example.com>",
                       "delivery": {"delivered_to": ["work@example.com"]},
                       "subject": f"Delivery confirmation {i}", "labels": ["INBOX", "UNREAD", "CATEGORY_PRIMARY"]} for i in range(10)],
          "nextPageToken": "next-page-token"}
message = {"headers": {"from": "vendor@example.com", "to": "team@example.com", "cc": "contact@example.com", "subject": "Delivery confirmation"},
           "delivery": {"delivered_to": ["work@example.com"], "x_original_to": ["team@example.com"]},
           "body": body, "message": {"id": "m0", "threadId": "thread0", "labelIds": ["INBOX", "UNREAD"],
                                      "payload": {"mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()}}}}


class Fixture:
    def profile(self, account):
        return {"emailAddress": account["email"]}
    def search(self, account, query, limit, cursor=None):
        return search
    def read(self, account, message_id):
        return message


with tempfile.TemporaryDirectory() as directory:
    (Path(directory) / "accounts.json").write_text(json.dumps({"accounts": [{"id": "work", "email": "work@example.com", "purpose": "Clients"}]}))
    mail = ea.Mail(directory, Fixture())
    small_search = mail.search("work", "is:unread")
    small_read = mail.read(small_search["messages"][0]["ref"])

skill = (ROOT / "skills/email-agent/SKILL.md").read_text()
frontmatter = skill.split("---", 2)[1].strip()
result = {"fixture": "Synthetic 10-message header page and long message; not live email or billing.",
          "tokenizer": "tiktoken/o200k_base", "discovery_metadata_tokens": count(frontmatter),
          "full_skill_tokens": count(skill), "mcp_tool_schemas_added": 0,
          "search": {"unprojected_headers_tokens": count(search), "compact_headers_tokens": count(small_search)},
          "read": {"unprojected_full_message_tokens": count(message), "compact_default_chunk_tokens": count(small_read),
                   "full_body_chars": len(body), "returned_body_chars": len(small_read["body"]),
                   "remainder_available": small_read["next_offset"] is not None}}
for section, before, after in (("search", "unprojected_headers_tokens", "compact_headers_tokens"),
                                ("read", "unprojected_full_message_tokens", "compact_default_chunk_tokens")):
    result[section]["reduction_percent"] = round(100 * (1 - result[section][after] / result[section][before]), 1)
(ROOT / "benchmarks").mkdir(exist_ok=True)
(ROOT / "benchmarks/results.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
