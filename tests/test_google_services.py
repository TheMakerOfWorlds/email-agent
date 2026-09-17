import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from google_auth import WorkspaceOAuth, scopes_for, checked_scopes, PREFIX, IDENTITY
from gmail_backend import OAuth, SCOPES
from google_core import Workspace, compact, save_download
from google_services import calendar, contacts, docs, drive, meet, sheets
from mail_errors import MailError
import google_transport


class MemoryStore:
    def __init__(self): self.data = {}
    def get(self, key): return copy.deepcopy(self.data.get(key))
    def put(self, key, value): self.data[key] = copy.deepcopy(value)


class Auth:
    def require(self, account, service): return "synthetic-token"


class ServicesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        (self.home/"accounts.json").write_text(json.dumps({"accounts": [
            {"id":"acme","email":"you@acme.example","purpose":"Acme only"},
            {"id":"personal","email":"you@personal.example","purpose":"Personal only"}]}))
        self.calls = []
        self.responses = []
        def transport(service, path, token, **kw):
            self.calls.append((service,path,kw))
            if not self.responses: raise AssertionError("Unexpected provider call")
            response = self.responses.pop(0)
            if isinstance(response,Exception): raise response
            return copy.deepcopy(response)
        self.w = Workspace("acme", home=self.home, auth=Auth(), transport=transport)

    def tearDown(self): self.temp.cleanup()

    def test_wrong_account_and_kind_refs_blocked_before_provider(self):
        other=Workspace("personal",home=self.home,auth=Auth())
        for ref, kind in ((other.ref("doc","a"),"doc"),(self.w.ref("file","a"),"doc")):
            with self.assertRaises(MailError): self.w.resolve(ref,kind)
        self.assertEqual([],self.calls)

    def test_ref_survives_only_same_client(self):
        ref=self.w.ref("sheet","abc")
        self.w.account["workspace_client"]="other"
        with self.assertRaises(MailError): self.w.resolve(ref,"sheet")

    def test_receipt_replay_does_not_call_twice(self):
        count=[]
        def create(): count.append(1); return {"id":"one"}
        first=self.w.write("meet.create",{},"request-001",create)
        second=self.w.write("meet.create",{},"request-001",create)
        self.assertEqual(first,second); self.assertEqual([1],count)
        with self.assertRaises(MailError): self.w.write("meet.create",{"changed":True},"request-001",create)

    def test_uncertain_is_not_retried(self):
        def fail(): raise MailError("synthetic timeout")
        first=self.w.write("sheets.append",{},"request-002",fail)
        self.assertEqual("uncertain",first["status"])
        again=self.w.write("sheets.append",{},"request-002",lambda: self.fail("must not retry"))
        self.assertEqual(first,again)

    def test_status_rejects_other_account(self):
        self.w.write("test",{},"request-003",lambda:{})
        other=Workspace("personal",home=self.home,auth=Auth())
        with self.assertRaises(MailError): other.status("request-003")

    def test_preview_does_not_authenticate_or_create_ledger(self):
        out=meet.run(self.w,"create",{},None,True)
        self.assertEqual("preview",out["status"])
        self.assertFalse((self.home/"google-operations.sqlite3").exists())
        self.assertEqual([],self.calls)

    def test_cursor_cannot_change_account_or_query(self):
        self.responses=[{"nextPageToken":"next","files":[]}]
        out=self.w.page("drive","/files",{"q":"first"})
        self.w.cursor=out["next_cursor"]
        with self.assertRaises(MailError): self.w.page("drive","/files",{"q":"second"})
        self.assertEqual(1,len(self.calls))

    def test_cursor_continues_same_query(self):
        self.responses=[{"nextPageToken":"next","files":[]},{"files":[]}]
        self.w.cursor=self.w.page("drive","/files",{"q":"same"})["next_cursor"]
        self.w.page("drive","/files",{"q":"same"})
        self.assertEqual("next",self.calls[-1][2]["params"]["pageToken"])

    def test_sheet_matrices_not_silently_truncated(self):
        data={"values":[list(range(40)) for _ in range(30)]}
        self.assertEqual(data,compact(data))

    def test_big_results_report_no_partial_matrix(self):
        result=compact({"values":[["x"*40000]]})
        self.assertTrue(result["result_too_large"])
        self.assertNotIn("values",result)

    def test_download_does_not_overwrite_or_follow_symlink(self):
        target=self.home/"file"
        saved=save_download(b"abc",str(target))
        self.assertEqual(3,saved["bytes"])
        self.assertEqual(0o600,target.stat().st_mode&0o777)
        with self.assertRaises(MailError): save_download(b"new",str(target))
        (self.home/"link").symlink_to(target)
        with self.assertRaises(MailError): save_download(b"new",str(self.home/"link"))
        self.assertEqual(b"abc",target.read_bytes())

    def test_drive_empty_parent_never_mutates(self):
        for parent in (None,""):
            with self.assertRaises(MailError): drive.run(self.w,"move",{"ref":self.w.ref("file","one"),"parent":parent},"move-001",False)
        self.assertEqual([],self.calls)

    def test_drive_move_requires_real_folder(self):
        self.responses=[{"id":"folder","mimeType":"application/pdf"}]
        result=drive.run(self.w,"move",{"ref":self.w.ref("file","one"),"parent":self.w.ref("file","folder")},"move-002",False)
        self.assertEqual("uncertain",result["status"])
        self.assertEqual(1,len(self.calls))
        self.assertEqual("GET",self.calls[0][2].get("method","GET"))

    def test_drive_search_returns_typed_refs(self):
        self.responses=[{"files":[{"id":"a","mimeType":"application/vnd.google-apps.document"}]}]
        out=drive.run(self.w,"search",{},None,False)
        self.assertEqual("a",self.w.resolve(out["files"][0]["ref"],"doc"))

    def test_sheet_unbounded_ranges_rejected(self):
        for extent in ("A:A","A1:Z9999","NamedRange","C4:A1"):
            with self.assertRaises(MailError): sheets.bounded_range(extent)
        self.assertEqual(("'Expenses'!A1:F20",6,20),sheets.bounded_range("'Expenses'!A1:F20"))

    def test_sheet_write_and_append_respect_width(self):
        for action in ("write","append"):
            with self.assertRaises(MailError): sheets.run(self.w,action,{"ref":self.w.ref("sheet","one"),"range":"A1:A5","values":[[1,2]]},"sheet-001",False)
        self.assertEqual([],self.calls)

    def test_sheet_defaults_to_raw(self):
        self.responses=[{"updatedRange":"A1"}]
        result=sheets.run(self.w,"write",{"ref":self.w.ref("sheet","one"),"range":"A1","values":[["=UNTRUSTED()"]]},"sheet-002",False)
        self.assertEqual("completed",result["status"])
        self.assertEqual("RAW",self.calls[-1][2]["params"]["valueInputOption"])

    def test_sheet_tab_metadata_paginates(self):
        self.responses=[{"sheets":[{"properties":{"sheetId":i}} for i in range(40)]}]
        out=sheets.run(self.w,"get",{"ref":self.w.ref("sheet","one"),"tabs_offset":25},None,False)
        self.assertEqual(25,out["sheets"][0]["properties"]["sheetId"])
        self.assertEqual(35,out["next_tabs_offset"])

    def document(self, count=1, body="x"*9000, revision="rev1"):
        return {"documentId":"doc","title":"Title","revisionId":revision,"tabs":[
            {"tabProperties":{"tabId":str(i),"title":"Tab"},"documentTab":{"body":{"content":[{"paragraph":{"elements":[{"startIndex":1,"endIndex":len(body)+1,"textRun":{"content":body}}]}}]}}}
            for i in range(count)]}

    def test_docs_chunk_continuation_matches_output(self):
        self.responses=[self.document()]
        out=self.w.envelope(docs.run(self.w,"get",{"ref":self.w.ref("doc","doc")},None,False))["result"]
        self.assertEqual(4000,len(out["body"])); self.assertEqual(4000,out["next_offset"])

    def test_docs_reject_oversized_chunk(self):
        self.responses=[self.document()]
        with self.assertRaises(MailError): docs.run(self.w,"get",{"ref":self.w.ref("doc","doc"),"chars":12000},None,False)

    def test_docs_multi_tab_requires_choice_for_writes(self):
        self.responses=[self.document(count=2)]
        out=docs.run(self.w,"replace",{"ref":self.w.ref("doc","doc"),"find":"old","replacement":"new"},"docs-001",False)
        self.assertEqual("uncertain",out["status"]); self.assertEqual(1,len(self.calls))

    def test_docs_selected_tab_and_revision_sent(self):
        doc=self.document(count=2)
        self.responses=[doc,{"replies":[]},doc]
        out=docs.run(self.w,"replace",{"ref":self.w.ref("doc","doc"),"tab":"1","find":"old","replacement":"new"},"docs-002",False)
        body=self.calls[1][2]["body"]
        self.assertEqual({"tabIds":["1"]},body["requests"][0]["replaceAllText"]["tabsCriteria"])
        self.assertEqual("rev1",body["writeControl"]["requiredRevisionId"])
        self.assertEqual("completed",out["status"])

    def test_docs_format_stale_revision_does_not_write(self):
        self.responses=[self.document(revision="new")]
        out=docs.run(self.w,"format",{"ref":self.w.ref("doc","doc"),"start":1,"end":5,"text_style":{"bold":True},"revision":"old"},"docs-003",False)
        self.assertEqual("uncertain",out["status"]); self.assertEqual(1,len(self.calls))

    def test_docs_tabs_and_structural_runs_are_bounded(self):
        self.responses=[self.document(count=40),self.document(body="hello")]
        out=docs.run(self.w,"get",{"ref":self.w.ref("doc","doc"),"tabs_offset":25},None,False)
        self.assertEqual("25",out["tabs"][0]["id"])
        out=docs.run(self.w,"get",{"ref":self.w.ref("doc","doc"),"structure":True},None,False)
        self.assertEqual({"start":1,"end":6,"text":"hello"},out["runs"][0])

    def event(self):
        return {"summary":"Work","start":{"dateTime":"2026-10-01T10:00:00-07:00"},"end":{"dateTime":"2026-10-01T11:00:00-07:00"}}

    def test_calendar_cannot_default_or_use_foreign_account(self):
        with self.assertRaises(MailError): calendar.run(self.w,"create",{"event":self.event()},"calendar-01",False)
        with self.assertRaises(MailError): calendar.calendar_id(self.w,"somebody@gmail.com")
        self.assertEqual([],self.calls)

    def test_calendar_rejects_naive_times(self):
        event=self.event(); event["start"]["dateTime"]="2026-10-01T10:00:00"
        with self.assertRaises(MailError): calendar.event_body(event,True)

    def test_calendar_guests_need_explicit_notifications(self):
        event=self.event(); event["attendees"]=[{"email":"guest@example.com"}]
        with self.assertRaises(MailError): calendar.run(self.w,"create",{"calendar":"primary","event":event},"calendar-02",False)
        self.assertEqual([],self.calls)

    def test_calendar_update_checks_existing_guests(self):
        self.responses=[{"id":"event","attendees":[{"email":"guest@example.com"}]}]
        ref=self.w.ref("event",json.dumps(["primary","event"],separators=(",",":")))
        out=calendar.run(self.w,"cancel",{"ref":ref},"calendar-03",False)
        self.assertEqual("uncertain",out["status"]); self.assertEqual(1,len(self.calls))

    def test_calendar_meet_has_unique_request_and_explicit_account(self):
        self.responses=[{"id":"event"},{"id":"event","organizer":{"email":"you@acme.example"},"conferenceData":{"createRequest":{"status":{"statusCode":"pending"}}}}]
        out=calendar.run(self.w,"create",{"calendar":"primary","event":self.event(),"meet":True},"calendar-04",False)
        body=self.calls[0][2]["body"]
        self.assertEqual("calendar-04",body["conferenceData"]["createRequest"]["requestId"])
        self.assertEqual(64,len(body["id"]))
        self.assertEqual("completed",out["status"])

    def test_meet_create_sends_no_calendar_invitation(self):
        self.responses=[{"name":"spaces/one"},{"name":"spaces/one","meetingUri":"https://meet.google.com/abc-defg-hij"}]
        out=meet.run(self.w,"create",{},"meeting-01",False)
        self.assertFalse(out["resource"]["invites_sent"])
        self.assertTrue(all(x[0]=="meet" for x in self.calls))

    def test_contacts_update_sends_etag_and_field_mask(self):
        self.responses=[{"etag":"old","metadata":{"sources":[]}}, {"resourceName":"people/one"}, {"resourceName":"people/one","etag":"new"}]
        out=contacts.run(self.w,"update",{"ref":self.w.ref("contact","people/one"),"person":{"phoneNumbers":[{"value":"123"}]}},"contact-01",False)
        self.assertEqual("old",self.calls[1][2]["body"]["etag"])
        self.assertEqual("phoneNumbers",self.calls[1][2]["params"]["updatePersonFields"])
        self.assertEqual("completed",out["status"])


