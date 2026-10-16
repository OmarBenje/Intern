"""Check engine discovery and safe configuration replacement."""

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('configurer', Path(__file__).with_name('configurer_moteur.py'))
configurer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configurer)


class ConfigurationTests(unittest.TestCase):
    def test_podman_is_rejected_even_when_command_succeeds(self):
        result = subprocess.CompletedProcess([], 0, 'podman version 5.8.2', '')
        with patch.object(configurer.subprocess, 'run', return_value=result):
            self.assertFalse(configurer.probe(['/usr/bin/docker', '--version']))

    def test_missing_client_is_rejected(self):
        with patch.object(configurer.subprocess, 'run', side_effect=FileNotFoundError):
            self.assertFalse(configurer.probe(['/missing/docker', '--version']))

    def test_quotes_spaces_backup_and_idempotence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'moteur.env'
            original = 'export DOCKER_BIN=/tmp/old-docker\n'
            path.write_text(original)
            values = {'DOCKER_BIN': "/project with space/it's docker", 'DOCKER_ENGINE_DATA': '/existing data'}
            configurer.save_config(path, values)
            self.assertEqual(configurer.existing_config(path), values)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            backups = list(path.parent.glob('moteur.env.*.bak'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), original)
            stamp = path.stat().st_mtime_ns
            configurer.save_config(path, values)
            self.assertEqual(path.stat().st_mtime_ns, stamp)

    def test_missing_engine_preserves_old_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'moteur.env'
            path.write_text('export DOCKER_BIN=/tmp/old-docker\n')
            original = path.read_bytes()
            with patch.object(configurer, 'CONFIG', path), \
                    patch.object(configurer, 'find_client', return_value=None), \
                    patch('sys.argv', ['configurer_moteur.py']):
                with self.assertRaisesRegex(SystemExit, 'Docker Engine introuvable'):
                    configurer.main()
            self.assertEqual(path.read_bytes(), original)

    def test_restore_requires_existing_data_before_downloading(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(configurer, 'CONFIG', Path(directory) / 'absent.env'), \
                    patch.object(configurer, 'find_client', return_value=None), \
                    patch.object(configurer, 'restore_engine') as restore, \
                    patch('sys.argv', ['configurer_moteur.py', '--restaurer']), \
                    patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(SystemExit, 'Stockage rootless existant requis'):
                    configurer.main()
            restore.assert_not_called()


if __name__ == '__main__':
    unittest.main()
