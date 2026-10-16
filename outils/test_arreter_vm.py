"""Contrôler l'arrêt ACPI, la reprise et les refus avant mutation."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('stop_vm', Path(__file__).with_name('arreter_vm.py'))
stop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stop)


class StopTests(unittest.TestCase):
    def test_all_shutdown_requests_precede_waiting(self):
        events = []
        with patch.object(stop, 'info', return_value={'VMState': 'running'}), \
                patch.object(stop, 'vbox', side_effect=lambda *args: events.append(args)), \
                patch.object(stop, 'wait_off', side_effect=lambda name: events.append(('wait', name))):
            stop.main()
        self.assertEqual(events[:3], [('controlvm', name, 'acpipowerbutton')
                                     for name in ('vm-donnees', 'vm-metier', 'vm-proxy')])
        self.assertTrue(all(event[0] == 'wait' for event in events[3:]))

    def test_already_stopped_vms_are_preserved(self):
        with patch.object(stop, 'info', side_effect=[{'VMState': 'poweroff'}, {'VMState': 'aborted'}, {'VMState': 'running'}]), \
                patch.object(stop, 'vbox') as command, patch.object(stop, 'wait_off') as wait:
            stop.main()
        command.assert_called_once_with('controlvm', 'vm-proxy', 'acpipowerbutton')
        wait.assert_called_once_with('vm-proxy')

    def test_paused_vm_refuses_before_any_shutdown(self):
        with patch.object(stop, 'info', side_effect=[{'VMState': 'running'}, {'VMState': 'paused'}, {'VMState': 'running'}]), \
                patch.object(stop, 'vbox') as command:
            with self.assertRaisesRegex(SystemExit, 'paused'):
                stop.main()
        command.assert_not_called()

    def test_timeout_does_not_force_poweroff(self):
        with patch.object(stop, 'info', return_value={'VMState': 'running'}), \
                patch.object(stop, 'vbox') as command, \
                patch.object(stop, 'wait_off', side_effect=RuntimeError('Arrêt non confirmé')):
            with self.assertRaisesRegex(RuntimeError, 'non confirmé'):
                stop.main()
        self.assertEqual(command.call_count, 3)
        self.assertTrue(all(c.args[-1] == 'acpipowerbutton' for c in command.call_args_list))
