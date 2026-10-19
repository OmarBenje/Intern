"""Fault injection for diagnostics, atomic evidence and graceful controller signals."""

import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from campagnes17 import Campaigns
from etalonnage import save, private_jmeter_log


class IncidentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.controller = Campaigns.__new__(Campaigns)
        self.controller.runtime = self.root
        self.controller.manifest = dict(progress=dict(action='bootstrap'))
        self.controller.env = dict(os.environ)

    def test_failure_keeps_stdout_and_recovery_does_not_overwrite_first_diagnostic(self):
        for message in ('original failure', 'recovery failure'):
            with self.assertRaisesRegex(RuntimeError, 'Command failed'):
                self.controller.run([sys.executable, '-c', f'print({message!r}); raise SystemExit(3)'])
        paths = self.controller.manifest['command_errors']
        self.assertEqual(len(paths), 2)
        original = json.loads((self.root / paths[0]).read_text())
        self.assertEqual(original['stdout'].strip(), 'original failure')
        self.assertEqual(original['returncode'], 3)
        self.assertEqual(original['action'], 'bootstrap')
        self.assertEqual((self.root / paths[0]).stat().st_mode & 0o777, 0o600)

    def test_timeout_and_missing_executable_are_distinct_and_keep_diagnostics(self):
        errors = [subprocess.TimeoutExpired(['fixture'], 2, output=b'partial stdout', stderr=b'partial stderr'),
                  FileNotFoundError('missing executable')]
        for error in errors:
            with self.subTest(error=type(error).__name__), \
                    patch('campagnes17.subprocess.run', side_effect=error):
                with self.assertRaises(type(error)) as raised:
                    self.controller.run(['fixture'])
                self.assertIs(raised.exception, error)
                path = self.root / self.controller.manifest['command_errors'][-1]
                self.assertEqual(json.loads(path.read_text())['error'], type(error).__name__)
        first = self.root / self.controller.manifest['command_errors'][0]
        self.assertEqual(json.loads(first.read_text())['stderr'], 'partial stderr')

    def test_expected_nonzero_status_does_not_create_false_incident(self):
        result = self.controller.run([sys.executable, '-c', 'raise SystemExit(1)'], check=False)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('command_errors', self.controller.manifest)

    def test_failed_atomic_replace_preserves_previous_manifest_and_cleans_temporary_file(self):
        path = self.root / 'manifest.json'
        save(path, dict(status='running'))
        with patch.object(Path, 'replace', side_effect=OSError('disk failure')):
            with self.assertRaisesRegex(OSError, 'disk failure'):
                save(path, dict(status='complete'))
        self.assertEqual(json.loads(path.read_text()), dict(status='running'))
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_serialization_failure_cannot_truncate_previous_evidence(self):
        path = self.root / 'manifest.json'
        save(path, dict(status='running'))
        with self.assertRaises(TypeError):
            save(path, dict(invalid=object()))
        self.assertEqual(json.loads(path.read_text()), dict(status='running'))

    def test_private_java_logs_do_not_collide_or_overwrite_existing_trace(self):
        with patch('etalonnage.ROOT', self.root / 'application/mesure'):
            a = private_jmeter_log(self.root / 'runtime/jmeter/serie-1/vm/240/jmeter.log')
            b = private_jmeter_log(self.root / 'runtime/jmeter/serie-1/docker/240/jmeter.log')
            c = private_jmeter_log(self.root / 'runtime/jmeter/etalonnage/docker/240/jmeter.log')
            self.assertEqual(len({a, b, c}), 3)
            a.write_text('original Java diagnostic')
            with self.assertRaises(FileExistsError):
                private_jmeter_log(a)
            self.assertEqual(a.read_text(), 'original Java diagnostic')
            self.assertEqual(a.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(RuntimeError, 'outside the application'):
                private_jmeter_log(self.root / 'application/logs/java.log')

    def test_standalone_java_logs_use_distinct_private_temporary_files(self):
        a, b = private_jmeter_log(), private_jmeter_log()
        try:
            self.assertNotEqual(a, b)
            self.assertEqual(a.stat().st_mode & 0o777, 0o600)
        finally:
            a.unlink()
            b.unlink()

    def test_real_sigterm_reaches_finally_and_releases_operation_lock(self):
        self.assert_signal_cleanup(signal.SIGTERM)

    def test_real_sigint_reaches_finally_and_releases_operation_lock(self):
        self.assert_signal_cleanup(signal.SIGINT)

    def assert_signal_cleanup(self, signum):
        script = '''import pathlib,sys,time
sys.path.insert(0,sys.argv[1])
import campagnes17 as module
root=pathlib.Path(sys.argv[2]); module.ROOT=root/'mesure'
c=module.Campaigns.__new__(module.Campaigns); c.runtime=root
def run():
    try:
        (root/'ready').touch()
        while True:
            c.check_stop(); time.sleep(.01)
    finally:
        (root/'restored').touch()
c.run_campaigns=run
try: c.main()
except InterruptedError: pass
'''
        process = subprocess.Popen([sys.executable, '-c', script, str(SCRIPTS), str(self.root)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / 'ready').exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue((self.root / 'ready').exists())
            process.send_signal(signum)
            _, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr.decode())
            self.assertTrue((self.root / 'restored').exists())
            with (self.root / '.execution/operations-vm.lock').open('a') as stream:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()
