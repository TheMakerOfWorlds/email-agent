#!/usr/bin/env python3
"""One-time setup; credentials never appear in arguments or output."""
import argparse
import json
from gmail_backend import OAuth
from email_agent import Mail
from mail_errors import MailError


def main():
    parser = argparse.ArgumentParser(description="Configure a Gmail-only OAuth client and connect a named mailbox.")
    commands = parser.add_subparsers(dest="command", required=True)
    client = commands.add_parser("client", help="Import a downloaded Desktop OAuth JSON into Keychain.")
    client.add_argument("file")
    client.add_argument("--name", default="default")
    connect = commands.add_parser("connect", help="Open the printed Google URL and complete consent.")
    connect.add_argument("account")
    args = parser.parse_args()
    auth = OAuth()
    try:
        if args.command == "client":
            result = auth.import_client(args.file, args.name)
        else:
            result = auth.connect(Mail().account(args.account))
        print(json.dumps(result, separators=(",", ":")))
        return 0
    except (MailError, OSError, ValueError, KeyError, TypeError) as error:
        # Keep HTTP bodies, codes, and credential values out of exception output.
        print(json.dumps({"error": str(error) if isinstance(error, MailError) else "Invalid setup data or unavailable local storage."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
