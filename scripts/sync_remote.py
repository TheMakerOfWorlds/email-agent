#!/usr/bin/env python3
"""Deploy this plugin to one explicitly configured Mac over verified SSH."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import sys

from email_agent import Mail
from gmail_backend import OAuth, exact_scopes
from mail_errors import MailError


ROOT = Path(__file__).resolve().parents[1]


def source_snapshot():
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise MailError("Commit the reviewed source changes before remote deployment.")
    files = {}
    for row in subprocess.check_output(["git", "ls-tree", "-rz", "HEAD"], cwd=ROOT).split(b"\0"):
        if not row:
            continue
        metadata, name = row.split(b"\t", 1)
        mode, kind, blob = metadata.decode().split()
        if kind != "blob" or mode not in ("100644", "100755"):
            raise MailError("Remote deployment accepts regular tracked files only.")
        raw = subprocess.check_output(["git", "cat-file", "blob", blob], cwd=ROOT)
        files[name.decode()] = base64.b64encode(raw).decode()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    return files, revision


def credential_snapshot(accounts, auth):
    """Read only records derived from the configured mailboxes; never enumerate Keychain."""
    records = {}
    for account in accounts:
        client = auth.client(account)
        client_key = "client." + account.get("client", "default")
        key = auth.token_key(account, client)
        token = auth.store.get(key)
        if not token or token.get("email") != account["email"] or token.get("client_id") != client["client_id"]:
            raise MailError("A configured mailbox has no matching credential to copy.")
        exact_scopes(token.get("scopes"))
        records[client_key], records[key] = client, token
    return records


def ledger_snapshot(home):
    path = home / "sends.sqlite3"
    if not path.exists():
        return []
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT id,digest,result FROM sends").fetchall()
    if len(rows) > 50000:
        raise MailError("Send history is too large for this setup transfer.")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="SSH alias for the user's destination Mac; saved after success.")
    parser.add_argument("--computer-name", help="Expected macOS computer name, verified before transfer.")
    parser.add_argument("--remote-home", help="Expected remote account home, verified before transfer.")
    parser.add_argument("--copy-credentials", action="store_true", help="Also copy only this plugin's configured Gmail grants to remote Keychain.")
    args = parser.parse_args()
    try:
        mail = Mail()
        target_path = mail.home / "remote.json"
        target = json.loads(target_path.read_text()) if target_path.exists() else {}
        for key, value in (("host", args.host), ("computer_name", args.computer_name), ("home", args.remote_home)):
            if value:
                target[key] = value
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,200}", target.get("host", ""))
                or not target.get("computer_name") or not target.get("home", "").startswith("/Users/")):
            raise MailError("First deployment requires --host, --computer-name, and --remote-home for the intended Mac.")
        ssh = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10", target["host"]]
        probe = "import json,os,subprocess; print(json.dumps({'home':os.path.expanduser('~'),'computer_name':subprocess.check_output(['/usr/sbin/scutil','--get','ComputerName'],text=True).strip()}))"
        check = subprocess.run(ssh + ["python3 -c " + shlex.quote(probe)], capture_output=True, text=True, timeout=25)
        if check.returncode:
            raise MailError("Cannot verify the configured remote Mac over pinned SSH. No credentials were transferred.")
        identity = json.loads(check.stdout)
        if any(identity.get(k) != target[k] for k in ("home", "computer_name")):
            raise MailError("Remote computer/account identity mismatch. No credentials were transferred.")
        files, revision = source_snapshot()
        accounts = json.loads(mail.config.read_text())
        payload = {"target": target, "revision": revision, "files": files, "accounts": accounts,
                   "ledger": ledger_snapshot(mail.home), "credentials": {}}
        if args.copy_credentials:
            payload["credentials"] = credential_snapshot(list(mail.accounts.values()), OAuth())
        # The bootstrap is public source code. Sensitive payload bytes only enter SSH stdin.
        receiver = (ROOT / "scripts" / "remote_session.py").read_text()
        outcome = subprocess.run(ssh + ["python3 -c " + shlex.quote(receiver)],
                                 input=json.dumps(payload).encode(), capture_output=True, timeout=400)
        try:
            report = json.loads(outcome.stdout)
        except ValueError:
            raise MailError("Remote setup returned no safe status; inspect connectivity and retry the same deployment.") from None
        if outcome.returncode or report.get("status") != "ready":
            # Only the receiver's fixed phase/error labels are safe to expose.
            phase = report.get("phase", "unknown")
            if not re.fullmatch(r"[a-z_]{1,40}", str(phase)):
                phase = "unknown"
            raise MailError("Remote setup failed during " + phase + "; partial progress remains. Retry after resolving that phase.")
        mail.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp = target_path.with_suffix(".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as out:
            json.dump(target, out, indent=2)
            out.write("\n")
        os.replace(temp, target_path)
        print(json.dumps(report, separators=(",", ":")))
        return 0
    except (MailError, OSError, ValueError, subprocess.SubprocessError):
        # Do not print subprocess output, payloads, or exception reprs containing secrets.
        error = sys.exc_info()[1]
        print(json.dumps({"error": str(error) if isinstance(error, MailError) else "Remote setup failed before a verified result; no secret values were logged."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
