"""Python pin consistency and rollback before touching a real VM service."""

import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('aligner_python_invite', ROOT / 'deploiement/scripts/aligner_python_invite.py')
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


class PythonAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.expected = (ROOT / 'metier/.python-version').read_text().strip()
        (self.project / '.python-version').write_text(self.expected)
        self.stage = self.project / ('.venv-python-' + self.expected)
        self.stage.mkdir()
        (self.stage / '.python-validation.json').write_text(json.dumps(dict(python=self.expected, exit_code=0)))
        (self.project / '.venv').mkdir()
        (self.project / '.venv/old-environment').touch()
        self.patches = [patch.object(guest, 'PROJECT', self.project),
                        patch.object(guest, 'version', return_value=self.expected),
                        patch.object(guest.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0))]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_docker_base_and_installer_follow_the_same_python_pin(self):
        versions = re.findall(r'^FROM python:([0-9.]+)-', (ROOT / 'docker/metier.Dockerfile').read_text(), re.M)
        self.assertEqual(versions, [self.expected, self.expected])
        installer = (ROOT / 'deploiement/scripts/installer_metier.sh').read_text()
        self.assertIn('cat /opt/intern/metier/.python-version', installer)
        self.assertNotIn('--python /usr/bin/python3', installer)

    def test_successful_activation_keeps_the_original_environment(self):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        with patch.object(guest, 'run'), patch.object(guest.urllib.request, 'urlopen', return_value=response):
            result = guest.activate(self.stage)
        self.assertEqual((self.project / '.venv').resolve(), self.stage)
        self.assertTrue((Path(result['backup']) / 'old-environment').exists())

    def test_failed_service_start_rolls_back_and_restarts_old_environment(self):
        def run(*parts, **kw):
            if parts == ('systemctl', 'start', 'intern'):
                raise RuntimeError('new runtime failed')
        with patch.object(guest, 'run', side_effect=run) as command:
            with self.assertRaisesRegex(RuntimeError, 'new runtime failed'):
                guest.activate(self.stage)
        self.assertTrue((self.project / '.venv/old-environment').exists())
        self.assertFalse((self.project / '.venv').is_symlink())
        command.assert_any_call('systemctl', 'restart', 'intern')

    def test_failed_rename_also_restarts_untouched_old_service(self):
        with patch.object(guest.os, 'replace', side_effect=OSError('rename denied')), \
                patch.object(guest, 'run') as command:
            with self.assertRaisesRegex(OSError, 'rename denied'):
                guest.activate(self.stage)
        self.assertTrue((self.project / '.venv/old-environment').exists())
        command.assert_any_call('systemctl', 'restart', 'intern')

    def test_untested_stage_cannot_replace_a_working_environment(self):
        (self.stage / '.python-validation.json').write_text(json.dumps(dict(python=self.expected, exit_code=1)))
        with patch.object(guest, 'run') as command:
            with self.assertRaisesRegex(RuntimeError, 'Successful tests'):
                guest.activate(self.stage)
        command.assert_not_called()
        self.assertTrue((self.project / '.venv/old-environment').exists())

    def test_preparation_never_modifies_an_already_active_stage(self):
        old = self.project / '.venv'
        (old / 'old-environment').unlink()
        old.rmdir()
        old.symlink_to(self.stage)
        with patch.object(guest, 'run') as command:
            with self.assertRaisesRegex(RuntimeError, 'already active'):
                guest.prepare(Path('/isolated/python'), self.expected)
        command.assert_not_called()

    def test_preparing_again_invalidates_previous_test_marker(self):
        with patch.object(guest, 'run'):
            guest.prepare(Path('/isolated/python'), self.expected)
        self.assertFalse((self.stage / '.python-validation.json').exists())
