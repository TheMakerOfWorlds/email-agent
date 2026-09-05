#!/usr/bin/env python3
"""Private-stdin receiver invoked by sync_remote.py; no secrets enter output/files."""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile


def checked_files(files):
    if not isinstance(files, dict) or not 1 <= len(files) <= 200:
        raise ValueError("Invalid source inventory")
    decoded, size = {}, 0
    for name, content in files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or str(path) != name or name.startswith(".git/"):
            raise ValueError("Invalid source path")
        raw = base64.b64decode(content, validate=True)
        size += len(raw)
        if size > 5_000_000:
            raise ValueError("Source too large")
        decoded[name] = raw
    manifest = json.loads(decoded[".codex-plugin/plugin.json"])
    if manifest.get("name") != "email-agent" or "scripts/email_agent.py" not in decoded:
        raise ValueError("Wrong plugin")
    return decoded, manifest


def expected_records(accounts, credentials, auth_class, scope_check):
    expected = set()
    for account in accounts:
        client_key = "client." + account.get("client", "default")
        client = credentials[client_key]
        if not re.fullmatch(r"[A-Za-z0-9_-]+\.apps\.googleusercontent\.com", client.get("client_id", "")):
            raise ValueError("Invalid client identity")
        token_key = auth_class.token_key(account, client)
        token = credentials[token_key]
        if token.get("email") != account["email"] or token.get("client_id") != client["client_id"] or not token.get("refresh_token"):
            raise ValueError("Credential identity mismatch")
        scope_check(token.get("scopes"))
        expected.update((client_key, token_key))
    if set(credentials) != expected:
        raise ValueError("Unrelated credential records rejected")
    return expected


def merge_ledger(path, rows):
    if not isinstance(rows, list) or len(rows) > 50000:
        raise ValueError("Invalid send history")
    with sqlite3.connect(path) as db:
        path.chmod(0o600)
        db.execute("CREATE TABLE IF NOT EXISTS sends (id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL)")
        for request_id, digest, result in rows:
            if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_id) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError("Invalid send record")
            record = json.loads(result)
            if record.get("request_id") != request_id or record.get("status") not in ("pending", "uncertain", "sent", "not_sent"):
                raise ValueError("Invalid send status")
            old = db.execute("SELECT digest FROM sends WHERE id=?", (request_id,)).fetchone()
            if old and old[0] != digest:
                raise ValueError("Conflicting send history")
            # Never downgrade or replace the remote machine's existing outcome.
            db.execute("INSERT OR IGNORE INTO sends VALUES (?,?,?)", (request_id, digest, result))