class OAuthTest(unittest.TestCase):
    def setUp(self):
        self.account={"id":"acme","email":"you@acme.example"}
        self.client={"client_id":"synthetic.apps.googleusercontent.com","client_secret":"test-only"}
        self.store=MemoryStore(); self.store.put("workspace.client.workspace",self.client)

    def test_scope_selection_is_service_specific(self):
        self.assertEqual({IDENTITY,PREFIX+"documents"},set(scopes_for(["docs"])))
        all_scopes=set(scopes_for(["calendar","meet","contacts","drive","docs","sheets"]))
        self.assertNotIn(PREFIX+"documents",all_scopes)
        self.assertNotIn(PREFIX+"spreadsheets",all_scopes)
        self.assertFalse(all_scopes & SCOPES)

    def test_unknown_scopes_and_missing_identity_are_rejected(self):
        for scopes in ([IDENTITY,PREFIX+"cloud-platform"],[PREFIX+"drive"],list(SCOPES)):
            with self.assertRaises(MailError): checked_scopes(scopes)

    def test_gmail_grant_namespace_is_unchanged(self):
        self.assertNotEqual(OAuth.token_key(self.account,self.client),WorkspaceOAuth.token_key(self.account,self.client))

    def test_same_actual_client_as_gmail_is_rejected(self):
        self.store.put("client.default",self.client)
        with self.assertRaises(MailError): WorkspaceOAuth(store=self.store).client(self.account)

    def test_workspace_import_cannot_overwrite_same_named_gmail_client(self):
        from gmail_backend import AUTH_URL,TOKEN_URL
        self.store.put("client.acme",{"client_id":"gmail.apps.googleusercontent.com","client_secret":"synthetic-old"})
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"client.json"
            path.write_text(json.dumps({"installed":{**self.client,"auth_uri":AUTH_URL,"token_uri":TOKEN_URL}}))
            auth=WorkspaceOAuth(store=self.store)
            auth.import_client(path,"acme")
            self.assertEqual("gmail.apps.googleusercontent.com",self.store.get("client.acme")["client_id"])
            self.assertEqual(self.client,self.store.get("workspace.client.acme"))
            path.write_text(json.dumps({"installed":{**self.client,"client_id":"another.apps.googleusercontent.com","auth_uri":AUTH_URL,"token_uri":TOKEN_URL}}))
            with self.assertRaises(MailError): auth.import_client(path,"acme")
            self.assertEqual(self.client,self.store.get("workspace.client.acme"))

    def test_pkce_and_offline_scopes_preserved(self):
        from urllib.parse import parse_qs,urlsplit
        auth=WorkspaceOAuth(["contacts"],store=self.store)
        query=parse_qs(urlsplit(auth.authorize_url(self.account,self.client,"http://127.0.0.1:123/callback","state","verifier")).query)
        self.assertEqual(["S256"],query["code_challenge_method"])
        self.assertEqual(["offline"],query["access_type"])
        self.assertEqual(set(scopes_for(["contacts"])),set(query["scope"][0].split()))

    def test_wrong_identity_cannot_replace_saved_grant(self):
        auth=WorkspaceOAuth(["contacts"],store=self.store,transport=lambda *a,**k:{"scope":" ".join(scopes_for(["contacts"])),"access_token":"synthetic","refresh_token":"synthetic-refresh"},
            identity_transport=lambda *a,**k:{"email":"wrong@example.com","verified_email":True})
        with self.assertRaises(MailError): auth.finish(self.account,self.client,"code","redirect","verifier")
        self.assertEqual({"workspace.client.workspace"},set(self.store.data))

    def test_refresh_identity_verified_before_storing(self):
        count=[]
        def identity(*a,**k):
            count.append(1); return {"email":self.account["email"],"verified_email":True}
        auth=WorkspaceOAuth(["contacts"],store=self.store,transport=lambda *a,**k:{"scope":" ".join(scopes_for(["contacts"])),"access_token":"synthetic","refresh_token":"synthetic-refresh"},identity_transport=identity)
        out=auth.finish(self.account,self.client,"code","redirect","verifier")
        self.assertEqual(2,len(count)); self.assertTrue(out["refresh_verified"])
        self.assertIn(auth.token_key(self.account,self.client),self.store.data)

    def test_unverified_email_is_rejected(self):
        auth=WorkspaceOAuth(store=self.store,identity_transport=lambda *a,**k:{"email":self.account["email"],"verified_email":False})
        with self.assertRaises(MailError): auth.identity("synthetic",self.account)


