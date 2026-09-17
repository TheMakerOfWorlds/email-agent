"""Bounded Google Workspace transport; no caller-supplied hosts or redirects."""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from gmail_backend import NoRedirect
from mail_errors import MailError

BASES = {
    "identity": "https://www.googleapis.com/oauth2/v2",
    "calendar": "https://www.googleapis.com/calendar/v3",
    "drive": "https://www.googleapis.com/drive/v3",
    "upload": "https://www.googleapis.com/upload/drive/v3",
    "docs": "https://docs.googleapis.com/v1",
    "sheets": "https://sheets.googleapis.com/v4",
    "contacts": "https://people.googleapis.com/v1",
    "meet": "https://meet.googleapis.com/v2",
}


def request(service, path, token, *, method="GET", params=None, body=None,
            raw=None, content_type=None, binary=False, etag=None):
    if service not in BASES or not path.startswith("/") or any(x in path for x in ("?", "#", "..", "\\")):
        raise MailError("Invalid Google resource path.")
    if method not in ("GET", "POST", "PATCH", "PUT", "DELETE"):
        raise MailError("Unsupported Google method.")
    url = BASES[service] + path
    if params:
        url += "?" + urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if body is not None:
        raw = json.dumps(body, ensure_ascii=False).encode()
        content_type = "application/json"
    if raw is not None:
        if len(raw) > 26_000_000:
            raise MailError("Google upload exceeds 25 MB plus metadata.")
        headers["Content-Type"] = content_type or "application/octet-stream"
    if etag:
        headers["If-Match"] = etag
    attempts = 3 if method == "GET" else 1
    for attempt in range(attempts):
        try:
            with build_opener(NoRedirect()).open(Request(url, data=raw, headers=headers, method=method), timeout=35) as response:
                content = response.read(26_000_001)
            if len(content) > 26_000_000:
                raise MailError("Google response exceeds the local size limit; narrow the request.")
            if binary:
                return content
            data = json.loads(content) if content else {}
            if not isinstance(data, dict):
                raise MailError("Unexpected Google response shape.")
            return data
        except HTTPError as error:
            if attempt + 1 < attempts and error.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            reason = {400: "invalid_request", 401: "reconnect_required", 403: "missing_permission_API_disabled_or_account_policy",
                      404: "not_found_in_selected_account", 409: "conflict", 412: "resource_changed_read_again",
                      429: "rate_limited"}.get(error.code, "provider_error")
            raise MailError(f"Google {service}: {reason} (HTTP {error.code}). Writes are not automatically retried.") from None
        except (URLError, TimeoutError, OSError):
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
                continue
            raise MailError("Google connection failed; a write may have completed. Check its request status before retrying.") from None
        except (ValueError, UnicodeError):
            raise MailError("Malformed Google response; inspect any attempted write before retrying.") from None
