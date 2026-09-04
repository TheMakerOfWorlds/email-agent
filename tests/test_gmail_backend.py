import base64
from email import message_from_bytes
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gmail_backend as gb
from mail_errors import MailError


class Store:
    def __init__(self):
        self.records = {}
        self.writes = []
    def get(self, key):
        return self.records.get(key)
    def put(self, key, value):
        self.records[key] = value
        self.writes.append(key)


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.client = {"client_id": "123.apps.googleusercontent.com", "client_secret": "CLIENT_SECRET"}
        self.store.records["client.default"] = self.client
        self.account = {"id": "work", "email": "work@example.com"}
        self.auth = gb.OAuth(self.store, self.http)
        self.calls = []
        self.scope = " ".join(sorted(gb.SCOPES))
        self.profile = self.account["email"]

    def http(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/profile"):
            return {"emailAddress": self.profile}
        return {"access_token": "ACCESS_SECRET", "refresh_token": "REFRESH_SECRET", "expires_in": 3600, "scope": self.scope}

    def finish(self):
        return self.auth.finish(self.account, self.client, "CODE", "http://127.0.0.1:1234/callback", "VERIFIER")

    def test_authorization_requests_only_two_scopes_and_offline_pkce(self):
        url = self.auth.authorize_url(self.account, self.client, "http://127.0.0.1:1234/callback", "state", "verifier")
        args = parse_qs(urlsplit(url).query)
        self.assertEqual(set(args["scope"][0].split()), gb.SCOPES)
        self.assertEqual(args["access_type"], ["offline"])
        self.assertEqual(args["include_granted_scopes"], ["false"])
        self.assertEqual(args["login_hint"], [self.account["email"]])
        self.assertEqual(args["code_challenge_method"], ["S256"])
        self.assertNotIn("CLIENT_SECRET", url)
        self.assertNotEqual(args["code_challenge"], ["verifier"])

    def test_excess_or_partial_scopes_never_saved(self):
        for scope in (self.scope + " https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/gmail.readonly", None):
            self.scope = scope
            with self.assertRaises(MailError):
                self.finish()
        self.assertEqual(self.store.writes, [])

    def test_wrong_mailbox_never_saved(self):
        self.profile = "wrong@example.com"
        with self.assertRaises(MailError):
            self.finish()
        self.assertEqual(self.store.writes, [])

    def test_initial_connection_verifies_refresh_and_redacts_tokens(self):
        result = self.finish()
        self.assertTrue(result["refresh_verified"])
        self.assertEqual(len([c for c in self.calls if c[0] == gb.TOKEN_URL]), 2)
        self.assertNotIn("SECRET", json.dumps(result))
        record = self.store.records[self.auth.token_key(self.account, self.client)]
        self.assertNotIn("access_token", record)
        self.assertEqual(record["refresh_token"], "REFRESH_SECRET")

    def test_access_cached_in_memory_and_refresh_scope_checked(self):
        self.finish()
        count = len(self.calls)
        self.auth.access(self.account)
        self.assertEqual(len(self.calls), count)
        self.auth.cache.clear()
        self.scope += " https://www.googleapis.com/auth/drive"
        with self.assertRaises(MailError):
            self.auth.access(self.account)

    def test_account_and_client_bind_credential_key(self):
        self.finish()
        with self.assertRaises(MailError):
            self.auth.access({"id": "personal", "email": "other@example.com"})
        self.store.records["client.default"] = {**self.client, "client_id": "456.apps.googleusercontent.com"}
        with self.assertRaises(MailError):
            self.auth.access(self.account)

    def test_client_import_rejects_foreign_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "client.json"
            path.write_text(json.dumps({"installed": {**self.client, "auth_uri": gb.AUTH_URL, "token_uri": "https://evil.example/token"}}))
            with self.assertRaises(MailError):
                self.auth.import_client(path)
            self.assertEqual(self.store.writes, [])

    def test_callback_rejects_missing_wrong_and_duplicate_state(self):
        for path in ("/callback?code=SECRET", "/callback?state=wrong&code=SECRET",
                     "/callback?state=correct&state=wrong&code=SECRET", "/elsewhere?state=correct&code=SECRET"):
            with self.assertRaises(MailError):
                gb.authorization_response(path, "correct")
        self.assertEqual(gb.authorization_response("/callback?state=correct&code=SECRET", "correct"), {"code": "SECRET"})
        self.assertIn("error", gb.authorization_response("/callback?state=correct&error=access_denied", "correct"))

    def test_keychain_secret_only_uses_stdin_and_is_verified(self):
        value = {"refresh_token": "PRIVATE_SECRET"}
        encoded = base64.b64encode(json.dumps(value).encode()).decode()
        responses = [subprocess.CompletedProcess([], 0, "", ""), subprocess.CompletedProcess([], 0, encoded, "")]
        with patch.object(gb.sys, "platform", "darwin"), patch.object(gb.subprocess, "run", side_effect=responses) as run:
            gb.Keychain().put("test.work", value)
            self.assertNotIn("PRIVATE_SECRET", str(run.call_args_list[0].args))
            self.assertNotIn("-w", run.call_args_list[0].args[0])
            self.assertIn("add-generic-password", run.call_args_list[0].kwargs["input"])
            self.assertTrue(run.call_args_list[0].kwargs["capture_output"])


class GmailTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        class Auth:
            def access(self, account):
                return "TOKEN_SECRET"
        self.gmail = gb.Gmail(Auth(), self.http)
        self.account = {"id": "work", "email": "work@example.com"}
        self.source = {"id": "m1", "threadId": "thread1", "payload": {"mimeType": "text/plain", "body": {"data": gb.b64(b"Hello")},
            "headers": [{"name": "Subject", "value": "Hello"}, {"name": "Message-ID", "value": "<original@example.com>"}]}}

    def http(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/send"):
            return {"id": "sent1", "threadId": "thread1"}
        return self.source

    def payload(self):
        return {"to": ["recipient@example.com"], "cc": [], "bcc": [], "subject": "Hello", "body": "Hi 🎸", "attachments": []}

    def test_plaintext_body_and_attachment_metadata(self):
        result = self.gmail.read(self.account, "m1")
        self.assertEqual(result["body"], "Hello")
        self.assertFalse(result["html_only"])

    def test_html_fallback_ignores_plaintext_attachment(self):
        self.source["payload"] = {"mimeType": "multipart/mixed", "parts": [
            {"mimeType": "text/html", "body": {"data": gb.b64(b"<p>Hi</p>")}},
            {"mimeType": "text/plain", "filename": "note.txt", "body": {"size": 3, "data": gb.b64(b"SECRET")}}]}
        result = self.gmail.read(self.account, "m1")
        self.assertEqual(result["body"], "<p>Hi</p>")
        self.assertTrue(result["html_only"])
        self.assertEqual(result["attachments"], [{"filename": "note.txt", "size": 3}])

    def test_mime_from_unicode_recipients_and_threading(self):
        payload = {**self.payload(), "bcc": ["private@example.com"], "reply_to": "work:identity:m1"}
        prepared = self.gmail.prepare_send(self.account, payload)
        message = message_from_bytes(gb.unb64(prepared["raw"]))
        self.assertEqual(message["From"], self.account["email"])
        self.assertEqual(message["Bcc"], "private@example.com")
        self.assertEqual(message["In-Reply-To"], "<original@example.com>")
        self.assertEqual(prepared["threadId"], "thread1")
        self.assertIn("🎸", message.get_payload(decode=True).decode())
        self.gmail.send(self.account, prepared)
        self.assertNotIn("retry", self.calls[-1][1])

    def test_attachment_changed_before_send_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comma,file.txt"
            path.write_text("before")
            payload = {**self.payload(), "attachments": [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]}
            self.gmail.prepare_send(self.account, payload)
            path.write_text("after")
            with self.assertRaises(MailError):
                self.gmail.prepare_send(self.account, payload)

    def test_external_endpoints_rejected(self):
        with self.assertRaises(MailError):
            gb.http_json("https://evil.example/messages", token="PRIVATE_SECRET")

    def test_get_retries_three_times_with_sanitized_errors(self):
        with patch.object(gb, "build_opener") as opener, patch.object(gb.time, "sleep"):
            opener.return_value.open.side_effect = URLError("PRIVATE_SECRET")
            with self.assertRaises(MailError) as error:
                gb.http_json(gb.API + "/profile", token="PRIVATE_SECRET", retry=True)
            self.assertEqual(opener.return_value.open.call_count, 3)
            self.assertNotIn("PRIVATE_SECRET", str(error.exception))

    def test_send_post_not_retried_on_5xx(self):
        with patch.object(gb, "build_opener") as opener:
            opener.return_value.open.side_effect = HTTPError(gb.API + "/messages/send", 503, "PRIVATE_SECRET", {}, io.BytesIO(b"PRIVATE_SECRET"))
            with self.assertRaises(MailError) as error:
                gb.http_json(gb.API + "/messages/send", token="PRIVATE_SECRET", payload={"raw": "MAIL"}, retry=True)
            self.assertEqual(opener.return_value.open.call_count, 1)
            self.assertNotIn("PRIVATE_SECRET", str(error.exception))


if __name__ == "__main__":
    unittest.main()