def atomic_json(path, value):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".email-agent-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(value, out, indent=2)
            out.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main(raw=None):
    phase = "input_validation"
    try:
        raw = sys.stdin.buffer.read(12_000_001) if raw is None else raw
        if len(raw) > 12_000_000:
            raise ValueError("Input too large")
        payload = json.loads(raw)
        h = Path.home()
        computer = subprocess.check_output(["/usr/sbin/scutil", "--get", "ComputerName"], text=True).strip()
        if payload["target"]["home"] != str(h) or payload["target"]["computer_name"] != computer or sys.platform != "darwin":
            raise ValueError("Wrong destination")
        files, manifest = checked_files(payload["files"])
        revision = payload["revision"]
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError("Invalid source revision")
        base = h / ".local/share/email-agent/releases"
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        release = base / revision
        phase = "source_install"
        if release.exists():
            for name, content in files.items():
                if (release / name).is_symlink() or (release / name).read_bytes() != content:
                    raise ValueError("Existing release was changed")
        else:
            stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=base))
            for name, content in files.items():
                dest = stage / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
            stage.rename(release)
        sys.path.insert(0, str(release / "scripts"))
        from email_agent import Mail
        from gmail_backend import Keychain, OAuth, Gmail, exact_scopes
        source = h / "plugins/email-agent"
        if source.exists() or source.is_symlink():
            if not source.is_symlink() or source.resolve().parent != base:
                raise ValueError("Refusing to replace an unmanaged plugin checkout")
        phase = "account_validation"
        config_dir = h / ".config/email-agent"
        config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        config_dir.chmod(0o700)
        config = config_dir / "accounts.json"
        state_path = config_dir / "deployment.json"
        if source.is_symlink() and source.resolve() != release:
            old_state = json.loads(state_path.read_text())
            if source.resolve().name != old_state["revision"]:
                raise ValueError("Remote source changed outside deployment")
            for name, digest in old_state["source_hashes"].items():
                if hashlib.sha256((source / name).read_bytes()).hexdigest() != digest:
                    raise ValueError("Remote source edits must be reconciled first")
        incoming = payload["accounts"]
        with tempfile.TemporaryDirectory(prefix=".validate-", dir=config_dir) as tmp:
            atomic_json(Path(tmp) / "accounts.json", incoming)
            validated = Mail(Path(tmp))
            accounts = list(validated.accounts.values())
        if config.exists():
            previous = json.loads(config.read_text())
            if not state_path.exists() or previous != json.loads(state_path.read_text())["accounts"]:
                if previous != incoming:
                    raise ValueError("Remote account notes changed; reconcile before replacing")
            by_id = {a["id"]: a for a in previous["accounts"]}
            for account in accounts:
                old = by_id.get(account["id"])
                if old and (old["email"].lower(), old.get("client", "default")) != (account["email"], account.get("client", "default")):
                    raise ValueError("Account identity changed")
        phase = "credential_validation"
        credentials = payload.get("credentials", {})
        copied = bool(credentials)
        if credentials:
            expected_records(accounts, credentials, OAuth, exact_scopes)
        keychain = Keychain()
        class TransferStore:
            def get(self, key):
                return credentials[key] if key in credentials else keychain.get(key)
            def put(self, key, value):
                credentials[key] = value
        auth = OAuth(store=TransferStore())
        backend = Gmail(auth=auth)
        verified = []
        for account in accounts:
            profile = backend.profile(account)  # Includes a real refresh using the copied grant.
            if profile.get("emailAddress", "").lower() != account["email"]:
                raise ValueError("Remote Gmail identity mismatch")
            verified.append({"id": account["id"], "email": account["email"], "refresh_verified": True})
        phase = "keychain_storage"
        for key, value in credentials.items():
            keychain.put(key, value)
        phase = "send_history"
        merge_ledger(config_dir / "sends.sqlite3", payload["ledger"])
        atomic_json(config, incoming)
        phase = "marketplace_install"
        marketplace = h / ".agents/plugins/marketplace.json"
        market = json.loads(marketplace.read_text()) if marketplace.exists() else {"name": "personal", "plugins": []}
        if market.get("name") != "personal":
            raise ValueError("Unexpected personal marketplace name")
        entries = [x for x in market.get("plugins", []) if x.get("name") == "email-agent"]
        helpers = h / ".codex/skills/.system/plugin-creator/scripts"
        if not entries:
            with tempfile.TemporaryDirectory(prefix=".scaffold-", dir=config_dir) as tmp:
                subprocess.run([sys.executable, str(helpers / "create_basic_plugin.py"), "email-agent", "--path", tmp, "--with-marketplace"],
                               check=True, capture_output=True, timeout=30)
        elif len(entries) != 1 or entries[0].get("source") != {"source": "local", "path": "./plugins/email-agent"}:
            raise ValueError("Existing marketplace points elsewhere")
        source.parent.mkdir(parents=True, exist_ok=True)
        link = source.parent / (".email-agent-" + revision)
        if link.is_symlink():
            link.unlink()
        link.symlink_to(release, target_is_directory=True)
        os.replace(link, source)
        codex = shutil.which("codex") or "/opt/homebrew/bin/codex"
        subprocess.run([codex, "plugin", "add", "email-agent@personal"], check=True, capture_output=True, timeout=90)
        phase = "installed_verification"
        installed = json.loads(subprocess.check_output([codex, "plugin", "list", "--marketplace", "personal", "--json"], timeout=30))
        entry = next(x for x in installed["installed"] if x["name"] == "email-agent")
        if not entry["enabled"] or entry["version"] != manifest["version"]:
            raise ValueError("Plugin not enabled at intended version")
        cache = h / ".codex/plugins/cache/personal/email-agent" / manifest["version"]
        for name, content in files.items():
            if (cache / name).read_bytes() != content:
                raise ValueError("Installed source mismatch")
        # Fresh process: prove the installed plugin reads Keychain without the transfer buffer.
        for account in accounts:
            result = subprocess.run([sys.executable, str(cache / "scripts/email_agent.py"), "doctor", account["id"]], capture_output=True, timeout=40)
            if result.returncode:
                raise ValueError("Installed mailbox verification failed")
        probe = '''import json,sys
sys.path.insert(0,sys.argv[1])
from email_agent import Mail
m=Mail(); rows=[]
for a in m.accounts.values():
 s=m.search(a['id'],'in:inbox',1)
 r=m.read(s['messages'][0]['ref']) if s['messages'] else None
 item={'id':a['id'],'cleanup':m.verify(a)['cleanup'],'search_verified':True,'read_verified':r is not None,'read_chars':len(r['body']) if r else 0}
 if a.get('send_as'):
  item['aliases']=[{'id':x['id'],'sendable':x['sendable']} for x in m.list_senders(a['id'])['senders']]
 rows.append(item)
print(json.dumps(rows))
'''
        checks = subprocess.run([sys.executable, "-c", probe, str(cache / "scripts")], capture_output=True, text=True, timeout=90)
        if checks.returncode:
            raise ValueError("Installed read checks failed")
        mail_checks = json.loads(checks.stdout)
        atomic_json(state_path, {"revision": revision, "accounts": incoming,
                                "source_hashes": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}})
        print(json.dumps({"status": "ready", "computer": computer, "source": str(source), "version": manifest["version"],
                          "revision": revision, "enabled": True, "accounts": verified, "credentials_copied": copied,
                          "ledger_records_supplied": len(payload["ledger"]), "mail_checks": mail_checks}))
        return 0
    except Exception:
        print(json.dumps({"status": "failed", "phase": phase}))
        return 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--socket":
        import contextlib
        import io
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(330)
            connection.connect(sys.argv[2])
            with connection.makefile("rb") as stream:
                payload_bytes = stream.read(12_000_001)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(payload_bytes)
            connection.sendall(output.getvalue().encode())
        raise SystemExit(code)
    raise SystemExit(main())
