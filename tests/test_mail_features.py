import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from email_agent import Mail
from gmail_backend import SCOPES, CLEANUP_SCOPE
from mail_errors import MailError
from mail_features import filter_rule


class Backend:
    def __init__(self):
        self.scopes = SCOPES
        self.mailbox = None
        self.calls = []
        self.states = {"m1": {"INBOX", "UNREAD"}, "m2": {"INBOX", "STARRED"}}
        self.label_rows = [{"id": "Label_1", "name": "Invoices", "type": "user"}]
        self.rules = []
    def profile(self, a):
        self.calls.append("profile")
        return {"emailAddress": self.mailbox or a["email"]}
    def permissions(self, a):
        return self.scopes
    def require_cleanup(self, a):
        if CLEANUP_SCOPE not in self.scopes:
            raise MailError("No modify access")
    def labels(self, a):
        self.calls.append("labels")
        return copy.deepcopy(self.label_rows)
    def message_labels(self, a, mid):
        return set(self.states[mid])
    def modify_labels(self, a, mid, add, remove):
        self.calls.append("modify")
        self.states[mid].update(add); self.states[mid].difference_update(remove)
    def create_label(self, a, name):
        self.calls.append("create_label")
        self.label_rows.append({"id": "Label_2", "name": name, "type": "user"})
    def filters(self, a):
        self.calls.append("filters")
        if "https://www.googleapis.com/auth/gmail.settings.basic" not in self.scopes:
            raise MailError("No settings access")
        return copy.deepcopy(self.rules)
    def create_filter(self, a, rule):
        self.calls.append("create_filter")
        self.rules.append({"id": "f1", **copy.deepcopy(rule)})
    def delete_filter(self, a, ident):
        self.calls.append("delete_filter")
        self.rules = [r for r in self.rules if r["id"] != ident]
    def attachment(self, a, mid, part, maximum):
        self.calls.append("attachment")
        return b"invoice bytes", "../../unsafe.pdf", "application/pdf"


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home / "accounts.json").write_text(json.dumps({"accounts": [
            {"id": "acme", "email": "me@acme.example"}, {"id": "personal", "email": "me@example.com"}]}))
        self.backend = Backend(); self.m = Mail(self.home, self.backend)
        self.a = self.m.account("acme")
        self.refs = [self.m.reference(self.a, mid) for mid in ("m1", "m2")]
        self.rule = {"criteria": {"from": "vendor@example.com", "hasAttachment": True, "query": "filename:pdf"},
                     "action": {"addLabelIds": ["Label_1"], "removeLabelIds": ["INBOX"]}}

    def test_all_previews_stay_local(self):
        self.m.organize("acme", self.refs, ["STARRED"], ["UNREAD"], preview=True)
        self.m.new_label("acme", "Review", preview=True)
        self.m.new_filter("acme", self.rule, preview=True)
        self.m.remove_filter("acme", self.m.filter_ref(self.a, "f1"), preview=True)
        self.assertEqual(self.backend.calls, [])

    def test_organization_restores_only_its_own_changes(self):
        before = copy.deepcopy(self.backend.states)
        r = self.m.organize("acme", self.refs, ["STARRED", "Label_1"], ["INBOX", "UNREAD"])
        self.assertEqual(r["status"], "complete")
        for row in r["messages"]:
            self.m.organize("acme", [row["ref"]], row["undo"]["add"], row["undo"]["remove"])
        self.assertEqual(self.backend.states, before)

    def test_organization_retry_does_not_write_twice(self):
        self.m.organize("acme", self.refs, [], ["INBOX"])
        count = self.backend.calls.count("modify")
        r = self.m.organize("acme", self.refs, [], ["INBOX"])
        self.assertEqual(self.backend.calls.count("modify"), count)
        self.assertTrue(all(x["status"] == "unchanged" for x in r["messages"]))

    def test_organization_rejects_cross_account_unknown_labels_conflicts_and_drafts(self):
        other = self.m.reference(self.m.account("personal"), "m1")
        for refs, add, remove in (([other], ["STARRED"], []), (self.refs, ["Label_missing"], []),
                                  (self.refs, ["SENT"], []), (self.refs, ["TRASH"], []), (self.refs, ["INBOX"], ["INBOX"])):
            with self.assertRaises(MailError): self.m.organize("acme", refs, add, remove)
        self.backend.states["m2"].add("DRAFT")
        with self.assertRaises(MailError): self.m.organize("acme", self.refs, [], ["INBOX"])
        self.assertNotIn("modify", self.backend.calls)

    def test_organization_post_timeout_verifies_before_continuing(self):
        original = self.backend.modify_labels
        def timeout(*args):
            original(*args); raise MailError("Timeout")
        with patch.object(self.backend, "modify_labels", side_effect=timeout):
            r = self.m.organize("acme", self.refs, [], ["INBOX"])
        self.assertEqual(r["status"], "complete")
        self.assertEqual(self.backend.calls.count("modify"), 2)
        self.assertTrue(all(x["status"] == "verified_after_error" for x in r["messages"]))

    def test_organization_uncertainty_stops_remaining_batch(self):
        with patch.object(self.backend, "message_labels", side_effect=[set(), set(), set(), MailError("Offline")]), \
                patch.object(self.backend, "modify_labels", side_effect=MailError("Timeout")) as mutate:
            r = self.m.organize("acme", self.refs, ["STARRED"], [])
        self.assertEqual([x["status"] for x in r["messages"]], ["uncertain", "not_attempted"])
        mutate.assert_called_once()

    def test_filter_validation_normalizes_and_preserves_full_search(self):
        value = {"criteria": {"query": "{from:one@example.com from:two@example.com} -has:userlabels", "size": 10000,
                              "sizeComparison": "larger", "excludeChats": False},
                 "action": {"addLabelIds": ["STARRED", "STARRED"], "removeLabelIds": []}}
        normalized = filter_rule(value)
        self.assertEqual(normalized["criteria"]["query"], value["criteria"]["query"])
        self.assertNotIn("excludeChats", normalized["criteria"])
        self.assertEqual(normalized["action"], {"addLabelIds": ["STARRED"]})

    def test_filter_rejects_unknown_actions_forwarding_empty_criteria_and_bad_sizes(self):
        for rule in ({"criteria": {}, "action": {"addLabelIds": ["STARRED"]}},
                     {"criteria": {"query": "x"}, "action": {"forward": "other@example.com"}},
                     {"criteria": {"query": "x", "unknown": "x"}, "action": {}},
                     {"criteria": {"size": True, "sizeComparison": "larger"}, "action": {"addLabelIds": ["STARRED"]}},
                     {"criteria": {"size": 2}, "action": {"addLabelIds": ["STARRED"]}}):
            with self.assertRaises(MailError): filter_rule(rule)

    def test_filter_creation_is_account_bound_and_idempotent(self):
        first = self.m.new_filter("acme", self.rule, "create-filter-001")
        self.assertEqual(first["status"], "created")
        self.assertEqual(self.m.new_filter("acme", self.rule, "create-filter-001"), first)
        self.assertEqual(self.m.operation_status("create-filter-001"), first)
        self.assertEqual(self.m.new_filter("acme", self.rule, "create-filter-002")["status"], "exists")
        with self.assertRaises(MailError): self.m.new_filter("personal", self.rule, "create-filter-001")
        self.assertEqual(self.backend.calls.count("create_filter"), 1)
        self.assertEqual((self.home / "operations.sqlite3").stat().st_mode & 0o777, 0o600)

    def test_filter_creation_timeout_is_verified_without_duplicate(self):
        original = self.backend.create_filter
        def timeout(*args):
            original(*args); raise MailError("Timeout")
        with patch.object(self.backend, "create_filter", side_effect=timeout):
            r = self.m.new_filter("acme", self.rule, "create-filter-001")
        self.assertEqual(r["status"], "verified_after_error")
        self.assertEqual(self.backend.calls.count("create_filter"), 1)

    def test_uncertain_creation_is_never_blindly_retried(self):
        with patch.object(self.backend, "create_filter", side_effect=MailError("Timeout")) as create:
            r = self.m.new_filter("acme", self.rule, "create-filter-001")
            self.assertEqual(r["status"], "uncertain")
            self.assertEqual(self.m.new_filter("acme", self.rule, "create-filter-001"), r)
            create.assert_called_once()

    def test_concurrent_creation_reserves_request_before_writing(self):
        started, resume = threading.Event(), threading.Event()
        original = self.backend.create_filter
        def wait(*args):
            started.set(); resume.wait(5); original(*args)
        with patch.object(self.backend, "create_filter", side_effect=wait), concurrent.futures.ThreadPoolExecutor(2) as pool:
            one = pool.submit(self.m.new_filter, "acme", self.rule, "create-filter-001")
            self.assertTrue(started.wait(5))
            two = self.m.new_filter("acme", self.rule, "create-filter-001")
            resume.set(); self.assertEqual(one.result()["status"], "created")
        self.assertEqual(two["status"], "pending")
        self.assertEqual(self.backend.calls.count("create_filter"), 1)

    def test_wrong_identity_and_missing_settings_block_filter_writes(self):
        self.backend.mailbox = "wrong@example.com"
        self.assertEqual(self.m.new_filter("acme", self.rule, "create-filter-001")["status"], "not_created")
        self.backend.mailbox = None; self.backend.scopes = {CLEANUP_SCOPE}
        self.assertEqual(self.m.new_filter("acme", self.rule, "create-filter-002")["status"], "not_created")
        self.assertNotIn("create_filter", self.backend.calls)

    def test_filter_delete_backs_up_exact_rule_and_verifies_absence(self):
        self.backend.rules = [{"id": "f1", **self.rule}]
        ref = self.m.filter_ref(self.a, "f1")
        with self.assertRaises(MailError): self.m.remove_filter("personal", ref)
        r = self.m.remove_filter("acme", ref)
        self.assertEqual(r["status"], "deleted")
        path = Path(r["backup"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(path.read_text())["filter"], {"id": "f1", **self.rule})
        self.assertEqual(self.m.remove_filter("acme", ref)["status"], "absent")
        self.assertEqual(self.backend.calls.count("delete_filter"), 1)

    def test_lists_are_filtered_and_paginated(self):
        self.backend.rules = [{"id": "f" + str(i), **self.rule} for i in range(30)]
        r = self.m.list_filters("acme", "vendor@", 0, 10)
        self.assertEqual((len(r["filters"]), r["total"], r["next_offset"]), (10, 30, 10))
        self.assertEqual(self.m.list_filters("acme", "absent")["filters"], [])
        self.assertEqual(self.m.list_labels("acme", "invoice")["labels"][0]["id"], "Label_1")

    def test_label_creation_reuses_existing_names(self):
        self.assertEqual(self.m.new_label("acme", "Invoices", "create-label-001")["status"], "exists")
        self.assertEqual(self.m.new_label("acme", "Review", "create-label-002")["status"], "created")
        self.assertEqual(self.backend.calls.count("create_label"), 1)

    def test_download_uses_selected_path_mode_and_exact_bytes(self):
        path = self.home / "chosen.pdf"
        r = self.m.download(self.refs[0], "1", str(path))
        self.assertEqual(path.read_bytes(), b"invoice bytes")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(r["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertTrue(r["untrusted"])
        with self.assertRaises(MailError): self.m.download(self.refs[0], "1", str(path))
        self.assertEqual(path.read_bytes(), b"invoice bytes")

    def test_download_rejects_symlink_relative_paths_and_invalid_part_before_fetch(self):
        target = self.home / "existing"; target.write_text("keep")
        link = self.home / "link"; link.symlink_to(target)
        for path, part in ((str(link), "1"), ("relative.pdf", "1"), (str(self.home / "new"), "../../1")):
            with self.assertRaises(MailError): self.m.download(self.refs[0], part, path)
        self.assertNotIn("attachment", self.backend.calls)
        self.assertEqual(target.read_text(), "keep")

    def test_download_wrong_identity_and_oversize_never_leave_a_file(self):
        path = self.home / "new"
        self.backend.mailbox = "wrong@example.com"
        with self.assertRaises(MailError): self.m.download(self.refs[0], "1", str(path))
        self.backend.mailbox = None
        with self.assertRaises(MailError): self.m.download(self.refs[0], "1", str(path), 2)
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
