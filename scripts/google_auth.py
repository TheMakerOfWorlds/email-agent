"""Opt-in Workspace grants stored separately from existing Gmail grants."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from email_agent import Mail
from gmail_backend import OAuth, TOKEN_URL, http_json
from google_transport import request
from mail_errors import MailError

PREFIX = "https://www.googleapis.com/auth/"
IDENTITY = PREFIX + "userinfo.email"
SERVICE_SCOPES = {
    "calendar": {PREFIX + "calendar.events", PREFIX + "calendar.calendarlist.readonly", PREFIX + "calendar.events.freebusy"},
    "drive": {PREFIX + "drive"},
    "docs": {PREFIX + "documents"},
    "sheets": {PREFIX + "spreadsheets"},
    "contacts": {PREFIX + "contacts"},
    "meet": {PREFIX + "meetings.space.created", PREFIX + "meetings.space.readonly"},
}
ALLOWED = {IDENTITY} | set().union(*SERVICE_SCOPES.values())


def scopes_for(services):
    if not services or set(services) - set(SERVICE_SCOPES):
        raise MailError("Select services from calendar, drive, docs, sheets, contacts, meet.")
    scopes = {IDENTITY} | set().union(*(SERVICE_SCOPES[s] for s in services))
    # Drive permission also authorizes Docs/Sheets; avoid redundant grants.
    if PREFIX + "drive" in scopes:
        scopes -= {PREFIX + "documents", PREFIX + "spreadsheets"}
    return sorted(scopes)


def checked_scopes(value):
    if not isinstance(value, (str, list, set, tuple, frozenset)):
        raise MailError("Google did not report Workspace scopes.")
    actual = set(value.split() if isinstance(value, str) else value)
    if not actual <= ALLOWED or IDENTITY not in actual:
        raise MailError("Unexpected Workspace permissions. Use a dedicated Workspace desktop client; Gmail grants stay separate.")
    return sorted(actual)


class WorkspaceOAuth(OAuth):
    def __init__(self, services=None, store=None, transport=None, identity_transport=None):
        super().__init__(store=store, transport=transport)
        self.requested = scopes_for(services or SERVICE_SCOPES)
        self.identity_http = identity_transport or request

    def client(self, account):
        client = self.store.get("workspace.client." + account.get("workspace_client", "workspace"))
        if not client:
            raise MailError("Workspace desktop client is not configured. See docs/workspace-setup.md; Gmail remains independent.")
        gmail_client = self.store.get("client." + account.get("client", "default"))
        if gmail_client and gmail_client.get("client_id") == client.get("client_id"):
            raise MailError("Workspace requires a separate desktop OAuth client to isolate existing Gmail grants.")
        return client

    def import_client(self, path, name="workspace"):
        backing = self.store
        class Namespace:
            def get(self, key):
                return backing.get("workspace." + key)
            def put(self, key, value):
                existing = self.get(key)
                if existing and existing != value:
                    raise MailError("Workspace client name is already in use. Choose a new --name instead of replacing active credentials.")
                backing.put("workspace." + key, value)
        return OAuth(store=Namespace()).import_client(path, name)

    @staticmethod
    def token_key(account, client):
        return "workspace." + OAuth.token_key(account, client)

    def authorize_url(self, account, client, redirect, state, verifier):
        parsed = urlsplit(super().authorize_url(account, client, redirect, state, verifier))
        query = dict(parse_qsl(parsed.query))
        query["scope"] = " ".join(self.requested)
        return urlunsplit(parsed._replace(query=urlencode(query)))

    def identity(self, token, account):
        data = self.identity_http("identity", "/userinfo", token)
        if data.get("email", "").lower() != account["email"] or data.get("verified_email") is not True:
            raise MailError("Authenticated Google identity differs from the selected account; operation blocked.")
        return data

    def access(self, account):
        client = self.client(account)
        key = self.token_key(account, client)
        if key in self.cache and self.cache[key][1] > time.time() + 60:
            return self.cache[key][0]
        saved = self.store.get(key)
        if not saved:
            raise MailError("Workspace not connected for this account. Use google_auth.py connect ACCOUNT; Gmail remains available.")
        if saved.get("email") != account["email"] or saved.get("client_id") != client["client_id"]:
            raise MailError("Workspace credential identity mismatch.")
        checked_scopes(saved.get("scopes"))
        fresh = self.http(TOKEN_URL, form=True, payload={**client, "grant_type": "refresh_token", "refresh_token": saved["refresh_token"]})
        scopes = checked_scopes(fresh.get("scope", saved["scopes"]))
        token = fresh.get("access_token")
        if not isinstance(token, str) or not token:
            raise MailError("Google returned no Workspace access token.")
        self.identity(token, account)
        if fresh.get("refresh_token"):
            self.store.put(key, {**saved, "refresh_token": fresh["refresh_token"], "scopes": scopes})
        self.cache[key] = (token, time.time() + int(fresh.get("expires_in", 3600)))
        self.scope_cache[key] = scopes
        return token

    def finish(self, account, client, code, redirect, verifier):
        data = self.http(TOKEN_URL, form=True, payload={**client, "code": code, "code_verifier": verifier,
                        "redirect_uri": redirect, "grant_type": "authorization_code"})
        scopes = checked_scopes(data.get("scope"))
        if not set(self.requested) <= set(scopes) or not data.get("refresh_token") or not data.get("access_token"):
            raise MailError("The requested Workspace permissions or renewable access were not granted; existing credentials preserved.")
        self.identity(data["access_token"], account)
        # Validate refresh before replacing an existing working grant.
        fresh = self.http(TOKEN_URL, form=True, payload={**client, "grant_type": "refresh_token", "refresh_token": data["refresh_token"]})
        refreshed_scopes = checked_scopes(fresh.get("scope", scopes))
        if not set(self.requested) <= set(refreshed_scopes):
            raise MailError("Refreshed Workspace grant lost required permissions.")
        self.identity(fresh["access_token"], account)
        self.store.put(self.token_key(account, client), {"email": account["email"], "client_id": client["client_id"],
            "refresh_token": fresh.get("refresh_token", data["refresh_token"]), "scopes": refreshed_scopes, "connected_at": int(time.time())})
        self.cache.clear()
        return {"account": account["id"], "email": account["email"], "authenticated": True,
                "refresh_verified": True, "scopes": refreshed_scopes, "storage": "macOS Keychain"}

    def require(self, account, service):
        token = self.access(account)
        scopes = set(self.scope_cache[self.token_key(account, self.client(account))])
        needed = SERVICE_SCOPES[service]
        if service in ("docs", "sheets") and PREFIX + "drive" in scopes:
            return token
        if not needed <= scopes:
            raise MailError(f"{service} is not authorized for this account. Reconnect with the intended service selection.")
        return token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    client = sub.add_parser("client")
    client.add_argument("file")
    client.add_argument("--name", default="workspace")
    connect = sub.add_parser("connect")
    connect.add_argument("account")
    connect.add_argument("--services", nargs="+", choices=sorted(SERVICE_SCOPES), default=sorted(SERVICE_SCOPES))
    args = parser.parse_args()
    try:
        if args.command == "client":
            # Prevent reusing any configured Gmail client's actual Google identity.
            candidate = json.loads(Path(args.file).read_text()).get("installed", {})
            auth = WorkspaceOAuth()
            for account in Mail().accounts.values():
                old = auth.store.get("client." + account.get("client", "default"))
                if old and old.get("client_id") == candidate.get("client_id"):
                    raise MailError("Create a distinct Workspace Desktop client; this Google client is already used by Gmail.")
            out = auth.import_client(args.file, args.name)
        else:
            out = WorkspaceOAuth(args.services).connect(Mail().account(args.account))
        print(json.dumps(out, separators=(",", ":")))
        return 0
    except (MailError, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"error": str(error) if isinstance(error, MailError) else "Invalid Workspace setup data or unavailable storage."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
