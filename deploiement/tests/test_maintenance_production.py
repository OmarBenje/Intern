"""Production SSH targets stay online and do not depend on VirtualBox."""

import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from deploiement.scripts.maintenance import machines, serveurs


class ProductionMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'ssh.conf').touch()
        self.path = self.root / 'production.json'
        self.profile = dict(ssh_config='ssh.conf', egress='direct', hosts=[dict(
            alias='intern-prod', services=['docker.service', 'cloudflared.service'],
            restart_services=['cloudflared.service'], health_url='http://127.0.0.1:8080/health/ready/')])

    def configuration(self):
        self.path.write_text(json.dumps(self.profile))
        return serveurs.configuration(self.path)

    def client(self, redemarrer=False):
        profile = self.configuration()
        client = serveurs.Servers(argparse.Namespace(config=profile['ssh_config'], action='executer', redemarrer=redemarrer), profile)
        client.report_path = self.root / 'report.json'
        client.run = Mock(return_value=subprocess.CompletedProcess([], 0, b'boot-id', b''))
        client.updates = Mock(touched={'intern-prod'})
        client.updates.call.return_value = dict(last_update=dict(owner=client.owner, status='complete', packages_after_sha256='packages'),
                                               reboot_required=True, boot_id='boot-id', kernel='kernel')
        return client

    def test_production_maintenance_only_uses_ssh_and_keeps_server_online(self):
        client = self.client()
        with patch.object(machines, 'operation_lock', return_value=nullcontext()):
            client.main()
        commands = [call.args[0] for call in client.run.call_args_list]
        self.assertTrue(commands)
        self.assertTrue(all(command[0] == 'ssh' for command in commands))
        self.assertTrue(all('intern-prod' in command for command in commands))
        self.assertFalse(any('systemctl reboot' in command[-1] or 'poweroff' in command[-1] for command in commands))
        self.assertTrue(any('restart cloudflared.service' in command[-1] for command in commands))
        self.assertTrue(any('http://127.0.0.1:8080/health/ready/' in command[-1] for command in commands))
        self.assertTrue(any('systemd-run' in command[-1] and '--proxy' not in command[-1] for command in commands))
        self.assertEqual(client.report['status'], 'reboot-required')
        client.updates.restore.assert_called_once_with('intern-prod', poweroff=False)

    def test_server_reboot_requires_explicit_option_and_verifies_new_boot(self):
        client = self.client(redemarrer=True)
        client.wait_ssh = Mock()
        client.updates.call.side_effect = [client.updates.call.return_value,
                                          dict(reboot_required=False, boot_id='new-boot', kernel='new-kernel')]
        client.update('intern-prod')
        client.wait_ssh.assert_called_once_with('intern-prod', old_boot='boot-id')
        self.assertTrue(client.report['hosts']['intern-prod']['rebooted'])
        self.assertTrue(any(call.args[0][-1] == 'sudo systemctl reboot' for call in client.run.call_args_list))

    def test_relative_ssh_configuration_is_resolved_against_profile(self):
        self.assertEqual(self.configuration()['ssh_config'], self.root / 'ssh.conf')

    def test_duplicate_servers_are_rejected_before_any_connection(self):
        self.profile['hosts'].append(dict(self.profile['hosts'][0]))
        with self.assertRaisesRegex(ValueError, 'distincts'):
            self.configuration()

    def test_unknown_restart_service_is_rejected(self):
        self.profile['hosts'][0]['restart_services'] = ['other.service']
        with self.assertRaisesRegex(ValueError, 'doivent figurer'):
            self.configuration()

    def test_profile_requires_a_health_check(self):
        self.profile['hosts'][0] = dict(alias='prod')
        with self.assertRaisesRegex(ValueError, 'service ou une URL'):
            self.configuration()

    def test_no_reboot_is_attempted_by_status_or_shutdown(self):
        client = self.client()
        client.shutdown_started()
        client.run.assert_not_called()
        self.assertEqual(client.info('intern-prod')[1], 'running')
        self.assertTrue(all(call.args[0][0] == 'ssh' for call in client.run.call_args_list))


if __name__ == '__main__':
    unittest.main()
