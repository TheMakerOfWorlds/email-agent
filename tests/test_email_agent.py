import concurrent.futures
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

SPEC = importlib.util.spec_from_file_location("email_agent", Path(__file__).resolve().parents[1] / "scripts/email_agent.py")
ea = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ea)


class FakeGmail:
    def __init__(self):
        self.calls = []
        self.profile_email = None
        self.fail_send = False
        self.body = "A useful message.\n" + "Long quoted history.\n" * 1000
        self.send_started = None
        self.send_continue = None

    def profile(self, account):
        self.calls.append((account["email"], ["profile"], None, False))
        return {"emailAddress": self.profile_email or account["email"]}

    def search(self, account, query, limit, cursor=None):
        self.calls.append((account["email"], ["search", query, limit, cursor], None, False))
        return {"messages": [{"id": "m1", "date": "2026-09-04", "from": "sender@example.com",
                "subject": "Hello", "labels": ["UNREAD"], "body": self.body}], "nextPageToken": "next-page"}

    def read(self, account, message_id):
        self.calls.append((account["email"], ["read", message_id], None, False))
        return {"message": {"id": message_id, "payload": {"raw": "OMIT"}}, "body": self.body,
                "headers": {"from": "sender@example.com", "to": account["email"], "subject": "Hello"}}

    def prepare_send(self, account, payload):
        return payload

    def send(self, account, payload):
        self.calls.append((account["email"], ["send"], payload["body"], True))
        if self.send_started:
            self.send_started.set()
            self.send_continue.wait(5)
        if self.fail_send:
            raise ea.MailError("Provider timed out; delivery may be uncertain if sending.")
        return {"from": account["email"], "messageId": "sent1", "threadId": "thread1"}


class EmailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.config = {"accounts": [{"id": "work", "email": "work@example.com", "purpose": "Clients", "avoid": "Family"},
                                     {"id": "personal", "email": "personal@example.com", "purpose": "Family"}]}
        (self.home / "accounts.json").write_text(json.dumps(self.config))
        self.backend = FakeGmail()
        self.mail = ea.Mail(self.home, self.backend)
        self.message = {"to": ["recipient@example.com"], "subject": "A subject", "body": "A message"}

    def writes(self):
        return [c for c in self.backend.calls if c[3]]

    def test_notes_do_not_access_provider(self):
        result = self.mail.list_accounts()
        self.assertEqual(result["accounts"][0]["purpose"], "Clients")
        self.assertEqual(self.backend.calls, [])

    def test_empty_install_is_actionable(self):
        other = ea.Mail(self.home / "empty", self.backend)
        self.assertEqual(other.list_accounts()["accounts"], [])
        with self.assertRaises(ea.MailError):
            other.search("work", "is:unread")
        self.assertEqual(self.backend.calls, [])

    def test_search_projects_headers_and_preserves_cursor(self):
        result = self.mail.search("work", "is:unread", cursor="page2")
        self.assertNotIn("body", result["messages"][0])
        self.assertNotIn("threadId", result["messages"][0])
        self.assertEqual(result["next_cursor"], "next-page")
        self.assertEqual("page2", self.backend.calls[-1][1][-1])
        self.assertTrue(result["messages"][0]["unread"])
        self.assertEqual(len(self.backend.calls), 2)

    def test_search_distinguishes_addressed_alias_from_authenticated_mailbox(self):
        data = {"messages": [{"id": "m1", "to": "team@example.com", "cc": "contact@example.com",
                "delivery": {"delivered_to": ["work@example.com"]}, "labels": ["UNREAD"]}]}
        with patch.object(self.backend, "search", return_value=data):
            result = self.mail.search("work", "to:team@example.com")
        self.assertEqual(result["mailbox"], "work@example.com")
        row = result["messages"][0]
        self.assertEqual(row["to"], "team@example.com")
        self.assertEqual(row["cc"], "contact@example.com")
        self.assertEqual(row["delivery"]["delivered_to"], ["work@example.com"])
        self.assertTrue(result["untrusted"])

    def test_read_exposes_alias_forwarding_and_visible_bcc_without_inference(self):
        ref = self.mail.reference(self.mail.account("work"), "m1")
        data = {"message": {"id": "m1"}, "body": "Hello", "headers": {
            "to": "team@example.com", "cc": "contact@example.com", "bcc": "visible@example.com",
            "sender": "list-owner@example.com", "reply_to": "team@example.com"},
            "delivery": {"delivered_to": ["work@example.com", "forwarder@example.net"],
                         "x_original_to": ["contact@example.com"], "list_id": ["Team <team.example.com>"]}}
        with patch.object(self.backend, "read", return_value=data):
            result = self.mail.read(ref)
        self.assertEqual(result["account"], "work")
        self.assertEqual(result["mailbox"], "work@example.com")
        self.assertEqual(result["to"], "team@example.com")
        self.assertEqual(result["bcc"], "visible@example.com")
        self.assertEqual(result["sender"], "list-owner@example.com")
        self.assertEqual(result["delivery"], data["delivery"])
        self.assertEqual(self.writes(), [])
        data["headers"].pop("bcc")
        with patch.object(self.backend, "read", return_value=data):
            self.assertNotIn("bcc", self.mail.read(ref))

    def test_routing_headers_have_explicit_bounded_output(self):
        data = {"delivered_to": ["🎸" * 700] * 20, "list_id": ["z" * 5000],
                "authorization": ["not a routing header"]}
        for summary, budget in ((False, 3000), (True, 320)):
            result = ea.delivery_context(data, summary=summary)
            self.assertTrue(result.pop("truncated"))
            self.assertNotIn("authorization", result)
            self.assertLessEqual(sum(len(v.rstrip("…")) for values in result.values() for v in values), budget)
        self.assertEqual(ea.delivery_context({}), {})

    def test_profile_mismatch_blocks_read_and_search(self):
        self.backend.profile_email = "wrong@example.com"
        with self.assertRaises(ea.MailError):
            self.mail.search("work", "hello")
        self.assertEqual(len(self.backend.calls), 1)

    def test_long_unicode_body_is_recoverable(self):
        self.backend.body = "🎸ab" * 3000
        ref = self.mail.reference(self.mail.account("work"), "m1")
        pieces, offset = [], 0
        while offset is not None:
            result = self.mail.read(ref, offset, 1000)
            pieces.append(result["body"])
            self.assertLessEqual(len(result["body"]), 1000)
            self.assertNotIn("payload", result)
            offset = result["next_offset"]
        self.assertEqual("".join(pieces), self.backend.body)

    def test_reference_invalid_after_identity_change(self):
        ref = self.mail.reference(self.mail.account("work"), "m1")
        self.mail.accounts["work"]["email"] = "changed@example.com"
        with self.assertRaises(ea.MailError):
            self.mail.read(ref)
        self.assertEqual(self.backend.calls, [])

    def test_html_only_mail_becomes_text_without_loading_links(self):
        raw = '<html><head><style>huge css</style></head><body><p>Hello &amp; welcome</p><script>unwanted script</script><a href="https://example.com/info">Details</a></body></html>'
        result = ea.readable_body({"body": raw, "message": {"payload": {"mimeType": "text/html", "body": {"data": "encoded"}}}})
        self.assertIn("Hello & welcome", result)
        self.assertIn("https://example.com/info", result)
        self.assertNotIn("huge css", result)
        self.assertNotIn("unwanted script", result)
        self.assertNotIn("<html>", result)

    def test_plaintext_markup_is_preserved(self):
        data = {"body": "Use <value> literally", "message": {"payload": {"mimeType": "text/plain", "body": {"data": "encoded"}}}}
        self.assertEqual(ea.readable_body(data), data["body"])

    def test_reply_account_mismatch_never_calls_provider(self):
        ref = self.mail.reference(self.mail.account("personal"), "m1")
        with self.assertRaises(ea.MailError):
            self.mail.send("work", dict(self.message, reply_to=ref), "request-001")
        self.assertEqual(self.backend.calls, [])

    def test_preview_is_local_and_does_not_echo_body(self):
        result = self.mail.send("work", self.message, preview=True)
        self.assertEqual(result["status"], "preview")
        self.assertNotIn("body", result)
        self.assertEqual(self.backend.calls, [])
        self.assertFalse((self.home / "sends.sqlite3").exists())

    def test_successful_send_retry_is_not_sent_again(self):
        first = self.mail.send("work", self.message, "request-001")
        second = self.mail.send("work", self.message, "request-001")
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "sent")
        self.assertEqual(len(self.writes()), 1)
        self.assertNotIn(self.message["body"], self.writes()[0][1])
        self.assertEqual(self.writes()[0][2], self.message["body"])
        self.assertEqual(self.mail.status("request-001"), first)

    def test_reused_request_id_with_different_content_fails(self):
        self.mail.send("work", self.message, "request-001")
        with self.assertRaises(ea.MailError):
            self.mail.send("work", dict(self.message, body="Changed"), "request-001")
        with self.assertRaises(ea.MailError):
            self.mail.send("personal", self.message, "request-001")
        self.assertEqual(len(self.writes()), 1)

    def test_uncertain_send_is_not_retried(self):
        self.backend.fail_send = True
        first = self.mail.send("work", self.message, "request-001")
        self.assertEqual(first["status"], "uncertain")
        self.assertEqual(self.mail.send("work", self.message, "request-001"), first)
        self.assertEqual(len(self.writes()), 1)

    def test_identity_failure_recorded_as_not_sent(self):
        self.backend.profile_email = "wrong@example.com"
        result = self.mail.send("work", self.message, "request-001")
        self.assertEqual(result["status"], "not_sent")
        self.assertEqual(self.writes(), [])

    def test_concurrent_same_request_only_sends_once(self):
        self.backend.send_started = threading.Event()
        self.backend.send_continue = threading.Event()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.mail.send, "work", self.message, "request-001")
            self.assertTrue(self.backend.send_started.wait(3))
            second = pool.submit(self.mail.send, "work", self.message, "request-001")
            result = second.result(timeout=3)
            self.assertEqual(result["status"], "pending")
            self.backend.send_continue.set()
            self.assertEqual(first.result(timeout=3)["status"], "sent")
        self.assertEqual(len(self.writes()), 1)

    def test_custom_from_and_header_injection_rejected(self):
        for change in ({"from": "other@example.com"}, {"subject": "Hi\r\nBcc: other@example.com"},
                       {"to": ["ok@example.com\nBcc:other@example.com"]}, {"to": ["bad\0@example.com"]}):
            with self.assertRaises(ea.MailError):
                self.mail.send("work", dict(self.message, **change), "request-001")
        self.assertEqual(self.backend.calls, [])

    def test_attachment_content_participates_in_request_identity(self):
        path = self.home / "report.txt"
        path.write_text("Version one")
        message = dict(self.message, attachments=[str(path)])
        self.mail.send("work", message, "request-001")
        path.write_text("Version two")
        with self.assertRaises(ea.MailError):
            self.mail.send("work", message, "request-001")
        self.assertEqual(len(self.writes()), 1)

    def test_duplicate_accounts_and_examples_rejected(self):
        for payload in ({"example_only": True, "accounts": []},
                        {"accounts": [self.config["accounts"][0], self.config["accounts"][0]]}):
            (self.home / "accounts.json").write_text(json.dumps(payload))
            with self.assertRaises(ea.MailError):
                ea.Mail(self.home, self.backend)

    def test_search_and_read_budget_limits(self):
        with self.assertRaises(ea.MailError):
            self.mail.search("work", "hello", 26)
        with self.assertRaises(ea.MailError):
            self.mail.read("invalid", chars=12001)
        self.assertEqual(self.backend.calls, [])



if __name__ == "__main__":
    unittest.main()
