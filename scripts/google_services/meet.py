"""Meet spaces and available conference artifacts; scheduling uses Calendar."""
from google_core import fields, segment
from mail_errors import MailError


def named_path(w, ref, kind, prefix):
    name = w.resolve(ref, kind)
    if not name.startswith(prefix+"/") or ".." in name:
        raise MailError("Unexpected Meet resource name.")
    return "/" + "/".join(segment(s) for s in name.split("/"))


def run(w, action, data, request_id, preview):
    if action == "create":
        fields(data, {"access"})
        access = data.get("access", "TRUSTED")
        if access not in ("RESTRICTED", "TRUSTED", "OPEN"):
            raise MailError("Meet access must be RESTRICTED, TRUSTED, or OPEN.")
        def execute():
            row = w.call("meet", "/spaces", method="POST", body={"config": {"accessType": access}})
            verified = w.call("meet", "/"+row["name"])
            return {**verified, "ref": w.ref("space", row["name"]), "invites_sent": False}
        return w.write("meet.create", {"access": access}, request_id, execute, preview)
    if action == "open":
        fields(data, {"code"}, ("code",))
        code = segment(data["code"])
        row = w.call("meet", "/spaces/"+code)
        return {**row, "ref": w.ref("space", row["name"])}
    if action == "get":
        fields(data, {"ref"}, ("ref",))
        row = w.call("meet", named_path(w, data["ref"], "space", "spaces"))
        return {**row, "ref": data["ref"]}
    if action == "records":
        fields(data, {"filter"})
        out = w.page("meet", "/conferenceRecords", {"pageSize": w.limit, "filter": data.get("filter")})
        out["conferenceRecords"] = [{**r, "ref": w.ref("conference", r["name"])} for r in out.get("conferenceRecords", [])]
        return out
    if action in ("participants", "recordings", "transcripts"):
        fields(data, {"ref"}, ("ref",))
        path = named_path(w, data["ref"], "conference", "conferenceRecords") + "/" + action
        out = w.page("meet", path, {"pageSize": w.limit})
        kind = {"participants": "participant", "recordings": "recording", "transcripts": "transcript"}[action]
        out[action] = [{**r, "ref": w.ref(kind, r["name"])} for r in out.get(action, [])]
        return out
    if action == "entries":
        fields(data, {"ref"}, ("ref",))
        return w.page("meet", named_path(w, data["ref"], "transcript", "conferenceRecords")+"/entries", {"pageSize": w.limit})
    raise MailError("Meet actions: create, open, get, records, participants, recordings, transcripts, entries. For invited meetings use calendar create with meet: true.")
