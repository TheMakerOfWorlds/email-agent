import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import auto_update as au


class UpdateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'home'
        self.home.mkdir()
        self.upstream = Path(self.tmp.name) / 'upstream'
        self.upstream.mkdir()
        self.g(self.upstream, 'init', '-b', 'main')
        self.g(self.upstream, 'config', 'user.name', 'Test')
        self.g(self.upstream, 'config', 'user.email', 'test@example.com')
        for name in ('scripts/auto_update.py', 'scripts/email_agent.py', 'skills/email-agent/SKILL.md', 'tests/test_auto_update.py'):
            p = self.upstream / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('# synthetic fixture\n')
        (self.upstream / '.gitignore').write_text('__pycache__/\n*.pyc\n')
        self.old = self.commit('0.1.0+one')
        self.source = self.home / 'plugins/email-agent'
        self.source.parent.mkdir()
        self.g(self.home, 'clone', str(self.upstream), str(self.source))
        self.g(self.source, 'remote', 'set-url', 'origin', au.repository_url(au.DEFAULT_REPO))
        self.config = {'source': str(self.source), 'repository': au.DEFAULT_REPO, 'python': sys.executable, 'codex': 'fake-codex', 'enabled': True}
        self.installed = '0.1.0+one'
        self.copy_cache()
        self.calls = []
        self.fail_install = False
        self.real_run = au.run
        self.patcher = patch.object(au, 'run', side_effect=self.command)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.new = self.commit('0.1.0+two')

    def g(self, cwd, *args):
        return subprocess.check_output(['git', '-C', str(cwd), *args], stderr=subprocess.DEVNULL).decode().strip()

    def commit(self, version):
        path = self.upstream / '.codex-plugin/plugin.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({'name': 'email-agent', 'version': version}))
        self.g(self.upstream, 'add', '.')
        self.g(self.upstream, 'commit', '-m', version)
        return self.g(self.upstream, 'rev-parse', 'HEAD')

    def copy_cache(self):
        version = json.loads((self.source / '.codex-plugin/plugin.json').read_text())['version']
        cache = self.home / '.codex/plugins/cache/personal/email-agent' / version
        shutil.copytree(self.source.resolve(), cache, ignore=shutil.ignore_patterns('.git', '__pycache__'), dirs_exist_ok=True)
        self.installed = version

    def command(self, args, home, cwd=None, timeout=90):
        self.calls.append(args)
        if args[0] == 'fake-codex':
            if args[2] == 'add':
                if self.fail_install:
                    raise au.UpdateError('command_failed')
                self.copy_cache()
                return b''
            return json.dumps({'installed': [{'name': 'email-agent', 'enabled': True, 'version': self.installed, 'source': {'path': str(self.source)}}]}).encode()
        args = [str(self.upstream) if a == au.repository_url(au.DEFAULT_REPO) else a for a in args]
        return self.real_run(args, home, cwd, timeout)

    def managed(self):
        base = self.home / '.local/share/email-agent/releases'
        base.mkdir(parents=True)
        release = base / self.old
        shutil.copytree(self.source, release, ignore=shutil.ignore_patterns('.git'))
        shutil.rmtree(self.source)
        self.source.symlink_to(release)
        raw = subprocess.check_output(['git', '-C', str(self.upstream), 'archive', self.old])
        files, _ = au.snapshot(raw)
        au.save(self.home / '.config/email-agent/deployment.json', {'revision': self.old, 'accounts': {'accounts': []}, 'source_hashes': au.hashes(files)})

    def test_checkout_updates_and_repeat_verifies_without_install(self):
        private = self.home / '.config/email-agent/accounts.json'
        au.atomic(private, b'private unchanged')
        result = au.update(self.home, self.config)
        self.assertEqual(result['status'], 'updated')
        self.assertEqual(self.g(self.source, 'rev-parse', 'HEAD'), self.new)
        self.assertEqual(private.read_bytes(), b'private unchanged')
        self.calls.clear()
        self.assertEqual(au.update(self.home, self.config)['status'], 'current')
        self.assertFalse(any(a[:3] == ['fake-codex', 'plugin', 'add'] for a in self.calls))

    def test_managed_release_updates_and_remains_compatible_with_remote_sync(self):
        self.managed()
        self.assertEqual(au.update(self.home, self.config)['status'], 'updated')
        self.assertEqual(self.source.resolve().name, self.new)
        state = json.loads((self.home / '.config/email-agent/deployment.json').read_text())
        self.assertEqual(state['revision'], self.new)
        self.assertEqual(state['accounts'], {'accounts': []})
        au.verify_files(self.source, state['source_hashes'])
        self.assertEqual(au.update(self.home, self.config)['status'], 'current')

    def test_managed_failed_install_restores_previous_source(self):
        self.managed()
        self.fail_install = True
        with self.assertRaises(au.UpdateError): au.update(self.home, self.config)
        self.assertEqual(self.source.resolve().name, self.old)
        self.assertEqual(json.loads((self.home / '.config/email-agent/deployment.json').read_text())['revision'], self.old)

    def test_checkout_failed_install_can_retry_without_reset(self):
        self.fail_install = True
        with self.assertRaises(au.UpdateError): au.update(self.home, self.config)
        self.assertEqual(self.g(self.source, 'rev-parse', 'HEAD'), self.new)
        self.assertEqual(self.installed, '0.1.0+one')
        self.fail_install = False
        self.assertEqual(au.update(self.home, self.config)['status'], 'updated')
        self.assertEqual(self.installed, '0.1.0+two')

    def test_disabled_plugin_is_not_reenabled(self):
        with patch.object(au, 'plugin_entry', side_effect=au.UpdateError('plugin_not_enabled')):
            with self.assertRaisesRegex(au.UpdateError, 'plugin_not_enabled'): au.update(self.home, self.config)
        self.assertFalse(any('fetch' in a or a[:3] == ['fake-codex', 'plugin', 'add'] for a in self.calls))

    def test_dirty_checkout_preserved_before_network(self):
        (self.source / 'untracked.txt').write_text('mine')
        with self.assertRaisesRegex(au.UpdateError, 'local_changes_preserved'): au.update(self.home, self.config)
        self.assertFalse(any('fetch' in a or a[0] == 'fake-codex' for a in self.calls))
        self.assertEqual(self.g(self.source, 'rev-parse', 'HEAD'), self.old)

    def test_managed_local_edit_preserved(self):
        self.managed()
        (self.source / 'scripts/email_agent.py').write_text('my edit')
        with self.assertRaisesRegex(au.UpdateError, 'source_or_cache_modified'): au.update(self.home, self.config)
        self.assertEqual(self.source.resolve().name, self.old)

    def test_managed_extra_file_preserved(self):
        self.managed()
        (self.source / 'notes.txt').write_text('mine')
        with self.assertRaisesRegex(au.UpdateError, 'local_changes_preserved'): au.update(self.home, self.config)

    def test_diverged_checkout_never_reset(self):
        self.g(self.source, 'config', 'user.name', 'Test')
        self.g(self.source, 'config', 'user.email', 'test@example.com')
        (self.source / 'local.txt').write_text('mine')
        self.g(self.source, 'add', '.')
        self.g(self.source, 'commit', '-m', 'local')
        local = self.g(self.source, 'rev-parse', 'HEAD')
        with self.assertRaises(au.UpdateError): au.update(self.home, self.config)
        self.assertEqual(self.g(self.source, 'rev-parse', 'HEAD'), local)

    def test_failed_release_tests_do_not_promote(self):
        (self.upstream / 'tests/test_auto_update.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_bad(self): self.fail()\n')
        self.commit('0.1.0+three')
        with self.assertRaises(au.UpdateError): au.update(self.home, self.config)
        self.assertEqual(self.g(self.source, 'rev-parse', 'HEAD'), self.old)
        self.assertEqual(self.installed, '0.1.0+one')

    def test_unchanged_version_rejected(self):
        (self.upstream / 'scripts/email_agent.py').write_text('# changed\n')
        self.commit('0.1.0+one')
        with self.assertRaisesRegex(au.UpdateError, 'release_version_not_changed'): au.update(self.home, self.config)

    def test_wrong_origin_rejected(self):
        self.g(self.source, 'remote', 'set-url', 'origin', 'https://github.com/other/repo.git')
        with self.assertRaisesRegex(au.UpdateError, 'repository_mismatch'): au.update(self.home, self.config)

    def test_tampered_cache_is_not_reported_current(self):
        au.update(self.home, self.config)
        cache = self.home / '.codex/plugins/cache/personal/email-agent/0.1.0+two/scripts/email_agent.py'
        cache.write_text('# altered\n')
        with self.assertRaisesRegex(au.UpdateError, 'source_or_cache_modified'): au.update(self.home, self.config)


