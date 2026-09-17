"""Search first; fetch selected files only. No permission/ownership mutation API."""
import hashlib
import json
import mimetypes
from pathlib import Path
import uuid

from google_core import fields, segment, text, save_download
from mail_errors import MailError

FILE_FIELDS = "id,name,mimeType,size,modifiedTime,parents,trashed,webViewLink,owners(displayName,emailAddress),capabilities(canEdit,canTrash,canDownload),description"


def get(w, ident):
    return w.call("drive", "/files/"+segment(ident), params={"fields": FILE_FIELDS, "supportsAllDrives": "true"})


def run(w, action, data, request_id, preview):
    if action == "search":
        fields(data, {"query", "order_by"})
        query = text(data.get("query", "trashed = false"), 2000)
        out = w.page("drive", "/files", {"q": query, "pageSize": w.limit, "orderBy": data.get("order_by", "modifiedTime desc"),
            "fields": "nextPageToken,incompleteSearch,files("+FILE_FIELDS+")", "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
        out["files"] = [w.file_ref(r) for r in out.get("files", [])]
        return out
    if action in ("open", "get"):
        fields(data, {"id"} if action == "open" else {"ref"}, ("id",) if action == "open" else ("ref",))
        ident = data["id"] if action == "open" else w.file_id(data["ref"])
        return w.file_ref(get(w, ident))
    if action in ("download", "export"):
        fields(data, {"ref", "output", "mime_type"}, ("ref", "output"))
        ident = w.file_id(data["ref"])
        metadata = get(w, ident)
        path = "/files/"+segment(ident)
        if action == "export":
            mime = data.get("mime_type", "application/pdf")
            if mime not in ("application/pdf", "text/plain", "text/csv", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
                raise MailError("Choose PDF, text, CSV, DOCX, or XLSX export MIME type.")
            raw = w.call("drive", path+"/export", params={"mimeType": mime}, binary=True)
        else:
            if metadata.get("mimeType", "").startswith("application/vnd.google-apps."):
                raise MailError("Use export for a native Google document.")
            if int(metadata.get("size", 0)) > 25_000_000:
                raise MailError("File exceeds the 25 MB download limit.")
            raw = w.call("drive", path, params={"alt": "media", "supportsAllDrives": "true"}, binary=True)
            if "size" in metadata and len(raw) != int(metadata["size"]):
                raise MailError("Download size differs from metadata; no file saved.")
        return {**save_download(raw, data["output"]), "ref": data["ref"]}
    if action not in ("folder-create", "upload", "update", "move", "trash", "restore"):
        raise MailError("Drive actions: search, open, get, download, export, folder-create, upload, update, move, trash, restore.")
    allowed = {"folder-create": {"name", "parent"}, "upload": {"path", "name", "parent", "mime_type"},
               "update": {"ref", "name", "description"}, "move": {"ref", "parent"}, "trash": {"ref"}, "restore": {"ref"}}[action]
    required = {"folder-create": ("name",), "upload": ("path",), "update": ("ref",), "move": ("ref", "parent"), "trash": ("ref",), "restore": ("ref",)}[action]
    fields(data, allowed, required)
    if action == "move" and (not isinstance(data["parent"], str) or not data["parent"]):
        raise MailError("Move requires a nonempty destination folder ref.")
    ident = w.file_id(data["ref"]) if "ref" in data else None
    parent = w.resolve(data["parent"], "file") if data.get("parent") else None
    for key in ("name", "description"):
        if key in data:
            text(data[key], 10000)
    content = None
    plan = dict(data)
    if action == "upload":
        path = Path(data["path"])
        if not path.is_absolute() or not path.is_file() or path.stat().st_size > 25_000_000:
            raise MailError("Upload needs an existing absolute file path of at most 25 MB.")
        content = path.read_bytes()
        if len(content) > 25_000_000:
            raise MailError("Upload exceeds 25 MB.")
        plan["sha256"] = hashlib.sha256(content).hexdigest()
    if action == "update" and not set(data) & {"name", "description"}:
        raise MailError("Provide a name or description to update.")
    def execute():
        if parent and get(w, parent)["mimeType"] != "application/vnd.google-apps.folder":
            raise MailError("Selected parent is not a folder in this account.")
        params = {"fields": FILE_FIELDS, "supportsAllDrives": "true"}
        if action in ("folder-create", "upload"):
            metadata = {"name": data.get("name", Path(data.get("path", "")).name)}
            if parent:
                metadata["parents"] = [parent]
            if action == "folder-create":
                metadata["mimeType"] = "application/vnd.google-apps.folder"
                out = w.call("drive", "/files", method="POST", params=params, body=metadata)
            else:
                mime = data.get("mime_type") or mimetypes.guess_type(data["path"])[0] or "application/octet-stream"
                if not isinstance(mime, str) or any(c in mime for c in "\r\n"):
                    raise MailError("Invalid upload MIME type.")
                boundary = "email_agent_"+uuid.uuid4().hex
                raw = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
                    + json.dumps(metadata).encode() + f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode()
                    + content + f"\r\n--{boundary}--\r\n".encode())
                out = w.call("upload", "/files", method="POST", params={**params, "uploadType": "multipart"},
                    raw=raw, content_type="multipart/related; boundary="+boundary)
        else:
            current = get(w, ident)
            body = {k: data[k] for k in ("name", "description") if k in data}
            if action in ("trash", "restore"):
                body = {"trashed": action == "trash"}
            if action == "move":
                params.update(addParents=parent, removeParents=",".join(current.get("parents", [])))
            out = w.call("drive", "/files/"+segment(ident), method="PATCH", params=params, body=body)
        return w.file_ref(get(w, out["id"]))
    return w.write("drive."+action, plan, request_id, execute, preview)
