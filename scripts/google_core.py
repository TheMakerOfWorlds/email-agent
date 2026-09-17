"""Shared account identity, bounded results, references, and write receipts."""
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote

from email_agent import Mail
from google_auth import WorkspaceOAuth, SERVICE_SCOPES
from google_transport import request
from mail_errors import MailError


def segment(value):
    if not isinstance(value, str) or not value or len(value) > 2000 or any(ord(c) < 32 for c in value):
        raise MailError("Invalid resource identifier.")
    return quote(value, safe="")


def fields(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or not set(required) <= set(value):
        raise MailError("Invalid input fields. Allowed: " + ", ".join(sorted(allowed)) + "; required: " + ", ".join(required))
    return value


def text(value, maximum=10000):
    if not isinstance(value, str) or len(value) > maximum:
        raise MailError(f"Expected text of at most {maximum} characters.")
    return value


def compact(value):
    """Bound provider data and disclose all truncation, without raw payload output."""
    truncated = []
    def visit(v, path="result", depth=0):
        if path.endswith(".values"):
            return v  # Sheets bounds its matrix; never truncate cells or formulas.
        if depth > 10:
            truncated.append(path)
            return "[nested content omitted]"
        if isinstance(v, str) and len(v) > 4000:
            truncated.append(path)
            return v[:4000]
        if isinstance(v, list):
            return [visit(x, f"{path}[{i}]", depth+1) for i, x in enumerate(v)]
        if isinstance(v, dict):
            return {k: visit(x, path+"."+k, depth+1) for k, x in v.items()}
        return v
    out = visit(value)
    if truncated:
        out = {"data": out, "truncated_fields": truncated}
    if len(json.dumps(out)) > 30000:
        return {"result_too_large": True, "instruction": "Request fewer results or a narrower range.",
                "resource": {k: value[k] for k in ("ref", "id", "name", "spreadsheetId", "documentId") if isinstance(value, dict) and k in value}}
    return out


class Workspace:
    def __init__(self, account_id, *, home=None, auth=None, transport=None, limit=10, cursor=None):
        self.mail = Mail(home)
        self.account = self.mail.account(account_id)
        self.auth = auth or WorkspaceOAuth()
        self.transport = transport or request
        if type(limit) is not int or not 1 <= limit <= 25:
            raise MailError("Use a result limit from 1 to 25.")
        self.limit, self.cursor = limit, cursor
        self.cursor_used = False

    def identity_key(self):
        return hashlib.sha256((self.account["email"]+"\n"+self.account.get("workspace_client", "workspace")).encode()).hexdigest()[:16]

    def ref(self, kind, ident):
        segment(ident)
        payload = base64.urlsafe_b64encode(ident.encode()).decode().rstrip("=")
        return f'g1:{self.account["id"]}:{self.identity_key()}:{kind}:{payload}'

    def resolve(self, ref, kind):
        try:
            prefix, aid, key, actual_kind, encoded = ref.split(":")
            ident = base64.b64decode(encoded + "="*(-len(encoded)%4), altchars=b"-_", validate=True).decode()
        except (AttributeError, ValueError, UnicodeError):
            raise MailError("Use an account-bound resource ref from this service's search/list/open command.") from None
        if prefix != "g1" or aid != self.account["id"] or key != self.identity_key() or actual_kind != kind or self.ref(kind, ident) != ref:
            raise MailError("Resource belongs to another account, client, or service; nothing changed.")
        return ident

    def call(self, service, path, **kwargs):
        permission = "drive" if service == "upload" else service
        token = self.auth.require(self.account, permission)
        return self.transport(service, path, token, **kwargs)

    def page(self, service, path, params=None, body=None):
        params = dict(params or {})
        binding = hashlib.sha256(json.dumps([service, path, params, body], sort_keys=True).encode()).hexdigest()[:20]
        if self.cursor:
            saved = json.loads(self.resolve(self.cursor, "cursor"))
            if saved.get("binding") != binding:
                raise MailError("Cursor belongs to another query. Keep its account, query, and page size unchanged.")
            params["pageToken"] = saved["token"]
            self.cursor_used = True
        out = self.call(service, path, params=params, **({"body": body, "method": "POST"} if body is not None else {}))
        token = out.pop("nextPageToken", None)
        if token:
            out["next_cursor"] = self.ref("cursor", json.dumps({"binding": binding, "token": token}, separators=(",", ":")))
        return out

    def file_ref(self, row):
        kind = {"application/vnd.google-apps.document": "doc", "application/vnd.google-apps.spreadsheet": "sheet"}.get(row.get("mimeType"), "file")
        return {**row, "ref": self.ref(kind, row["id"])}

    def file_id(self, ref):
        for kind in ("file", "doc", "sheet"):
            try:
                return self.resolve(ref, kind)
            except MailError:
                pass
        raise MailError("Use a Drive/Docs/Sheets ref belonging to the selected account.")

    def envelope(self, result):
        return {"account": self.account["id"], "selected_identity": self.account["email"],
                "content_trust": "untrusted", "result": compact(result)}

    @contextmanager
    def ledger(self):
        home = self.mail.home
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = home / "google-operations.sqlite3"
        if path.is_symlink():
            raise MailError("Workspace ledger must not be a symlink.")
        db = sqlite3.connect(path, timeout=10)
        path.chmod(0o600)
        db.execute("CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL)")
        try:
            with db:
                yield db
        finally:
            db.close()

    def status(self, request_id):
        with self.ledger() as db:
            row = db.execute("SELECT result FROM operations WHERE id=?", (request_id,)).fetchone()
        if not row:
            return {"status": "unknown", "request_id": request_id}
        result = json.loads(row[0])
        if result["account"] != self.account["id"] or result["identity"] != self.identity_key():
            raise MailError("Request belongs to another account or OAuth client.")
        return result

    def write(self, operation, plan, request_id, execute, preview=False):
        # Validation and ref resolution happen before this point. Preview does not contact Google.
        if preview:
            return {"status": "preview", "account": self.account["id"], "as": self.account["email"],
                    "operation": operation, "plan": compact(plan), "permission": "not_checked"}
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_id):
            raise MailError("Writes require a stable request-id of 8–100 letters, digits, underscores, or hyphens.")
        digest = hashlib.sha256(json.dumps([self.identity_key(), operation, plan], sort_keys=True).encode()).hexdigest()
        result = {"request_id": request_id, "account": self.account["id"], "identity": self.identity_key(),
                  "operation": operation, "status": "pending"}
        with self.ledger() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT digest,result FROM operations WHERE id=?", (request_id,)).fetchone()
            if row:
                if row[0] != digest:
                    raise MailError("Request ID already belongs to another operation, resource, or account.")
                return json.loads(row[1])
            db.execute("INSERT INTO operations VALUES (?,?,?)", (request_id, digest, json.dumps(result)))
        try:
            result.update(status="completed", resource=compact(execute()))
        except Exception as error:
            # Conservative even if failure was pre-write: do not risk duplicate remote mutations.
            result.update(status="uncertain", error=str(error) if isinstance(error, MailError) else "Operation did not return a verified result.")
        with self.ledger() as db:
            db.execute("UPDATE operations SET result=? WHERE id=?", (json.dumps(result), request_id))
        return result


def save_download(raw, output):
    path = Path(output)
    if not path.is_absolute() or len(raw) > 25_000_000:
        raise MailError("Download needs an absolute new path and at most 25 MB.")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
    except FileExistsError:
        raise MailError("Output already exists; choose a new path.") from None
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
