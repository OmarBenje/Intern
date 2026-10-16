"""Vérifier les refus avant mutation et la conservation des snapshots."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('reset_vm', Path(__file__).with_name('reinitialiser_vm.py'))
reset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset)


class ResetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('vm-proxy', 'vm-metier', 'vm-donnees'):
            folder = self.root / 'machines' / name
            folder.mkdir(parents=True)
            (folder / 'disk.vdi').touch()
            (folder / (name + '.vbox')).write_text(
                '<VirtualBox xmlns="http://www.virtualbox.org/">'
                f'<Machine name="{name}" uuid="{{{name}}}">'
                '<MediaRegistry><HardDisks><HardDisk location="disk.vdi"/></HardDisks></MediaRegistry>'
                '<Snapshot name="base propre" uuid="{base}"/>'
                '<Snapshot name="avant reseau" uuid="{old}"/>'
                '</Machine></VirtualBox>')

    def invoke(self, mock):
        with patch('sys.argv', ['reset', '--vm-work', str(self.root), '--base-propre']), \
                patch.object(reset, 'vbox', mock), contextlib.redirect_stdout(io.StringIO()):
            reset.main()

    def test_missing_disk_refuses_before_any_vbox_command(self):
        from unittest.mock import Mock
        (self.root / 'machines/vm-donnees/disk.vdi').unlink()
        command = Mock(return_value='')
        with self.assertRaises(SystemExit):
            self.invoke(command)
        command.assert_not_called()

    def test_running_vm_refuses_before_mutation(self):
        from unittest.mock import Mock
        command = Mock(return_value='"vm-proxy" {uuid}')
        with self.assertRaises(SystemExit):
            self.invoke(command)
        self.assertEqual(command.call_args_list, [unittest.mock.call('list', 'runningvms')])

    def test_missing_snapshot_refuses_before_any_vbox_command(self):
        from unittest.mock import Mock
        config = self.root / 'machines/vm-donnees/vm-donnees.vbox'
        config.write_text(config.read_text().replace('base propre', 'autre'))
        command = Mock(return_value='')
        with self.assertRaises(SystemExit):
            self.invoke(command)
        command.assert_not_called()

    def test_recovers_previous_configuration_without_deleting_disks(self):
        from unittest.mock import Mock
        target = self.root / 'machines/vm-metier/vm-metier.vbox'
        backup = target.with_suffix('.vbox-prev')
        target.rename(backup)
        command = Mock(return_value='')
        self.invoke(command)
        self.assertEqual(target.read_bytes(), backup.read_bytes())
        calls = [c.args for c in command.call_args_list]
        self.assertIn(('unregistervm', '{vm-metier}'), calls)
        self.assertIn(('registervm', str(target)), calls)
        self.assertTrue((target.parent / 'disk.vdi').exists())

    def test_backup_precedes_restore_and_archive_names_do_not_match_step_names(self):
        from unittest.mock import Mock
        command = Mock(return_value='')
        self.invoke(command)
        calls = [c.args for c in command.call_args_list]
        for name in ('vm-proxy', 'vm-metier', 'vm-donnees'):
            take = next(i for i,c in enumerate(calls) if c[:3] == ('snapshot', name, 'take'))
            restore = calls.index(('snapshot', name, 'restore', 'base propre'))
            self.assertLess(take, restore)
            edit = next(c for c in calls if c[:3] == ('snapshot', name, 'edit'))
            self.assertNotIn('avant reseau', edit[-1])
        self.assertFalse(any('delete' in c or 'deletevm' in c for c in calls))


if __name__ == '__main__':
    unittest.main()
