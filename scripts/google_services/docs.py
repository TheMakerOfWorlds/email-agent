"""Bounded document text and targeted edits with revision preconditions."""
from google_core import fields, segment, text
from mail_errors import MailError


def tabs_of(doc):
    result = []
    def visit(tabs):
        for tab in tabs:
            result.append(tab)
            visit(tab.get("childTabs", []))
    visit(doc.get("tabs", []))
    return result


def fetch(w, ident):
    return w.call("docs", "/documents/"+segment(ident), params={"includeTabsContent": "true"})


def content_text(value):
    chunks = []
    def visit(v):
        if isinstance(v, dict):
            if "textRun" in v:
                chunks.append(v["textRun"].get("content", ""))
            else:
                for x in v.values():
                    visit(x)
        elif isinstance(v, list):
            for x in v:
                visit(x)
    visit(value)
    return "".join(chunks)


def selected_tab(doc, tab_id=None):
    tabs = tabs_of(doc)
    if tab_id:
        selected = [t for t in tabs if t["documentTab"]["body"] is not None and t["tabProperties"]["tabId"] == tab_id]
        if not selected:
            raise MailError("Tab is not in the selected document.")
        return selected[0]
    if len(tabs) > 1:
        raise MailError("Document has multiple tabs; get its tab list, then choose tab explicitly.")
    return tabs[0] if tabs else None


def run(w, action, data, request_id, preview):
    if action in ("open", "get"):
        fields(data, {"id", "ref", "tab", "offset", "chars", "tabs_offset", "structure", "runs_offset"}, ("id",) if action == "open" else ("ref",))
        ident = data["id"] if action == "open" else w.resolve(data["ref"], "doc")
        doc = fetch(w, ident)
        tabs = tabs_of(doc)
        rows = [{"id": t["tabProperties"]["tabId"], "title": t["tabProperties"].get("title")} for t in tabs]
        tabs_offset = data.get("tabs_offset", 0)
        if type(tabs_offset) is not int or tabs_offset < 0:
            raise MailError("tabs_offset must be a nonnegative integer.")
        tab_page = rows[tabs_offset:tabs_offset+w.limit]
        next_tab = tabs_offset+w.limit if tabs_offset+w.limit < len(rows) else None
        if len(tabs) > 1 and not data.get("tab"):
            return {"ref": w.ref("doc", ident), "title": doc["title"], "tabs": tab_page, "next_tabs_offset": next_tab, "instruction": "Choose tab to read its bounded content."}
        tab = selected_tab(doc, data.get("tab"))
        body = content_text(tab.get("documentTab", {}) if tab else doc.get("body", {}))
        offset, chars = data.get("offset", 0), data.get("chars", 4000)
        if type(offset) is not int or offset < 0 or type(chars) is not int or not 1 <= chars <= 4000:
            raise MailError("Use offset >= 0 and chars between 1 and 4000.")
        out = {"ref": w.ref("doc", ident), "title": doc["title"], "revision": doc.get("revisionId"), "tabs": tab_page, "next_tabs_offset": next_tab,
                "body": body[offset:offset+chars], "total_chars": len(body), "next_offset": offset+chars if offset+chars < len(body) else None}
        if data.get("structure"):
            runs=[]
            def visit(v):
                if isinstance(v, dict):
                    if "textRun" in v and "startIndex" in v and "endIndex" in v:
                        runs.append({"start":v["startIndex"],"end":v["endIndex"],"text":v["textRun"].get("content","")[:300]})
                    else:
                        for child in v.values(): visit(child)
                elif isinstance(v,list):
                    for child in v: visit(child)
            visit(tab.get("documentTab",{}).get("body",{}) if tab else doc.get("body",{}))
            ro=data.get("runs_offset",0)
            if type(ro) is not int or ro<0:
                raise MailError("runs_offset must be a nonnegative integer.")
            out.update(runs=runs[ro:ro+w.limit],next_runs_offset=ro+w.limit if ro+w.limit<len(runs) else None)
        return out
    if action == "create":
        fields(data, {"title"}, ("title",))
        text(data["title"], 1000)
        def execute():
            out = w.call("docs", "/documents", method="POST", body=data)
            verified = fetch(w, out["documentId"])
            return {"ref": w.ref("doc", out["documentId"]), "title": verified["title"]}
        return w.write("docs.create", data, request_id, execute, preview)
    if action not in ("append", "replace", "format"):
        raise MailError("Docs actions: open, get, create, append, replace, format. Drive search discovers documents.")
    allowed = {"append": {"ref", "tab", "text"}, "replace": {"ref", "tab", "find", "replacement", "match_case"},
               "format": {"ref", "tab", "start", "end", "text_style", "revision"}}[action]
    required = {"append": ("ref", "text"), "replace": ("ref", "find", "replacement"), "format": ("ref", "start", "end", "text_style", "revision")}[action]
    fields(data, allowed, required)
    ident = w.resolve(data["ref"], "doc")
    for key in ("text", "find", "replacement"):
        if key in data:
            text(data[key], 100000)
    if action == "replace" and not data["find"]:
        raise MailError("Replacement search text must not be empty.")
    if action == "format":
        fields(data["text_style"], {"bold", "italic", "underline", "strikethrough", "fontSize", "weightedFontFamily", "foregroundColor", "backgroundColor"})
        if not data["text_style"] or type(data["start"]) is not int or type(data["end"]) is not int or not 1 <= data["start"] < data["end"]:
            raise MailError("Formatting requires a nonempty style and explicit increasing UTF-16 document indexes.")
    def execute():
        doc = fetch(w, ident)
        if action == "format" and doc.get("revisionId") != data["revision"]:
            raise MailError("Document changed since the indexed read; read it again before formatting.")
        tab = selected_tab(doc, data.get("tab"))
        tab_id = tab["tabProperties"]["tabId"] if tab else None
        if action == "append":
            edit = {"insertText": {"text": data["text"], "endOfSegmentLocation": {"tabId": tab_id} if tab_id else {}}}
        elif action == "replace":
            request = {"containsText": {"text": data["find"], "matchCase": data.get("match_case", True)}, "replaceText": data["replacement"]}
            if tab_id:
                request["tabsCriteria"] = {"tabIds": [tab_id]}
            edit = {"replaceAllText": request}
        else:
            extent = {"startIndex": data["start"], "endIndex": data["end"]}
            if tab_id:
                extent["tabId"] = tab_id
            edit = {"updateTextStyle": {"range": extent, "textStyle": data["text_style"], "fields": ",".join(sorted(data["text_style"]))}}
        out = w.call("docs", "/documents/"+segment(ident)+":batchUpdate", method="POST",
                     body={"requests": [edit], "writeControl": {"requiredRevisionId": doc["revisionId"]}})
        verified = fetch(w, ident)
        return {"ref": data["ref"], "title": verified["title"], "revision": verified.get("revisionId"), "replies": out.get("replies", [])}
    return w.write("docs."+action, data, request_id, execute, preview)
