"""Personal contacts in the explicitly selected Google account."""
from google_core import fields, segment, text
from mail_errors import MailError

MASK = "names,emailAddresses,phoneNumbers,organizations,biographies,metadata,addresses,urls"
EDITABLE = {"names", "emailAddresses", "phoneNumbers", "organizations", "biographies", "addresses", "urls"}


def path_for(w, ref):
    name = w.resolve(ref, "contact")
    if not name.startswith("people/") or name.count("/") != 1:
        raise MailError("Invalid contact reference.")
    return "/people/" + segment(name.split("/")[1])


def row(w, person):
    return {**person, "ref": w.ref("contact", person["resourceName"])}


def run(w, action, data, request_id, preview):
    if action == "list":
        fields(data, set())
        out = w.page("contacts", "/people/me/connections", {"pageSize": w.limit, "personFields": MASK, "sortOrder": "LAST_MODIFIED_DESCENDING"})
        out["connections"] = [row(w, r) for r in out.get("connections", [])]
        return out
    if action == "search":
        fields(data, {"query"}, ("query",))
        text(data["query"], 500)
        # Google requires a warm-up request for the search cache.
        w.call("contacts", "/people:searchContacts", params={"query": "", "readMask": MASK})
        out = w.call("contacts", "/people:searchContacts", params={"query": data["query"], "readMask": MASK, "pageSize": w.limit})
        return {"results": [row(w, r["person"]) for r in out.get("results", [])], "search": "prefix; narrow query if capped"}
    if action == "get":
        fields(data, {"ref"}, ("ref",))
        return row(w, w.call("contacts", path_for(w, data["ref"]), params={"personFields": MASK}))
    if action not in ("create", "update", "delete"):
        raise MailError("Contacts actions: list, search, get, create, update, delete.")
    fields(data, {"ref", "person"}, ("person",) if action == "create" else ("ref",))
    person = data.get("person", {})
    fields(person, EDITABLE)
    if action != "delete" and not person:
        raise MailError("Supply at least one contact field.")
    for key, values in person.items():
        if not isinstance(values, list) or len(values) > 25:
            raise MailError("Contact fields must be arrays of at most 25 values.")
    path = path_for(w, data["ref"]) if action != "create" else "/people:createContact"
    def execute():
        current = w.call("contacts", path, params={"personFields": MASK}) if action != "create" else {}
        if action == "delete":
            w.call("contacts", path+":deleteContact", method="DELETE")
            return {"ref": data["ref"], "status": "deleted"}
        body = dict(person)
        params = {"personFields": MASK}
        if action == "update":
            body.update(etag=current["etag"], metadata=current["metadata"])
            params["updatePersonFields"] = ",".join(sorted(person))
        out = w.call("contacts", path + (":updateContact" if action == "update" else ""),
                     method="PATCH" if action == "update" else "POST", params=params, body=body)
        return row(w, w.call("contacts", "/"+out["resourceName"], params={"personFields": MASK}))
    return w.write("contacts."+action, data, request_id, execute, preview)
