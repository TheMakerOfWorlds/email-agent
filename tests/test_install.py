import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import install


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.calls = []
        def configure(args):
            self.calls.append(args)
            print(json.dumps({'enabled': args[0] == 'enable'}))
            return 0
        p = patch.object(install.auto_update, 'main', side_effect=configure)
        p.start()
        self.addCleanup(p.stop)

    def saved(self, enabled, repository='someone/fork'):
        install.auto_update.save(self.home / '.config/email-agent/auto-update.json', {'enabled': enabled, 'repository': repository})

    def test_first_install_defaults_to_updates(self):
        self.assertTrue(install.configure_updates(self.home)['enabled'])
        self.assertEqual(self.calls, [['enable', '--repository', install.auto_update.DEFAULT_REPO]])

    def test_disabled_preference_survives_reinstall(self):
        self.saved(False)
        self.assertFalse(install.configure_updates(self.home)['enabled'])
        self.assertEqual(self.calls, [])

    def test_saved_fork_is_preserved(self):
        self.saved(True)
        install.configure_updates(self.home)
        self.assertEqual(self.calls, [['enable', '--repository', 'someone/fork']])

    def test_explicit_opt_out_disables_existing_job(self):
        self.saved(True)
        self.assertFalse(install.configure_updates(self.home, disable=True)['enabled'])
        self.assertEqual(self.calls, [['disable']])

    def test_new_fork_selected_explicitly(self):
        install.configure_updates(self.home, repository='example/new-fork')
        self.assertEqual(self.calls, [['enable', '--repository', 'example/new-fork']])

    def test_install_failure_does_not_enable_updates(self):
        with patch.object(install.shutil, 'which', return_value='codex'), patch.object(install.auto_update, 'run', side_effect=install.auto_update.UpdateError('failed')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(install.main([]), 1)
        self.assertEqual(self.calls, [])

    def test_successful_install_enables_updates(self):
        with patch.object(install.Path, 'home', return_value=self.home), patch.object(install.shutil, 'which', return_value='codex'), patch.object(install.auto_update, 'run') as run, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(install.main([]), 0)
        self.assertTrue(json.loads(output.getvalue())['auto_updates']['enabled'])
        run.assert_called_once()
