#!/usr/bin/env python3
"""Compact, account-explicit Gmail. Python standard library and macOS Keychain."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from contextlib import contextmanager
from email.utils import parseaddr
from html.parser import HTMLParser


from mail_errors import MailError
from gmail_backend import Gmail, SCOPES


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def text(value, limit):
    value = str(value or "")
    return value if len(value) <= limit else value[:limit] + "…"


def address(value):
    if (not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or not re.fullmatch(r"[^\s<>,;@]+@[^\s<>,;@]+\.[^\s<>,;@]+", value)):
        raise MailError("Use a complete, bare email address.")
    return value


def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise MailError("Cannot read valid JSON from the requested file.") from exc


class HTMLText(HTMLParser):
    """Plain presentation of HTML-only email; never loads remote resources."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3"):
            self.parts.append("\n")
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href.startswith(("https://", "http://", "mailto:")):
                self.parts.append("[" + href + "] ")

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()
        elif not self.hidden and tag in ("p", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def readable_body(data):
    body = data.get("body", "")
    if not isinstance(body, str):
        raise MailError("Unexpected message body.")
    def has_content(part, mime):
        return (part.get("mimeType", "").split(";")[0].lower() == mime and bool(part.get("body", {}).get("data"))) or any(
            has_content(child, mime) for child in part.get("parts", []))
    payload = data.get("message", {}).get("payload", {})
    if data.get("html_only") or (has_content(payload, "text/html") and not has_content(payload, "text/plain")):
        parser = HTMLText()
        parser.feed(body)
        body = re.sub(r"\n[ \t]*\n+", "\n\n", "".join(parser.parts)).strip()
    return body


class Mail:
    def __init__(self, home=None, backend=None):
        self.home = Path(home or os.environ.get("EMAIL_AGENT_HOME", Path.home() / ".config/email-agent"))
        self.config = self.home / "accounts.json"
        self.backend = backend or Gmail()
        payload = load_json(self.config) if self.config.exists() else {"accounts": []}
        if not isinstance(payload, dict) or payload.get("example_only"):
            raise MailError("Account configuration must be a real account directory, not the example.")
        rows = payload.get("accounts")
        if not isinstance(rows, list):
            raise MailError("Account directory must contain an accounts array.")
        self.accounts = {}
        identities = set()
        for row in rows:
            if not isinstance(row, dict) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", str(row.get("id", ""))):
                raise MailError("Account IDs must be short lowercase names, such as work.")
            row = dict(row, email=address(row.get("email")).lower())
            if row.get("provider", "gmail") not in ("gmail", "google_workspace"):
                raise MailError("This adapter supports Gmail and Google Workspace mail only.")
            if not isinstance(row.get("client", "default"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", row.get("client", "default")):
                raise MailError("Invalid OAuth client name.")
            for key in ("purpose", "avoid"):
                if not isinstance(row.get(key, ""), str) or len(row.get(key, "")) > 500:
                    raise MailError("Account purpose and avoid notes must be strings of at most 500 characters.")
            if row["id"] in self.accounts or row["email"] in identities:
                raise MailError("Duplicate account ID or email address.")
            identities.add(row["email"])
            self.accounts[row["id"]] = row

    def account(self, account_id):
        if account_id not in self.accounts:
            raise MailError("Unknown account. Run accounts; configure only intended mailboxes in accounts.json.")
        return self.accounts[account_id]

    def list_accounts(self):
        rows = [{k: a[k] for k in ("id", "email", "purpose", "avoid") if a.get(k)} for a in self.accounts.values()]
        return {"accounts": rows, "authentication": "not_checked", "config": str(self.config)}

    @staticmethod
    def identity_key(account):
        return hashlib.sha256((account["email"] + "\n" + account.get("client", "default")).encode()).hexdigest()[:12]

    def reference(self, account, message_id):
        if not isinstance(message_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", message_id):
            raise MailError("Provider returned an invalid message ID.")
        return f'{account["id"]}:{self.identity_key(account)}:{message_id}'

    def resolve(self, ref):
        parts = ref.split(":")
        if len(parts) != 3:
            raise MailError("Use the complete message ref returned by search or read.")
        account = self.account(parts[0])
        if self.reference(account, parts[2]) != ref:
            raise MailError("Message ref does not match the configured account identity.")
        return account, parts[2]

    def verify(self, account):
        data = self.backend.profile(account)
        if str(data.get("emailAddress", "")).lower() != account["email"]:
            raise MailError("Authenticated mailbox differs from configured address; operation blocked.")
        return {"account": account["id"], "email": account["email"], "authenticated": True, "scopes": sorted(SCOPES)}

    def search(self, account_id, query, limit=10, cursor=None):
        if not query.strip() or len(query) > 2000 or not 1 <= limit <= 25:
            raise MailError("Search needs a query of 1–2000 characters and limit 1–25.")
        account = self.account(account_id)
        self.verify(account)
        data = self.backend.search(account, query, limit, cursor)
        items = data.get("messages")
        if not isinstance(items, list) or len(items) > limit:
            raise MailError("Unexpected search response shape or result count.")
        rows = []
        for item in items:
            rows.append({"ref": self.reference(account, item.get("id")),
                         "date": text(item.get("date"), 50), "from": text(item.get("from"), 160),
                         "subject": text(item.get("subject"), 200),
                         "unread": "UNREAD" in (item.get("labels") or [])})
        return {"account": account_id, "untrusted": True, "messages": rows,
                "next_cursor": data.get("nextPageToken") or None}

    def read(self, ref, offset=0, chars=4000):
        if offset < 0 or not 1 <= chars <= 12000:
            raise MailError("Read needs offset >= 0 and chars 1–12000.")
        account, message_id = self.resolve(ref)
        self.verify(account)
        data = self.backend.read(account, message_id)
        if data.get("message", {}).get("id") != message_id:
            raise MailError("Provider returned a different message.")
        headers = data.get("headers", {})
        body = readable_body(data)
        if not isinstance(body, str) or not isinstance(headers, dict):
            raise MailError("Unexpected message body or headers.")
        end = min(offset + chars, len(body))
        attachments = data.get("attachments") or []
        return {"ref": ref, "untrusted": True,
                **{k: text(headers.get(k), 500) for k in ("from", "to", "cc", "reply_to", "subject", "date") if headers.get(k)},
                "body": body[offset:end], "offset": offset, "total_chars": len(body),
                "next_offset": end if end < len(body) else None,
                "attachments": [{"name": text(a.get("filename"), 200), "size": a.get("size")} for a in attachments[:20]],
                "attachment_count": len(attachments)}

    def prepare(self, account_id, message):
        account = self.account(account_id)
        allowed = {"to", "cc", "bcc", "subject", "body", "reply_to", "attachments"}
        if not isinstance(message, dict) or set(message) - allowed:
            raise MailError("Message fields: to, cc, bcc, subject, body, reply_to, attachments. From is fixed by account.")
        result = {}
        for key in ("to", "cc", "bcc"):
            rows = message.get(key, [])
            if not isinstance(rows, list) or len(rows) > 50:
                raise MailError("Recipients must be arrays of at most 50 bare email addresses.")
            result[key] = [address(v) for v in rows]
        if not result["to"]:
            raise MailError("At least one explicit To recipient is required.")
        subject, body = message.get("subject"), message.get("body")
        if not isinstance(subject, str) or not subject.strip() or len(subject) > 998 or any(c in subject for c in "\r\n\0"):
            raise MailError("Subject must be one nonempty line, at most 998 characters.")
        if not isinstance(body, str) or not body.strip() or len(body) > 200000:
            raise MailError("Body must contain 1–200000 characters.")
        result.update(subject=subject, body=body)
        if message.get("reply_to"):
            other, _ = self.resolve(message["reply_to"])
            if other["id"] != account_id:
                raise MailError("Reply belongs to another account; sending is blocked.")
            result["reply_to"] = message["reply_to"]
        files = message.get("attachments", [])
        if not isinstance(files, list) or len(files) > 10:
            raise MailError("At most 10 attachment paths are supported.")
        result["attachments"] = []
        total = 0
        for name in files:
            if not isinstance(name, str):
                raise MailError("Attachment paths must be strings.")
            path = Path(name).expanduser().resolve()
            if not path.is_file():
                raise MailError("Attachment file is missing.")
            total += path.stat().st_size
            if total > 18_000_000:
                raise MailError("Attachments exceed this wrapper's 18 MB total limit.")
            result["attachments"].append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        return account, result

    @contextmanager
    def ledger(self):
        self.home.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self.home / "sends.sqlite3"
        db = sqlite3.connect(path, timeout=10)
        path.chmod(0o600)
        try:
            db.execute("CREATE TABLE IF NOT EXISTS sends (id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL)")
            with db:
                yield db
        finally:
            db.close()

    def status(self, request_id):
        with self.ledger() as db:
            row = db.execute("SELECT result FROM sends WHERE id=?", (request_id,)).fetchone()
        if not row:
            return {"request_id": request_id, "status": "unknown"}
        return json.loads(row[0])

    def send(self, account_id, message, request_id=None, preview=False):
        account, payload = self.prepare(account_id, message)
        if preview:
            return {"status": "preview", "from": account["email"], "to": payload["to"],
                    "cc": payload["cc"], "bcc": payload["bcc"], "subject": payload["subject"],
                    "body_chars": len(payload["body"]), "reply_to": payload.get("reply_to"),
                    "attachments": [Path(a["path"]).name for a in payload["attachments"]]}
        if not request_id or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_id):
            raise MailError("Sending requires a stable request-id of 8–100 letters, digits, underscores, or hyphens.")
        digest = hashlib.sha256(compact([account["email"], account.get("client", "default"), payload]).encode()).hexdigest()
        # Reserve before preflight/provider I/O; concurrent/repeated requests cannot send twice.
        result = {"request_id": request_id, "account": account_id, "status": "pending"}
        with self.ledger() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT digest,result FROM sends WHERE id=?", (request_id,)).fetchone()
            if old:
                if old[0] != digest:
                    raise MailError("request-id was already used for a different message or account.")
                return json.loads(old[1])
            db.execute("INSERT INTO sends VALUES (?,?,?)", (request_id, digest, compact(result)))
        attempted = False
        try:
            self.verify(account)
            prepared = self.backend.prepare_send(account, payload)
            attempted = True
            data = self.backend.send(account, prepared)
            sender = parseaddr(data.get("from", ""))[1].lower()
            if sender != account["email"]:
                raise MailError("Provider's sender result did not match the intended mailbox; inspect Sent mail.")
            result.update(status="sent", sender=sender, ref=self.reference(account, data.get("messageId")))
        except (MailError, OSError) as exc:
            result.update(status="uncertain" if attempted else "not_sent", error=str(exc) if isinstance(exc, MailError) else "Local file error.")
        with self.ledger() as db:
            db.execute("UPDATE sends SET result=? WHERE id=?", (compact(result), request_id))
        return result


def parser():
    p = argparse.ArgumentParser(description="Compact Gmail: accounts, search, read, send, status. Setup: doctor.")
    s = p.add_subparsers(dest="command", required=True)
    s.add_parser("accounts", help="List account purpose notes; no authentication or email access.")
    q = s.add_parser("search", help="Return headers only; Gmail query syntax.")
    q.add_argument("account"); q.add_argument("query")
    q.add_argument("--limit", type=int, default=10); q.add_argument("--cursor")
    q = s.add_parser("read", help="Read a message ref in bounded chunks.")
    q.add_argument("ref"); q.add_argument("--offset", type=int, default=0); q.add_argument("--chars", type=int, default=4000)
    q = s.add_parser("send", help="Send requested mail; JSON file fields: to[], subject, body; optional cc[], bcc[], reply_to ref, attachments[].")
    q.add_argument("account"); q.add_argument("--message", required=True, help="JSON file path, or - for stdin")
    q.add_argument("--request-id"); q.add_argument("--preview", action="store_true", help="Validate and show the plan without provider access.")
    q = s.add_parser("status", help="Look up a send request; pending/uncertain requires inspection, never blind retry.")
    q.add_argument("request_id")
    q = s.add_parser("doctor", help="Verify one configured mailbox identity without reading messages.")
    q.add_argument("account")
    return p


def main():
    args = parser().parse_args()
    try:
        mail = Mail()
        if args.command == "accounts":
            result = mail.list_accounts()
        elif args.command == "search":
            result = mail.search(args.account, args.query, args.limit, args.cursor)
        elif args.command == "read":
            result = mail.read(args.ref, args.offset, args.chars)
        elif args.command == "doctor":
            result = mail.verify(mail.account(args.account))
        elif args.command == "status":
            result = mail.status(args.request_id)
        else:
            message = json.load(sys.stdin) if args.message == "-" else load_json(args.message)
            result = mail.send(args.account, message, args.request_id, args.preview)
        print(compact(result))
        return 1 if result.get("status") in ("uncertain", "pending", "not_sent") else 0
    except (MailError, ValueError, TypeError, AttributeError, sqlite3.Error, OSError) as exc:
        print(compact({"error": str(exc) if isinstance(exc, MailError) else "Invalid input or local storage failure."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
