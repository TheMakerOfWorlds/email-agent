"""On-demand mailbox organization, attachments, and saved filters."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3

from mail_errors import MailError


SYSTEM_MUTABLE = frozenset({"INBOX", "UNREAD", "STARRED", "IMPORTANT", "SPAM",
    "CATEGORY_PERSONAL", "CATEGORY_SOCIAL", "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS"})


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def label_changes(add, remove, *, filters=False):
    allowed = SYSTEM_MUTABLE | ({"TRASH"} if filters else set())
    for rows in (add, remove):
        if not isinstance(rows, list) or len(rows) > 100 or any(not isinstance(v, str) or not
                (v in allowed or re.fullmatch(r"Label_[A-Za-z0-9_-]{1,190}", v)) for v in rows):
            raise MailError("Use mutable Gmail system label IDs or Label_ IDs from labels ACCOUNT. Use trash/restore for message deletion.")
    if set(add) & set(remove) or not (add or remove):
        raise MailError("Label changes must be nonempty and cannot add and remove the same label.")
    return sorted(set(add)), sorted(set(remove))


def filter_rule(value):
    if not isinstance(value, dict) or set(value) != {"criteria", "action"}:
        raise MailError("A filter JSON needs exactly criteria and action objects.")
    criteria, action = value["criteria"], value["action"]
    strings = {"from", "to", "subject", "query", "negatedQuery"}
    bools = {"hasAttachment", "excludeChats"}
    if not isinstance(criteria, dict) or set(criteria) - strings - bools - {"size", "sizeComparison"}:
        raise MailError("Unknown filter criteria; see the filter reference.")
    out = {}
    for key, val in criteria.items():
        if key in strings:
            if not isinstance(val, str) or len(val) > 2000 or any(ord(c) < 32 for c in val):
                raise MailError("Filter text must be a single line of at most 2000 characters.")
            if val.strip():
                out[key] = val.strip()
        elif key in bools:
            if type(val) is not bool:
                raise MailError("Filter attachment/chat flags must be booleans.")
            if val:
                out[key] = True
        elif key == "size":
            if type(val) is not int or not 0 <= val <= 2 ** 53 - 1:
                raise MailError("Filter size must be a nonnegative integer.")
            out[key] = val
        else:
            if val not in ("smaller", "larger"):
                raise MailError("Filter sizeComparison must be smaller or larger.")
            out[key] = val
    if ("size" in out) != ("sizeComparison" in out):
        raise MailError("Filter size and sizeComparison must be supplied together.")
    if not out or set(out) <= {"excludeChats"}:
        raise MailError("A saved filter needs explicit matching criteria.")
    if not isinstance(action, dict) or set(action) - {"addLabelIds", "removeLabelIds"}:
        raise MailError("Filter actions support addLabelIds/removeLabelIds. Automatic forwarding is not enabled.")
    add, remove = label_changes(action.get("addLabelIds", []), action.get("removeLabelIds", []), filters=True)
    return {"criteria": out, "action": {k: v for k, v in (("addLabelIds", add), ("removeLabelIds", remove)) if v}}


class MailFeatures:
    def selection(self, account_id, refs):
        account = self.account(account_id)
        if not isinstance(refs, list) or not 1 <= len(refs) <= 25 or any(not isinstance(r, str) for r in refs) or len(set(refs)) != len(refs):
            raise MailError("Select 1–25 unique message refs from one mailbox.")
        ids = []
        for ref in refs:
            source, ident = self.resolve(ref)
            if source["id"] != account_id:
                raise MailError("Selected message belongs to another mailbox; nothing changed.")
            ids.append(ident)
        return account, ids

    def check_labels(self, account, add, remove):
        known = {r["id"] for r in self.backend.labels(account)}
        if any(v.startswith("Label_") and v not in known for v in add + remove):
            raise MailError("A selected custom label does not exist in this mailbox.")

    def organize(self, account_id, refs, add, remove, preview=False):
        account, ids = self.selection(account_id, refs)
        add, remove = label_changes(add, remove)
        if preview:
            return {"status": "preview", "account": account_id, "refs": refs, "add": add, "remove": remove,
                    "permission": "not_checked"}
        self.verify(account)
        self.backend.require_cleanup(account)
        self.check_labels(account, add, remove)
        states = [self.backend.message_labels(account, mid) for mid in ids]
        if any("DRAFT" in s for s in states):
            raise MailError("Organization does not operate on drafts; nothing changed.")
        outcomes, stopped = [], False
        def matches(labels):
            return set(add) <= labels and not set(remove) & labels
        for ref, mid in zip(refs, ids):
            if stopped:
                outcomes.append({"ref": ref, "status": "not_attempted"})
                continue
            attempted, before = False, None
            try:
                before = self.backend.message_labels(account, mid)
                if "DRAFT" in before:
                    raise MailError("Message became a draft.")
                if matches(before):
                    outcomes.append({"ref": ref, "status": "unchanged"})
                    continue
                attempted = True
                self.backend.modify_labels(account, mid, add, remove)
                if not matches(self.backend.message_labels(account, mid)):
                    raise MailError("Gmail did not show the requested labels.")
                status = "organized"
            except (MailError, OSError):
                try:
                    after = self.backend.message_labels(account, mid)
                    status = "verified_after_error" if attempted and matches(after) else "not_changed"
                except (MailError, OSError):
                    status = "uncertain" if attempted else "not_changed"
                stopped = status != "verified_after_error"
            item = {"ref": ref, "status": status}
            if attempted and before is not None:
                item["undo"] = {"add": sorted(set(remove) & before), "remove": sorted(set(add) - before)}
            outcomes.append(item)
        return {"status": "partial" if stopped else "complete", "account": account_id, "messages": outcomes}

    def list_labels(self, account_id, contains="", offset=0, limit=50):
        account = self.account(account_id)
        if offset < 0 or not 1 <= limit <= 100:
            raise MailError("Label listing requires offset >= 0 and limit 1–100.")
        self.verify(account)
        rows = sorted((r for r in self.backend.labels(account) if contains.casefold() in r["name"].casefold()), key=lambda r: r["name"])
        return {"account": account_id, "labels": rows[offset:offset + limit], "total": len(rows),
                "next_offset": offset + limit if offset + limit < len(rows) else None}

    @contextmanager
    def operation_ledger(self):
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.home / "operations.sqlite3"
        db = sqlite3.connect(path, timeout=10)
        path.chmod(0o600)
        try:
            db.execute("CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL)")
            with db:
                yield db
        finally:
            db.close()

    def operation_status(self, request_id):
        with self.operation_ledger() as db:
            row = db.execute("SELECT result FROM operations WHERE id=?", (request_id,)).fetchone()
        return json.loads(row[0]) if row else {"request_id": request_id, "status": "unknown"}

    def create_once(self, account, operation, payload, request_id, find, create):
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_id):
            raise MailError("Creation requires a stable request-id of 8–100 letters, digits, underscores, or hyphens.")
        digest = hashlib.sha256(canonical([account["email"], account.get("client", "default"), operation, payload]).encode()).hexdigest()
        result = {"request_id": request_id, "account": account["id"], "operation": operation, "status": "pending"}
        with self.operation_ledger() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT digest,result FROM operations WHERE id=?", (request_id,)).fetchone()
            if old:
                if old[0] != digest:
                    raise MailError("request-id already belongs to another operation or account.")
                return json.loads(old[1])
            db.execute("INSERT INTO operations VALUES (?,?,?)", (request_id, digest, canonical(result)))
        attempted = False
        try:
            self.verify(account)
            matches = find()
            if matches:
                result.update(status="exists", resource=matches[0])
            else:
                attempted = True
                create()
                matches = find()
                if not matches:
                    raise MailError("Creation result could not be verified.")
                result.update(status="created", resource=matches[0])
        except (MailError, OSError) as exc:
            result["status"] = "uncertain" if attempted else "not_created"
            result["error"] = str(exc) if isinstance(exc, MailError) else "Local operation failed."
            if attempted:
                try:
                    matches = find()
                    if matches:
                        result.update(status="verified_after_error", resource=matches[0])
                        result.pop("error", None)
                except (MailError, OSError):
                    pass
        with self.operation_ledger() as db:
            db.execute("UPDATE operations SET result=? WHERE id=?", (canonical(result), request_id))
        return result

    def new_label(self, account_id, name, request_id=None, preview=False):
        account = self.account(account_id)
        if not isinstance(name, str) or not name.strip() or len(name) > 225 or any(ord(c) < 32 for c in name):
            raise MailError("A label name must be a nonempty single line of at most 225 characters.")
        name = name.strip()
        if preview:
            return {"status": "preview", "account": account_id, "name": name, "permission": "not_checked"}
        return self.create_once(account, "label-create", {"name": name}, request_id,
            lambda: [r for r in self.backend.labels(account) if r["name"] == name], lambda: self.backend.create_label(account, name))

    def filter_ref(self, account, ident):
        if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", ident):
            raise MailError("Invalid Gmail filter ID.")
        return f'{account["id"]}:{self.identity_key(account)}:filter:{ident}'

    def list_filters(self, account_id, contains="", offset=0, limit=20):
        account = self.account(account_id)
        if offset < 0 or not 1 <= limit <= 100:
            raise MailError("Filter listing requires offset >= 0 and limit 1–100.")
        self.verify(account)
        rows = [r for r in self.backend.filters(account) if contains.casefold() in canonical(r).casefold()]
        return {"account": account_id, "untrusted": True,
                "filters": [{"ref": self.filter_ref(account, r["id"]), **{k: r[k] for k in ("criteria", "action") if k in r}} for r in rows[offset:offset + limit]],
                "total": len(rows), "next_offset": offset + limit if offset + limit < len(rows) else None}

    def new_filter(self, account_id, value, request_id=None, preview=False):
        account = self.account(account_id)
        rule = filter_rule(value)
        if preview:
            return {"status": "preview", "account": account_id, **rule, "applies_to": "future_matching_mail", "permission": "not_checked"}
        def find():
            matches = []
            for row in self.backend.filters(account):
                try:
                    same = filter_rule({k: row.get(k, {}) for k in ("criteria", "action")}) == rule
                except MailError:
                    same = False
                if same:
                    matches.append({"ref": self.filter_ref(account, row["id"])})
            return matches
        def create():
            self.check_labels(account, rule["action"].get("addLabelIds", []), rule["action"].get("removeLabelIds", []))
            self.backend.create_filter(account, rule)
        return self.create_once(account, "filter-create", rule, request_id, find, create)

    def remove_filter(self, account_id, ref, preview=False):
        account = self.account(account_id)
        pieces = ref.split(":")
        if len(pieces) != 4 or self.filter_ref(account, pieces[-1]) != ref:
            raise MailError("Use the filter ref from this mailbox; cross-account deletion is blocked.")
        if preview:
            return {"status": "preview", "account": account_id, "ref": ref, "permission": "not_checked"}
        self.verify(account)
        matches = [r for r in self.backend.filters(account) if r["id"] == pieces[-1]]
        if not matches:
            return {"status": "absent", "ref": ref}
        backup = {"account": account_id, "email": account["email"], "ref": ref, "filter": matches[0]}
        folder = self.home / "filter-backups"
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        dest = folder / (hashlib.sha256(ref.encode()).hexdigest() + ".json")
        try:
            fd = os.open(str(dest), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if dest.is_symlink() or json.loads(dest.read_text()) != backup:
                raise MailError("Existing filter backup differs; deletion blocked.")
        else:
            with os.fdopen(fd, "w") as out:
                out.write(canonical(backup))
                out.flush(); os.fsync(out.fileno())
        try:
            self.backend.delete_filter(account, pieces[-1])
        except (MailError, OSError):
            pass
        try:
            present = any(r["id"] == pieces[-1] for r in self.backend.filters(account))
            status = "not_deleted" if present else "deleted"
        except (MailError, OSError):
            status = "uncertain"
        return {"status": status, "account": account_id, "ref": ref, "backup": str(dest), "existing_messages_changed": False}

    def download(self, ref, part, output, max_bytes=25_000_000):
        account, mid = self.resolve(ref)
        if not isinstance(part, str) or not re.fullmatch(r"root|\d+(?:\.\d+)*", part):
            raise MailError("Use the attachment part from read REF.")
        if type(max_bytes) is not int or not 1 <= max_bytes <= 25_000_000:
            raise MailError("Attachment limit must be 1–25000000 bytes.")
        path = Path(output).expanduser()
        if not path.is_absolute() or not path.parent.is_dir() or path.exists() or path.is_symlink():
            raise MailError("Choose a new absolute output filename in an existing directory; files are never overwritten.")
        self.verify(account)
        raw, name, mime = self.backend.attachment(account, mid, part, max_bytes)
        if len(raw) > max_bytes:
            raise MailError("Attachment exceeds the selected download limit.")
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(raw); out.flush(); os.fsync(out.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return {"status": "downloaded", "account": account["id"], "ref": ref, "part": part, "path": str(path),
                "original_name": str(name)[:200], "mime": mime, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "untrusted": True}
