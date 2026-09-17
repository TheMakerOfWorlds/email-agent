#!/usr/bin/env python3
"""Install the registered plugin, enabling GitHub updates by default on first setup."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess

import auto_update


def configure_updates(home, disable=False, repository=None):
    path = home / '.config/email-agent/auto-update.json'
    config = json.loads(path.read_text()) if path.exists() else {}
    if disable:
        command = ['disable']
    elif config.get('enabled') is False:
        return {'enabled': False, 'reason': 'saved_preference'}
    else:
        command = ['enable', '--repository', repository or config.get('repository', auto_update.DEFAULT_REPO)]
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = auto_update.main(command)
    result = json.loads(output.getvalue())
    if code:
        raise auto_update.UpdateError('update_configuration_failed')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-auto-update', action='store_true', help='Disable automatic updates and remember that preference.')
    parser.add_argument('--repository', help='Trusted GitHub OWNER/REPO; defaults to saved upstream or the official repository.')
    parser.add_argument('--configure-updates', action='store_true', help='Configure updates for an already installed plugin, without reinstalling.')
    args = parser.parse_args(argv)
    installed = False
    try:
        if not args.configure_updates:
            codex = shutil.which('codex')
            if not codex:
                raise auto_update.UpdateError('codex_not_found')
            auto_update.run([codex, 'plugin', 'add', 'email-agent@personal'], Path.home(), timeout=120)
            installed = True
        updates = configure_updates(Path.home(), args.no_auto_update, args.repository)
        print(json.dumps({'status': 'ready', 'plugin_installed': installed, 'auto_updates': updates}))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, auto_update.UpdateError):
        print(json.dumps({'status': 'failed', 'plugin_installed': installed,
                          'reason': 'Installation or update configuration failed; inspect source/marketplace and retry.'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