class UpdateBoundaryTests(unittest.TestCase):
    def test_repository_is_github_slug_only(self):
        for repo in ('../repo', 'user/repo;echo', 'user/repo/extra', 'https://github.com/u/r', 'u/r?token=x'):
            with self.assertRaises(au.UpdateError): au.repository_url(repo)

    def test_archive_rejects_traversal_and_symlink(self):
        for name, kind in (('../escape', tarfile.REGTYPE), ('link', tarfile.SYMTYPE)):
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode='w') as tar:
                item = tarfile.TarInfo(name)
                item.type = kind
                item.linkname = '/private'
                tar.addfile(item)
            with self.assertRaises(au.UpdateError): au.snapshot(buffer.getvalue())

    def test_environment_does_not_forward_tokens(self):
        with patch.dict(os.environ, {'GOOGLE_TOKEN': 'secret', 'CODEX_THREAD_ID': 'thread', 'GIT_SSH_COMMAND': 'bad'}):
            env = au.environment(Path('/Users/test'))
        self.assertFalse({'GOOGLE_TOKEN', 'CODEX_THREAD_ID', 'GIT_SSH_COMMAND'} & set(env))

    def test_lock_prevents_concurrent_update(self):
        import fcntl
        with tempfile.TemporaryDirectory() as temp, patch.object(au.Path, 'home', return_value=Path(temp)):
            folder = Path(temp) / '.config/email-agent'
            au.save(folder / 'auto-update.json', {'enabled': True})
            with (folder / 'update.lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(au, 'update') as update, patch('sys.stdout', io.StringIO()) as output:
                    self.assertEqual(au.main(['run']), 0)
                    self.assertEqual(json.loads(output.getvalue())['status'], 'busy')
                    update.assert_not_called()
