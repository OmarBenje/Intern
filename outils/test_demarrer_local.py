"""Regression checks for the execution guide's reported launcher failures."""

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('demarrer_local', Path(__file__).with_name('demarrer_local.py'))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.runtime = Path(self.directory.name)
        self.runtime_patch = patch.object(launcher, 'RUNTIME', self.runtime)
        self.runtime_patch.start()
        self.addCleanup(self.runtime_patch.stop)

    def test_engine_file_and_database_configuration_are_loaded(self):
        (self.runtime / 'moteur.env').write_text(
            'export DOCKER_BIN="/existing engine/docker"\n'
            'export DOCKER_HOST=unix:///existing/docker.sock\n')
        (self.runtime / 'local.env').write_text(
            'POSTGRES_PORT=5544\nPOSTGRES_USER=custom_user\nPOSTGRES_PASSWORD=custom_password\n')
        with patch.dict(os.environ, {'VIRTUAL_ENV': '/another/venv'}):
            env = launcher.local_environment('http://localhost:5173', 'http://localhost:8000')
        self.assertNotIn('VIRTUAL_ENV', env)
        self.assertEqual(env['DOCKER_BIN'], '/existing engine/docker')
        self.assertEqual(env['DOCKER_HOST'], 'unix:///existing/docker.sock')
        self.assertEqual(launcher.postgres_environment(env)['PGPORT'], '5544')
        self.assertEqual(launcher.postgres_environment(env)['PGUSER'], 'custom_user')

    def test_sql_uses_config_and_requested_database_without_preparation(self):
        (self.runtime / 'local.env').write_text('POSTGRES_PORT=5544\nPOSTGRES_PASSWORD=custom_password\n')
        with patch('sys.argv', ['demarrer_local.py', 'sql', '--database', 'dedicated']), \
                patch.object(launcher.shutil, 'which', return_value='/bin/psql'), \
                patch.object(launcher, 'run') as run:
            launcher.main()
        run.assert_called_once()
        self.assertEqual(run.call_args.args, ('psql', '-X'))
        self.assertEqual(run.call_args.kwargs['env']['PGDATABASE'], 'dedicated')
        self.assertEqual(run.call_args.kwargs['env']['PGPORT'], '5544')

    def test_podman_has_specific_diagnostic_and_never_starts_compose(self):
        probe = subprocess.CompletedProcess([], 1)
        info = subprocess.CompletedProcess([], 1, '', 'Emulate Docker CLI using podman')
        with patch('sys.argv', ['demarrer_local.py', 'metier']), \
                patch.object(launcher.shutil, 'which', return_value='/bin/tool'), \
                patch.object(launcher, 'occupied', return_value=False), \
                patch.object(launcher.subprocess, 'run', side_effect=[probe, info]), \
                patch.object(launcher, 'run') as run:
            with self.assertRaisesRegex(SystemExit, 'utilise Podman'):
                launcher.main()
        # Only dependency sync is allowed before the failure, no Compose mutation.
        run.assert_called_once()
        self.assertEqual(run.call_args.args, ('uv', 'sync', '--project', 'metier', '--frozen'))
        self.assertNotIn('VIRTUAL_ENV', run.call_args.kwargs['env'])

    def test_invalid_local_configuration_reports_line(self):
        (self.runtime / 'local.env').write_text('POSTGRES_PORT\n')
        with self.assertRaisesRegex(SystemExit, 'local.env:1'):
            launcher.local_environment('http://localhost:5173', 'http://localhost:8000')


if __name__ == '__main__':
    unittest.main()
