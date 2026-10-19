"""Update pause ownership, package-manager safety and exclusive maintenance."""

from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from deploiement.scripts.maintenance import invite as guest
from deploiement.scripts.maintenance.commun import VMUpdates, operation_lock


class GuestMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(guest, 'STATE', self.root))
        self.stack.enter_context(patch.object(guest, 'busy', return_value=[]))
        self.stack.enter_context(patch.object(guest, 'packages', return_value='packages'))
        self.properties = {unit: dict(LoadState='loaded', ActiveState='active' if unit in guest.TIMERS else 'inactive',
                                     UnitFileState='enabled', NextElapseUSecRealtime='tomorrow') for unit in guest.UNITS}
        self.stack.enter_context(patch.object(guest, 'property_of', side_effect=lambda unit, key: self.properties[unit][key]))
        self.commands = []
        def run(*command, **kwargs):
            self.commands.append(command)
            if command[:2] == ('systemctl', 'mask'):
                for unit in command[2:]:
                    if unit in self.properties:
                        self.properties[unit]['UnitFileState'] = 'masked-runtime' if '--runtime' in command else 'masked'
            if command[:2] == ('systemctl', 'unmask'):
                for unit in command[2:]:
                    self.properties[unit]['UnitFileState'] = 'enabled'
            return subprocess.CompletedProcess(command, 0, '', '')
        self.stack.enter_context(patch.object(guest, 'run', side_effect=run))

    def test_pause_never_stops_an_active_package_manager(self):
        with patch.object(guest, 'busy', return_value=['apt-daily-upgrade.service']):
            state = guest.pause('campaign', 'measurement')
        self.assertTrue(state['busy'])
        stopped = [command[2:] for command in self.commands if command[:2] == ('systemctl', 'stop')]
        self.assertEqual(stopped, [(timer,) for timer in guest.TIMERS])
        self.assertEqual(guest.read('pause.json')['owner'], 'campaign')

    def test_pause_is_idempotent_and_original_masks_survive_restore(self):
        self.properties['apt-daily.timer']['UnitFileState'] = 'masked'
        guest.pause('campaign', 'measurement')
        first = guest.read('pause.json')
        guest.pause('campaign', 'measurement')
        self.assertEqual(first, guest.read('pause.json'))
        guest.restore('campaign')
        unmasked = [command for command in self.commands if command[:2] == ('systemctl', 'unmask')]
        self.assertNotIn('apt-daily.timer', unmasked[-1])
        self.assertIsNone(guest.read('pause.json'))

    def test_foreign_owner_cannot_change_or_restore_pause(self):
        guest.pause('first', 'measurement')
        self.commands.clear()
        with self.assertRaisesRegex(RuntimeError, 'already paused'):
            guest.pause('second', 'maintenance')
        with self.assertRaisesRegex(RuntimeError, 'another operation'):
            guest.restore('second')
        self.assertEqual(self.commands, [])

    def test_shutdown_restore_does_not_start_catchup_updates(self):
        guest.pause('campaign', 'measurement')
        self.commands.clear()
        state = guest.restore('campaign', start_timers=False)
        self.assertFalse(any(command[:2] == ('systemctl', 'start') for command in self.commands))
        self.assertEqual(state['restored_timers'], list(guest.TIMERS))

    def test_restore_preserves_an_existing_runtime_mask(self):
        self.properties['apt-daily.service']['UnitFileState'] = 'masked-runtime'
        guest.pause('campaign', 'measurement')
        self.commands.clear()
        guest.restore('campaign')
        self.assertIn(('systemctl', 'mask', '--runtime', 'apt-daily.service'), self.commands)

    def test_busy_updates_prevent_restore_and_keep_ownership(self):
        guest.pause('campaign', 'measurement')
        with patch.object(guest, 'busy', return_value=['dpkg']):
            with self.assertRaisesRegex(RuntimeError, 'still active'):
                guest.restore('campaign')
        self.assertEqual(guest.read('pause.json')['owner'], 'campaign')

    def test_upgrade_requires_explicit_maintenance_purpose(self):
        guest.pause('campaign', 'measurement')
        with self.assertRaisesRegex(RuntimeError, 'Explicit maintenance'):
            guest.update('campaign', '')

    def test_failed_upgrade_retains_status_and_never_removes_pause(self):
        guest.pause('maintenance', 'maintenance')
        with patch.object(guest.subprocess, 'run', side_effect=subprocess.CalledProcessError(100, ['apt-get'])):
            with self.assertRaises(subprocess.CalledProcessError):
                guest.update('maintenance', 'socks5h://127.0.0.1:18765')
        self.assertEqual(guest.read('last-update.json')['status'], 'failed')
        self.assertIsNotNone(guest.read('pause.json'))

    def test_successful_upgrade_is_recorded_with_versions_and_proxy(self):
        guest.pause('maintenance', 'maintenance')
        with patch.object(guest.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as runner:
            report = guest.update('maintenance', 'socks5h://127.0.0.1:18765')
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['packages_after_sha256'], 'packages')
        for call in runner.call_args_list:
            self.assertIn('Acquire::http::Proxy=socks5h://127.0.0.1:18765', call.args[0])
            self.assertNotIn('full-upgrade', call.args[0])
        self.assertEqual(guest.read('last-update.json'), report)


class HostMaintenanceTests(unittest.TestCase):
    def client(self, states):
        ssh = Mock(side_effect=[subprocess.CompletedProcess([], 0, json.dumps(s).encode()) for s in states])
        client = VMUpdates(ssh, 'owner', Mock())
        client.install = Mock()
        return client

    def test_waits_for_existing_updates_then_freezes_versions(self):
        client = self.client([dict(busy=['apt']), dict(busy=[], packages_sha256='same'), dict(busy=[], packages_sha256='same')])
        with patch('deploiement.scripts.maintenance.commun.time.sleep'):
            client.pause('proxy')
            client.pause('proxy')
        self.assertEqual(client.fingerprints, dict(proxy='same'))
        self.assertEqual(client.ssh.call_count, 3)

    def test_package_changes_between_vm_passes_are_rejected(self):
        client = self.client([dict(busy=[], packages_sha256='before'), dict(busy=[], packages_sha256='after')])
        client.pause('proxy')
        with self.assertRaisesRegex(RuntimeError, 'Paquets modifiés'):
            client.pause('proxy')

    def test_pending_reboot_prevents_measurement(self):
        client = self.client([dict(busy=[], packages_sha256='same', reboot_required=True)])
        with self.assertRaisesRegex(RuntimeError, 'Maintenance requise'):
            client.pause('proxy')
        self.assertIn('proxy', client.touched)

    def test_maintenance_is_allowed_before_a_required_reboot(self):
        client = self.client([dict(busy=[], packages_sha256='same', reboot_required=True)])
        client.pause('proxy', purpose='maintenance')

    def test_operation_lock_excludes_parallel_measurement_and_maintenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'operation.lock'
            with operation_lock(path):
                with self.assertRaisesRegex(RuntimeError, 'déjà active'):
                    with operation_lock(path):
                        self.fail('Concurrent operation entered')
            with operation_lock(path):
                pass


if __name__ == '__main__':
    unittest.main()
