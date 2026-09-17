#!/usr/bin/env python3
"""Opt-in macOS GitHub updater. Never reads Google credentials or mailbox data."""
import argparse
import contextlib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

LABEL = 'com.themakerofworlds.email-agent.update'
DEFAULT_REPO = 'TheMakerOfWorlds/email-agent'


class UpdateError(Exception):
    pass


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.update-')
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save(path, value):
    atomic(path, (json.dumps(value, indent=2)+'\n').encode())


def environment(home):
    # Do not inherit Codex app session variables, Google secrets, or Git overrides.
    return {'HOME': str(home), 'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
            'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
            'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'en_US.UTF-8'}


def run(args, home, cwd=None, timeout=90):
    result = subprocess.run(args, cwd=cwd, env=environment(home), capture_output=True, timeout=timeout)
    if result.returncode:
        raise UpdateError('command_failed_' + Path(args[0]).name)  # Never echo command output or environment.
    return result.stdout


def git(repo, home, *args):
    return run(['git', '-c', 'core.hooksPath=/dev/null', '-C', str(repo), *args], home)


def repository_url(repo):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or any(x in ('.', '..') for x in repo.split('/')):
        raise UpdateError('invalid_repository')
    return 'https://github.com/'+repo+'.git'


def snapshot(raw):
    files = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise UpdateError('invalid_archive_path')
            if member.isdir():
                continue
            if not member.isfile() or member.name.startswith('.git/'):
                raise UpdateError('invalid_archive_entry')
            total += member.size
            if total > 5_000_000 or len(files) >= 200:
                raise UpdateError('release_too_large')
            files[member.name] = archive.extractfile(member).read()
    manifest = json.loads(files['.codex-plugin/plugin.json'])
    if manifest.get('name') != 'email-agent' or not re.fullmatch(r'[A-Za-z0-9.+_-]{1,100}', manifest.get('version', '')):
        raise UpdateError('invalid_manifest')
    for required in ('scripts/auto_update.py', 'scripts/email_agent.py', 'skills/email-agent/SKILL.md', 'tests/test_auto_update.py'):
        if required not in files:
            raise UpdateError('incomplete_release')
    return files, manifest['version']


def hashes(files):
    return {name: hashlib.sha256(body).hexdigest() for name, body in files.items()}


def verify_files(root, expected):
    for name, digest in expected.items():
        p = root / name
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise UpdateError('source_or_cache_modified')


def check_source(source, home, base, expected_url):
    actual = source.resolve(strict=True)
    if (actual / '.git').exists():
        if git(actual, home, 'status', '--porcelain').strip():
            raise UpdateError('local_changes_preserved')
        origin = git(actual, home, 'remote', 'get-url', 'origin').decode().strip()
        accepted = {expected_url, expected_url.removesuffix('.git'),
                    'git@github.com:'+expected_url.split('github.com/', 1)[1]}
        if origin not in accepted:
            raise UpdateError('repository_mismatch')
        if not git(actual, home, 'branch', '--show-current').strip():
            raise UpdateError('detached_checkout_preserved')
        return actual, git(actual, home, 'rev-parse', 'HEAD').decode().strip(), 'checkout'
    if not source.is_symlink() or actual.parent != (base / 'releases').resolve():
        raise UpdateError('unmanaged_source_preserved')
    state = json.loads((home / '.config/email-agent/deployment.json').read_text())
    if actual.name != state['revision']:
        raise UpdateError('deployment_revision_mismatch')
    verify_files(actual, state['source_hashes'])
    known = set(state['source_hashes'])
    extras = [p for p in actual.rglob('*') if p.is_file() and str(p.relative_to(actual)) not in known
              and '__pycache__' not in p.parts and p.suffix != '.pyc']
    if extras:
        raise UpdateError('local_changes_preserved')
    return actual, state['revision'], 'release'


def plugin_entry(home, codex):
    listing = json.loads(run([codex, 'plugin', 'list', '--marketplace', 'personal', '--json'], home, timeout=40))
    entries = [e for e in listing.get('installed', []) if e.get('name') == 'email-agent']
    if len(entries) != 1 or not entries[0].get('enabled'):
        raise UpdateError('plugin_not_enabled')
    return entries[0]


def promote_link(source, release):
    link = source.parent / '.email-agent-update-link'
    if link.is_symlink():
        link.unlink()
    if link.exists():
        raise UpdateError('link_path_occupied')
    link.symlink_to(release, target_is_directory=True)
    os.replace(link, source)


def update(home, config):
    base = home / '.local/share/email-agent'
    source = Path(config['source'])
    url = repository_url(config['repository'])
    actual, old_revision, kind = check_source(source, home, base, url)
    # Respect uninstall/disable; background updates must not silently enable a disabled plugin.
    entry = plugin_entry(home, config['codex'])
    if Path(entry.get('source', {}).get('path', '')).resolve() != actual:
        raise UpdateError('marketplace_source_mismatch')
    mirror = base / 'upstream.git'
    if not mirror.exists():
        run(['git', 'init', '--bare', str(mirror)], home)
    git(mirror, home, 'fetch', '--no-tags', url, '+refs/heads/main:refs/heads/upstream-main')
    revision = git(mirror, home, 'rev-parse', 'refs/heads/upstream-main').decode().strip()
    # Never undo local commits or adopt rewritten/disconnected upstream history.
    git(mirror, home, 'merge-base', '--is-ancestor', old_revision, revision)
    files, version = snapshot(git(mirror, home, 'archive', revision))
    expected = hashes(files)
    cache = home / '.codex/plugins/cache/personal/email-agent' / version
    if old_revision == revision and entry.get('version') == version:
        verify_files(actual, expected)
        verify_files(cache, expected)
        return {'status': 'current', 'revision': revision, 'version': version}
    if entry.get('version') == version and old_revision != revision:
        raise UpdateError('release_version_not_changed')
    releases = base / 'releases'
    releases.mkdir(parents=True, exist_ok=True, mode=0o700)
    release = releases / revision
    if not release.exists():
        with tempfile.TemporaryDirectory(prefix='.stage-', dir=releases) as tmp:
            stage = Path(tmp) / 'release'
            stage.mkdir()
            for name, body in files.items():
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
            # Release tests are public code from the explicitly trusted GitHub main branch.
            run([config['python'], '-m', 'unittest', 'discover', '-s', 'tests', '-q'], home, cwd=stage, timeout=120)
            run([config['python'], '-m', 'compileall', '-q', 'scripts'], home, cwd=stage, timeout=60)
            stage.rename(release)
    verify_files(release, expected)
    # Check again after network and tests, before touching source or installing.
    if check_source(source, home, base, url) != (actual, old_revision, kind):
        raise UpdateError('source_changed_during_update')
    if kind == 'checkout':
        git(actual, home, 'fetch', str(mirror), revision)
        git(actual, home, 'merge', '--ff-only', revision)
    else:
        promote_link(source, release)
    try:
        run([config['codex'], 'plugin', 'add', 'email-agent@personal'], home, timeout=120)
        installed = plugin_entry(home, config['codex'])
        if installed.get('version') != version:
            raise UpdateError('installed_version_mismatch')
        verify_files(cache, expected)
    except Exception:
        if kind == 'release':
            promote_link(source, actual)
            # Restore the previous installed version when possible. Never hide a failure.
            with contextlib.suppress(Exception):
                run([config['codex'], 'plugin', 'add', 'email-agent@personal'], home, timeout=120)
        # A checkout remains fast-forwarded, with no reset that could destroy concurrent edits.
        raise
    if kind == 'release':
        state_path = home / '.config/email-agent/deployment.json'
        state = json.loads(state_path.read_text())
        state.update(revision=revision, source_hashes=expected)
        save(state_path, state)
    return {'status': 'updated', 'revision': revision, 'previous_revision': old_revision, 'version': version}


def domain():
    return 'gui/'+str(os.getuid())


def launch(home, *args, check=True):
    result = subprocess.run(['/bin/launchctl', *args], capture_output=True, timeout=20)
    if check and result.returncode:
        raise UpdateError('launch_agent_command_failed')
    return result.returncode == 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enable', 'disable', 'status', 'run'])
    parser.add_argument('--repository', default=DEFAULT_REPO, help='Trusted GitHub OWNER/REPO, main branch.')
    args = parser.parse_args(argv)
    home = Path.home()
    config_dir = home / '.config/email-agent'
    config_path = config_dir / 'auto-update.json'
    status_path = config_dir / 'auto-update-status.json'
    plist = home / 'Library/LaunchAgents' / (LABEL+'.plist')
    try:
        if args.action == 'status':
            config = json.loads(config_path.read_text()) if config_path.exists() else {}
            result = {'enabled': bool(config.get('enabled')), 'loaded': launch(home, 'print', domain()+'/'+LABEL, check=False),
                      'repository': config.get('repository'), 'interval_seconds': 3600,
                      'last_check': json.loads(status_path.read_text()) if status_path.exists() else None}
        elif args.action == 'disable':
            config = json.loads(config_path.read_text()) if config_path.exists() else {}
            config['enabled'] = False
            save(config_path, config)
            launch(home, 'bootout', domain()+'/'+LABEL, check=False)
            if plist.exists():
                plist.unlink()
            result = {'enabled': False}
        elif args.action == 'enable':
            if sys.platform != 'darwin':
                raise UpdateError('macos_required')
            repository_url(args.repository)
            source = home / 'plugins/email-agent'
            codex = shutil.which('codex')
            if not codex:
                raise UpdateError('codex_not_found')
            check_source(source, home, home / '.local/share/email-agent', repository_url(args.repository))
            config = {'enabled': True, 'source': str(source), 'repository': args.repository,
                      'codex': codex, 'python': sys.executable}
            save(config_path, config)
            atomic(plist, plistlib.dumps({'Label': LABEL, 'ProgramArguments': [sys.executable, str(source / 'scripts/auto_update.py'), 'run'],
                                         'RunAtLoad': True, 'StartInterval': 3600, 'ProcessType': 'Background',
                                         'EnvironmentVariables': environment(home)}))
            launch(home, 'bootout', domain()+'/'+LABEL, check=False)
            launch(home, 'bootstrap', domain(), str(plist))
            result = {'enabled': True, 'repository': args.repository, 'interval_seconds': 3600}
        else:
            config = json.loads(config_path.read_text())
            if not config.get('enabled'):
                raise UpdateError('updates_disabled')
            config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(config_dir / 'update.lock', os.O_RDWR | os.O_CREAT, 0o600)
            with os.fdopen(fd, 'w') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    print(json.dumps({'status': 'busy'}))
                    return 0
                result = update(home, config)
                result['checked_at'] = int(time.time())
                save(status_path, result)
        print(json.dumps(result))
        return 0
    except Exception as error:
        result = {'status': 'failed', 'reason': str(error) if isinstance(error, UpdateError) else 'update_check_failed',
                  'checked_at': int(time.time())}
        if args.action == 'run':
            save(status_path, result)
        print(json.dumps(result))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
