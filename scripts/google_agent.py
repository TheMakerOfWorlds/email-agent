#!/usr/bin/env python3
"""Account-first Google services. Loads only the selected service module."""
import argparse
import importlib
import json
from pathlib import Path
import sys

from email_agent import Mail
from google_core import Workspace
from google_auth import SERVICE_SCOPES
from mail_errors import MailError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=["accounts", "doctor", "status", *SERVICE_SCOPES])
    parser.add_argument("account", nargs="?")
    parser.add_argument("action", nargs="?")
    parser.add_argument("--input", help="JSON file, or - for stdin. Only fields documented for the action are accepted.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--cursor")
    parser.add_argument("--request-id")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    try:
        if args.service == "accounts":
            result = Mail().list_accounts()
            result["available_commands"] = ["gmail", *SERVICE_SCOPES]
            result["routing"] = "Choose the exact company/account from purpose notes; ask if ambiguous. Permissions are checked on use."
        else:
            if not args.account:
                raise MailError("An explicit account ID is required; run accounts first.")
            workspace = Workspace(args.account, limit=args.limit, cursor=args.cursor)
            if args.service == "doctor":
                permissions = workspace.auth.permissions(workspace.account)
                result = {"account": args.account, "authenticated_as": workspace.account["email"], "scopes": permissions,
                          "authenticated": True, "refresh_verified": True}
            elif args.service == "status":
                result = workspace.status(args.action or args.request_id)
            else:
                if not args.action:
                    raise MailError("Specify a service action; read that service's reference.")
                data = {}
                if args.input:
                    if args.input == "-":
                        raw = sys.stdin.read(1_000_001)
                    else:
                        with Path(args.input).open() as source:
                            raw = source.read(1_000_001)
                    if len(raw) > 1_000_000:
                        raise MailError("Input JSON exceeds 1 MB.")
                    data = json.loads(raw)
                module = importlib.import_module("google_services." + args.service)
                result = module.run(workspace, args.action, data, args.request_id, args.preview)
                result = workspace.envelope(result)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (MailError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({"error": str(error) if isinstance(error, MailError) else "Invalid service input or unavailable local data. Read the service reference."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
