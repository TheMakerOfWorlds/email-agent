"""Explicit-account, explicit-calendar scheduling."""
from datetime import datetime, date
import hashlib
import json

from email_agent import address
from google_core import fields, segment, text
from mail_errors import MailError

EVENT_FIELDS = "id,etag,summary,description,location,start,end,status,organizer,creator,attendees,attendeesOmitted,htmlLink,hangoutLink,conferenceData,recurrence,recurringEventId"


def calendar_id(w, value):
    if value == "primary":
        return "primary"  # Explicit opt-in, never an implicit fallback.
    return w.resolve(value, "calendar")


def event_row(w, cal, row):
    return {**row, "ref": w.ref("event", json.dumps([cal, row["id"]], separators=(",", ":")))}


def event_target(w, ref):
    cal, event = json.loads(w.resolve(ref, "event"))
    return cal, "/calendars/" + segment(cal) + "/events/" + segment(event)


def timestamp(value):
    value = text(value, 100)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise MailError("Calendar timestamps need a UTC offset or Z.")
    return parsed


def event_body(body, create):
    fields(body, {"summary", "description", "location", "start", "end", "attendees", "recurrence", "visibility", "transparency", "reminders"},
           ("summary", "start", "end") if create else ())
    if not body:
        raise MailError("Supply the event fields to change.")
    for key in ("summary", "description", "location"):
        if key in body:
            text(body[key], 20000)
    if ("start" in body) != ("end" in body):
        raise MailError("Supply start and end together.")
    if "start" in body:
        start, end = body["start"], body["end"]
        for point in (start, end):
            fields(point, {"date", "dateTime", "timeZone"})
            if ("date" in point) == ("dateTime" in point):
                raise MailError("Each event endpoint needs either date or offset-qualified dateTime.")
        if "date" in start and "date" in end:
            first, last = date.fromisoformat(start["date"]), date.fromisoformat(end["date"])
        elif "dateTime" in start and "dateTime" in end:
            first, last = timestamp(start["dateTime"]), timestamp(end["dateTime"])
        else:
            raise MailError("Start and end must use the same date/time form.")
        if last <= first:
            raise MailError("Event end must be after start; all-day end dates are exclusive.")
    attendees = body.get("attendees", [])
    if not isinstance(attendees, list) or len(attendees) > 100:
        raise MailError("Select at most 100 intended attendees.")
    for person in attendees:
        fields(person, {"email", "optional", "displayName"}, ("email",))
        address(person["email"])
    return dict(body)


def run(w, action, data, request_id, preview):
    if action == "calendars":
        fields(data, set())
        out = w.page("calendar", "/users/me/calendarList", {"maxResults": w.limit,
            "fields": "nextPageToken,items(id,summary,description,timeZone,primary,accessRole)"})
        out["items"] = [{**r, "ref": w.ref("calendar", r["id"])} for r in out.get("items", [])]
        return out
    if action == "events":
        fields(data, {"calendar", "after", "before", "query"}, ("calendar", "after", "before"))
        if timestamp(data["before"]) <= timestamp(data["after"]):
            raise MailError("Choose an increasing time window.")
        cal = calendar_id(w, data["calendar"])
        out = w.page("calendar", "/calendars/"+segment(cal)+"/events", {"timeMin": data["after"], "timeMax": data["before"],
            "q": data.get("query"), "singleEvents": "true", "orderBy": "startTime", "maxResults": w.limit,
            "fields": "nextPageToken,items("+EVENT_FIELDS+")"})
        out["items"] = [event_row(w, cal, r) for r in out.get("items", [])]
        return out
    if action == "availability":
        fields(data, {"calendars", "after", "before"}, ("calendars", "after", "before"))
        if not isinstance(data["calendars"], list) or not 1 <= len(data["calendars"]) <= 25:
            raise MailError("Choose 1–25 calendar refs from this account.")
        if timestamp(data["before"]) <= timestamp(data["after"]):
            raise MailError("Choose an increasing time window.")
        return w.call("calendar", "/freeBusy", method="POST", body={"timeMin": data["after"], "timeMax": data["before"],
            "items": [{"id": calendar_id(w, x)} for x in data["calendars"]]})
    if action == "get":
        fields(data, {"ref"}, ("ref",))
        cal, path = event_target(w, data["ref"])
        return event_row(w, cal, w.call("calendar", path, params={"fields": EVENT_FIELDS}))
    if action not in ("create", "update", "cancel"):
        raise MailError("Calendar actions: calendars, events, availability, get, create, update, cancel.")
    fields(data, {"calendar", "ref", "event", "meet", "notify"}, ("calendar", "event") if action == "create" else ("ref",))
    if data.get("notify", "none") not in ("all", "externalOnly", "none") or type(data.get("meet", False)) is not bool:
        raise MailError("notify must be all, externalOnly, or none; meet must be boolean.")
    body = event_body(data.get("event", {}), action == "create") if action != "cancel" else {}
    if body.get("attendees") and data.get("notify") != "all":
        raise MailError("Creating/replacing attendees requires explicit notify: all. Review recipients before sending invitations.")
    if action == "create":
        cal = calendar_id(w, data["calendar"])
        path = "/calendars/" + segment(cal) + "/events"
    else:
        cal, path = event_target(w, data["ref"])
        if "calendar" in data:
            raise MailError("An existing event ref already fixes its calendar.")
    plan = {**data, "calendar_id": cal}
    def execute():
        current = w.call("calendar", path) if action != "create" else {}
        if current.get("attendees") and data.get("notify") != "all":
            raise MailError("This event has attendees. Set notify: all explicitly to update/cancel it and notify them.")
        params = {"sendUpdates": data.get("notify", "none"), "conferenceDataVersion": 1}
        if data.get("meet"):
            body["conferenceData"] = {"createRequest": {"requestId": request_id, "conferenceSolutionKey": {"type": "hangoutsMeet"}}}
        if action == "cancel":
            w.call("calendar", path, method="DELETE", params=params, etag=current.get("etag"))
            return {"ref": data["ref"], "status": "cancelled", "attendee_notifications": data.get("notify", "none")}
        if action == "create":
            body["id"] = hashlib.sha256((w.identity_key()+request_id).encode()).hexdigest()
        out = w.call("calendar", path, method="POST" if action == "create" else "PATCH", params=params, body=body, etag=current.get("etag"))
        target = "/calendars/" + segment(cal) + "/events/" + segment(out["id"])
        verified = w.call("calendar", target, params={"fields": EVENT_FIELDS})
        return event_row(w, cal, verified)
    return w.write("calendar."+action, plan, request_id, execute, preview)