class TransportTest(unittest.TestCase):
    def test_unknown_host_and_traversal_are_blocked(self):
        for service,path in (("external","/files"),("drive","https://example.com"),("drive","/files/../permissions"),("drive","/files?alt=media")):
            with self.assertRaises(MailError): google_transport.request(service,path,"synthetic")

    def test_writes_are_never_automatically_retried_or_error_bodies_exposed(self):
        from urllib.error import HTTPError
        import io
        error=HTTPError("https://www.googleapis.com/drive/v3/files",500,"internal",{},io.BytesIO(b'private-provider-content'))
        with patch.object(google_transport,"build_opener") as opener:
            opener.return_value.open.side_effect=error
            with self.assertRaises(MailError) as caught: google_transport.request("drive","/files","synthetic",method="POST",body={"name":"test"})
            self.assertEqual(1,opener.return_value.open.call_count)
            self.assertNotIn("private-provider-content",str(caught.exception))

    def test_transient_gets_use_bounded_retries(self):
        from urllib.error import HTTPError
        error=HTTPError("https://www.googleapis.com/drive/v3/files",503,"internal",{},None)
        with patch.object(google_transport,"build_opener") as opener,patch.object(google_transport.time,"sleep"):
            opener.return_value.open.side_effect=error
            with self.assertRaises(MailError): google_transport.request("drive","/files","synthetic")
            self.assertEqual(3,opener.return_value.open.call_count)


if __name__ == "__main__": unittest.main()
