"""Regression checks for VirtualBox session transitions during step-8 shutdown."""

import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / 'deploiement/scripts/reseau_etape8.py'
spec = importlib.util.spec_from_file_location('reseau_etape8', path)
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)


def response(code=0, state='poweroff', error=''):
    return subprocess.CompletedProcess([], code, f'VMState="{state}"\n', error)


class VirtualBoxTransitionTests(unittest.TestCase):
    def test_netplan_timeout_can_exceed_read_only_check_timeout(self):
        with patch.object(network, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
            network.ssh(Path('/tmp/ssh.conf'), 'vm-donnees', 'sudo netplan apply', timeout=120)
        self.assertEqual(run.call_args.kwargs['timeout'], 120)

    def test_ssh_banner_timeout_before_authentication_is_retried(self):
        transient = subprocess.CompletedProcess([], 255, '', 'Connection timed out during banner exchange')
        success = subprocess.CompletedProcess([], 0, 'ok', '')
        with patch.object(network, 'run', side_effect=[transient, success]) as run, \
                patch.object(network.time, 'sleep'):
            result = network.ssh(Path('/tmp/config with spaces/ssh.conf'), 'vm-metier', 'hostname')
        self.assertEqual(result.stdout, 'ok')
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args.args[0][2], 'ssh.conf')

    def test_ssh_banner_retries_are_bounded(self):
        error = subprocess.CompletedProcess([], 255, '', 'Connection timed out during banner exchange')
        with patch.object(network, 'run', return_value=error) as run, \
                patch.object(network.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'banner exchange'):
                network.ssh(Path('/tmp/ssh.conf'), 'vm-metier', 'hostname')
        self.assertEqual(run.call_count, 3)

    def test_ssh_never_replays_remote_failure_or_authentication_error(self):
        for code, output, error in ((1, '', 'command failed'), (255, 'started', 'Connection timed out during banner exchange'),
                                    (255, '', 'Permission denied (publickey)')):
            with self.subTest(error=error), patch.object(network, 'run', return_value=subprocess.CompletedProcess([], code, output, error)) as run:
                with self.assertRaises(RuntimeError):
                    network.ssh(Path('/tmp/ssh.conf'), 'vm-metier', 'remote operation')
                run.assert_called_once()

    def test_partial_stopping_output_is_retried_until_success(self):
        transient = response(1, 'stopping', 'The object is not ready\nThe session is not locked')
        with patch.object(network, 'run', side_effect=[transient, response()]) as run, \
                patch.object(network.time, 'sleep'):
            self.assertEqual(network.info('vm-donnees')['VMState'], 'poweroff')
        self.assertEqual(run.call_count, 2)
        self.assertFalse(run.call_args.kwargs['check'])

    def test_console_unlock_transition_is_retried(self):
        transient = subprocess.CompletedProcess([], 1, '',
            'Failed to get a console object from the direct session (VBOX_E_INVALID_OBJECT_STATE)')
        with patch.object(network, 'run', side_effect=[transient, response()]) as run, \
                patch.object(network.time, 'sleep'):
            self.assertEqual(network.info('vm-metier')['VMState'], 'poweroff')
        self.assertEqual(run.call_count, 2)

    def test_nontransient_permission_error_is_not_hidden(self):
        error = response(1, error='Permission denied reading VM configuration')
        with patch.object(network, 'run', return_value=error) as run:
            with self.assertRaisesRegex(RuntimeError, 'Permission denied'):
                network.info('vm-donnees')
        run.assert_called_once()

    def test_transient_error_has_a_deadline(self):
        error = response(1, 'stopping', 'The object is not ready')
        with patch.object(network, 'run', return_value=error), \
                patch.object(network.time, 'monotonic', side_effect=[0, 0, 2]):
            with self.assertRaisesRegex(RuntimeError, 'Session VirtualBox indisponible'):
                network.info('vm-donnees', timeout=1)

    def test_command_timeout_has_a_clear_diagnostic(self):
        with patch.object(network, 'run', side_effect=subprocess.TimeoutExpired('VBoxManage', 1)):
            with self.assertRaisesRegex(RuntimeError, 'VirtualBox ne répond pas'):
                network.info('vm-donnees', timeout=1)

    def test_shutdown_waits_for_poweroff(self):
        with patch.object(network, 'info', side_effect=[{'VMState': 'stopping'}, {'VMState': 'poweroff'}]) as info, \
                patch.object(network.time, 'sleep'):
            network.wait_off('vm-donnees')
        self.assertEqual(info.call_count, 2)

    def test_successful_but_incomplete_output_is_rejected(self):
        with patch.object(network, 'run', return_value=subprocess.CompletedProcess([], 0, 'name="vm-donnees"', '')):
            with self.assertRaisesRegex(RuntimeError, 'sortie incomplète'):
                network.info('vm-donnees')


if __name__ == '__main__':
    unittest.main()
