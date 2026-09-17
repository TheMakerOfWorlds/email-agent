import base64
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import remote_install as ri
import sync_remote as sr
from gmail_backend import OAuth, SCOPES, exact_scopes
from google_auth import WorkspaceOAuth, scopes_for


class RemoteSyncTests(unittest.TestCase):
    def files(self):
        return {".codex-plugin/plugin.json": base64.b64encode(b'{"name":"email-agent"}').decode(),
                "scripts/email_agent.py": base64.b64encode(b"pass\n").decode()}

    def test_source_paths_cannot_escape_release(self):
        for name in ("../secret", "/tmp/secret", "scripts/../../secret", "scripts//other", ".git/config"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                ri.checked_files({**self.files(), name: "eA=="})
        self.assertEqual(ri.checked_files(self.files())[0]["scripts/email_agent.py"], b"pass\n")

    def credentials(self):
        a = {"id": "acme", "email": "you@acme.example"}
        client = {"client_id": "example.apps.googleusercontent.com", "client_secret": "synthetic"}
        key = OAuth.token_key(a, client)
        data = {"client.default": client, key: {"email": a["email"], "client_id": client["client_id"],
                                               "refresh_token": "synthetic-refresh", "scopes": list(SCOPES)}}
        return a, key, data

    def test_credentials_accept_only_exact_configured_record_set(self):
        account, key, data = self.credentials()
        self.assertEqual(ri.expected_records([account], data, OAuth, exact_scopes), {"client.default", key})
        data["unrelated.service"] = {"secret": "do not copy"}
        with self.assertRaises(ValueError):
            ri.expected_records([account], data, OAuth, exact_scopes)

    def test_wrong_identity_and_extra_scopes_are_rejected(self):
        account, key, data = self.credentials()
        data[key]["email"] = "someone@else.example"
        with self.assertRaises(ValueError):
            ri.expected_records([account], data, OAuth, exact_scopes)
        data[key]["email"] = account["email"]
        data[key]["scopes"].append("https://www.googleapis.com/auth/drive")
        with self.assertRaises(sr.MailError):
            ri.expected_records([account], data, OAuth, exact_scopes)

    def test_export_reads_only_derived_keys(self):
        account, key, data = self.credentials()
        seen = []
        def get(k):
            seen.append(k)
            return data[k]
        auth = OAuth(store=SimpleNamespace(get=get))
        self.assertEqual(sr.credential_snapshot([account], auth), data)
        self.assertEqual(seen, ["client.default", key])

    def test_history_preserves_remote_outcome_and_rejects_conflicts(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "sends.sqlite3"
            sent = json.dumps({"request_id": "request-001", "status": "sent"})
            pending = json.dumps({"request_id": "request-001", "status": "pending"})
            ri.merge_ledger(p, [["request-001", "a"*64, sent]])
            ri.merge_ledger(p, [["request-001", "a"*64, pending]])
            with self.assertRaises(ValueError):
                ri.merge_ledger(p, [["request-001", "b"*64, pending]])
            with sqlite3.connect(p) as db:
                self.assertEqual(db.execute("SELECT result FROM sends").fetchone()[0], sent)
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_receiver_failure_never_prints_payload(self):
        output = io.StringIO()
        payload = json.dumps({"private_value": "NEVER_LOG_THIS"}).encode()
        with patch.object(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(payload))), patch.object(sys, "stdout", output), patch.object(ri.subprocess, "check_output", return_value="Example Mac"):
            self.assertEqual(ri.main(), 1)
        self.assertEqual(json.loads(output.getvalue()), {"status": "failed", "phase": "input_validation"})
        self.assertNotIn("NEVER_LOG_THIS", output.getvalue())

    def test_wrong_remote_identity_prevents_credential_read_or_transfer(self):
        with tempfile.TemporaryDirectory() as temp:
            mail = SimpleNamespace(home=Path(temp))
            args = ["sync_remote.py", "--host", "remote-mac", "--computer-name", "Expected Mac", "--remote-home", "/Users/admin", "--copy-credentials"]
            probe = SimpleNamespace(returncode=0, stdout=json.dumps({"computer_name":"Other Mac", "home":"/Users/admin"}))
            with patch.object(sys, "argv", args), patch.object(sr, "Mail", return_value=mail), patch.object(sr.subprocess, "run", return_value=probe) as run, patch.object(sr, "credential_snapshot") as collect, patch.object(sys, "stdout", io.StringIO()):
                self.assertEqual(sr.main(), 1)
                collect.assert_not_called()
                self.assertEqual(run.call_count, 1)
                self.assertIn("StrictHostKeyChecking=yes", run.call_args.args[0])

    def test_atomic_notes_are_owner_only(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "accounts.json"
            ri.atomic_json(p, {"accounts": []})
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(temp).iterdir()), [p])

    def workspace_credentials(self):
        account = {"id":"acme","email":"you@acme.example"}
        client = {"client_id":"workspace.apps.googleusercontent.com","client_secret":"synthetic"}
        key = WorkspaceOAuth.token_key(account,client)
        return account,key,{"workspace.client.workspace":client,key:{"email":account["email"],"client_id":client["client_id"],"refresh_token":"synthetic","scopes":scopes_for(["docs"])}}

    def test_workspace_transfer_excludes_other_services_and_unconfigured_accounts(self):
        account,key,data=self.workspace_credentials()
        self.assertEqual(set(data),ri.expected_workspace_records([account],data))
        seen=[]
        def get(name): seen.append(name); return data.get(name)
        out=sr.workspace_credential_snapshot([account],WorkspaceOAuth(store=SimpleNamespace(get=get)))
        self.assertEqual(data,out)
        self.assertEqual(["workspace.client.workspace",key],seen)
        data["unrelated.token"]={"secret":"synthetic"}
        with self.assertRaises(ValueError): ri.expected_workspace_records([account],data)

    def test_workspace_transfer_rejects_orphan_client_and_gmail_scopes(self):
        account,key,data=self.workspace_credentials()
        with self.assertRaises(ValueError): ri.expected_workspace_records([account],{"workspace.client.workspace":data["workspace.client.workspace"]})
        data[key]["scopes"]=list(SCOPES)
        with self.assertRaises(sr.MailError): ri.expected_workspace_records([account],data)

    def test_normal_sync_does_not_collect_workspace_grants(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            config=home/"accounts.json"; config.write_text('{"accounts":[]}')
            mail=SimpleNamespace(home=home,config=config,accounts={})
            args=["sync_remote.py","--host","remote-mac","--computer-name","Expected Mac","--remote-home","/Users/admin"]
            probe=SimpleNamespace(returncode=0,stdout=json.dumps({"computer_name":"Expected Mac","home":"/Users/admin"}))
            ready=SimpleNamespace(returncode=0,stdout=b'{"status":"ready"}')
            with patch.object(sys,"argv",args),patch.object(sr,"Mail",return_value=mail),patch.object(sr,"source_snapshot",return_value=({},"a"*40)),patch.object(sr.subprocess,"run",side_effect=[probe,ready,SimpleNamespace(returncode=0,stdout=b'{"auto_updates":{"enabled":true}}')]),patch.object(sr,"workspace_credential_snapshot") as collect,patch.object(sys,"stdout",io.StringIO()):
                self.assertEqual(0,sr.main()); collect.assert_not_called()

    def test_staged_sync_installs_via_ssh_then_verifies_in_desktop_session(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp); config=home/"accounts.json"; config.write_text('{"accounts":[]}')
            mail=SimpleNamespace(home=home,config=config,accounts={})
            args=["sync_remote.py","--host","remote-mac","--computer-name","Expected Mac","--remote-home","/Users/admin"]
            responses=[SimpleNamespace(returncode=0,stdout=json.dumps({"computer_name":"Expected Mac","home":"/Users/admin"})),
                       SimpleNamespace(returncode=0,stdout=b'{"status":"prepared","version":"v1"}'),
                       SimpleNamespace(returncode=0,stdout=b''),
                       SimpleNamespace(returncode=0,stdout=b'{"installed":[{"name":"email-agent","version":"v1","enabled":true}]}'),
                       SimpleNamespace(returncode=0,stdout=b'{"status":"ready"}'),
                       SimpleNamespace(returncode=0,stdout=b'{"auto_updates":{"enabled":true}}')]
            with patch.object(sys,"argv",args),patch.object(sr,"Mail",return_value=mail),patch.object(sr,"source_snapshot",return_value=({},"a"*40)),patch.object(sr.subprocess,"run",side_effect=responses) as run,patch.object(sys,"stdout",io.StringIO()):
                self.assertEqual(0,sr.main())
                self.assertEqual("codex plugin add email-agent@personal",run.call_args_list[2].args[0][-1])
                payload=json.loads(run.call_args_list[4].kwargs["input"])
                self.assertEqual("verify",payload["stage"])
                self.assertEqual({},payload["workspace_credentials"])
                self.assertIn("install.py --configure-updates",run.call_args_list[5].args[0][-1])


if __name__ == "__main__":
    unittest.main()
