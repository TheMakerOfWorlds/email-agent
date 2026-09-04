#!/usr/bin/env python3
"""Run the receiver once in the logged-in Mac session, using a private memory-only socket."""
import base64
import json
import os
from pathlib import Path
import plistlib
import secrets
import socket
import subprocess
import sys
import tempfile


def main():
    phase = "desktop_session"
    try:
        raw = sys.stdin.buffer.read(12_000_001)
        if len(raw) > 12_000_000:
            raise ValueError("Input too large")
        payload = json.loads(raw)
        h = Path.home()
        computer = subprocess.check_output(["/usr/sbin/scutil", "--get", "ComputerName"], text=True).strip()
        if payload["target"]["home"] != str(h) or payload["target"]["computer_name"] != computer:
            raise ValueError("Wrong destination")
        code = base64.b64decode(payload["files"]["scripts/remote_install.py"], validate=True)
        base = h / ".config/email-agent"
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix=".session-", dir=base) as tmp:
            folder = Path(tmp)
            worker = folder / "receiver.py"
            worker.write_bytes(code)  # Public source code only, never the private payload.
            endpoint = folder / "pipe"
            label = "com.themakerofworlds.email-agent.session-" + secrets.token_hex(8)
            domain = "gui/" + str(os.getuid())
            plist = folder / "job.plist"
            plist.write_bytes(plistlib.dumps({"Label": label, "ProgramArguments": [sys.executable, str(worker), "--socket", str(endpoint)],
                                             "RunAtLoad": True, "ProcessType": "Interactive"}))
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(endpoint))
                endpoint.chmod(0o600)
                server.listen(1)
                server.settimeout(30)
                subprocess.run(["/bin/launchctl", "bootstrap", domain, str(plist)], capture_output=True, check=True, timeout=15)
                try:
                    connection, _ = server.accept()
                    with connection:
                        connection.settimeout(350)
                        connection.sendall(raw)
                        connection.shutdown(socket.SHUT_WR)
                        with connection.makefile("rb") as stream:
                            result = json.loads(stream.read(1_000_001))
                finally:
                    subprocess.run(["/bin/launchctl", "bootout", domain + "/" + label], capture_output=True, timeout=15)
        print(json.dumps(result))
        return 0 if result.get("status") == "ready" else 1
    except Exception:
        print(json.dumps({"status": "failed", "phase": phase}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
