"""Explicit update orchestration: reboot, detached APT and interrupted operations."""

import argparse
from contextlib import nullcontext
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from deploiement.scripts.maintenance import machines as host
from deploiement.scripts.maintenance.commun import operation_lock


class MaintenanceCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report_patch = patch.object(host, 'REPORT', self.root / 'maintenance.json')
        self.report_patch.start()
        self.addCleanup(self.report_patch.stop)
        self.client = host.Maintenance(argparse.Namespace(config=self.root / 'ssh.conf', action='executer'))
        self.client.tunnel = Mock(side_effect=lambda service: nullcontext('socks5h://127.0.0.1:18765'))
        self.client.ssh = Mock(return_value=subprocess.CompletedProcess([], 0, b''))
        self.client.updates = Mock(touched=set())
        self.client.updates.pause.return_value = {}
        self.complete = dict(last_update=dict(owner=self.client.owner, status='complete', packages_after_sha256='packages'),
                             reboot_required=False, boot_id='old-boot', kernel='kernel')

    def test_upgrade_runs_under_systemd_and_uses_temporary_ssh_proxy(self):
        self.client.updates.call.return_value = self.complete
        self.client.update('proxy')
        commands = [call.args[1] for call in self.client.ssh.call_args_list]
        self.assertTrue(any('systemd-run' in command and 'socks5h://127.0.0.1:18765' in command for command in commands))
        self.client.updates.pause.assert_called_once_with('proxy', purpose='maintenance')
        self.assertFalse(self.client.report['hosts']['proxy']['rebooted'])

    def test_required_reboot_waits_for_a_new_boot_then_checks_service(self):
        self.client.updates.call.side_effect = [{**self.complete, 'reboot_required': True}, self.complete]
        self.client.wait_ssh = Mock()
        self.client.update('donnees')
        self.client.wait_ssh.assert_called_once_with('donnees', old_boot='old-boot')
        self.assertTrue(self.client.report['hosts']['donnees']['rebooted'])
        self.client.ssh.assert_any_call('donnees', 'sudo systemctl is-active --quiet postgresql@16-main')

    def test_failed_background_upgrade_is_not_reported_as_successful(self):
        self.client.updates.call.return_value = {**self.complete, 'last_update': {**self.complete['last_update'], 'status': 'failed'}}
        with self.assertRaisesRegex(RuntimeError, 'Mise à jour échouée'):
            self.client.update('proxy')
        self.assertNotIn('proxy', self.client.report['hosts'])

    def test_busy_package_manager_prevents_shutdown_during_cleanup(self):
        self.client.boot = Mock()
        self.client.update = Mock(side_effect=RuntimeError('SSH lost'))
        self.client.updates.touched = {'proxy'}
        self.client.updates.restore.side_effect = RuntimeError('APT still busy')
        self.client.shutdown_started = Mock()
        with patch.object(host, 'operation_lock', return_value=nullcontext()):
            with self.assertRaisesRegex(RuntimeError, 'Restauration non terminée'):
                self.client.main()
        self.client.shutdown_started.assert_not_called()
        self.assertEqual(self.client.report['status'], 'failed')
        self.assertEqual(self.client.report['error'], 'SSH lost')

    def test_campaign_lock_prevents_any_vm_change(self):
        path = self.root / 'operation.lock'
        self.client.boot = Mock()
        with operation_lock(path):
            with patch.object(host, 'operation_lock', side_effect=lambda: operation_lock(path)):
                with self.assertRaisesRegex(RuntimeError, 'déjà active'):
                    self.client.main()
        self.client.boot.assert_not_called()


if __name__ == '__main__':
    unittest.main()
