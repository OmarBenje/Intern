"""Campaign resource isolation and failure recovery, without Docker or VMs."""

import argparse
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import campagnes17 as campaign
import lancer17 as launcher


def result(stdout=b'', code=0, stderr=b''):
    return subprocess.CompletedProcess([], code, stdout, stderr)


class CampaignSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.measure = self.root / 'Intern/mesure'
        self.measure.mkdir(parents=True)
        # Hash checks use the real protocol and plan; output stays isolated.
        (self.measure / 'plan.jmx').write_bytes((campaign.ROOT / 'plan.jmx').read_bytes())
        self.root_patch = patch.object(campaign, 'ROOT', self.measure)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.env = self.root / 'docker.env'
        self.env.write_text('POSTGRES_USER=intern_user\nPOSTGRES_DB=intern\n')

    def controller(self, name='runtime'):
        args = argparse.Namespace(runtime=self.root / name,
            output=self.measure / name, docker='docker', docker_host='unix:///test',
            docker_config=self.root, env_file=self.env, ssh_config=self.root / 'ssh.conf',
            jmeter='jmeter', reference_project='intern-docker')
        return campaign.Campaigns(args)

    def ready(self, controller):
        controller.dc = Mock(return_value=result())
        controller.run = Mock(return_value=result())
        controller.vm_state = Mock(return_value='running')
        controller.vm_info = Mock(return_value='')
        controller.docker = Mock(side_effect=lambda *parts, **kw:
            result(code=1) if parts[:2] == ('volume', 'inspect') else result())

    def test_new_runtimes_have_distinct_projects_and_legacy_resume_keeps_name(self):
        first, second = self.controller(), self.controller('second')
        self.assertNotEqual(first.project, second.project)
        self.ready(first)
        first.preflight()
        self.assertEqual(first.project, self.controller().project)
        first.owner_path.rename(first.runtime / 'previous-project.json')
        self.assertNotEqual(first.project, self.controller().project)
        (second.runtime / 'base.sql').touch()
        self.assertEqual(self.controller('second').project, campaign.PROJECT)

    def test_conflict_fails_before_stopping_services_or_restoring_vms(self):
        controller = self.controller()
        self.ready(controller)
        controller.dc.return_value = result(b'existing-container\n')
        controller.bootstrap = Mock()
        controller.restore_vm = Mock()
        with self.assertRaisesRegex(RuntimeError, 'sans propriétaire'):
            controller.main()
        controller.run.assert_not_called()
        controller.bootstrap.assert_not_called()
        controller.restore_vm.assert_not_called()
        self.assertEqual([call.args for call in controller.dc.call_args_list], [('ps', '-a', '-q')])
        self.assertFalse(controller.owner_path.exists())
        self.assertIn('sans propriétaire', controller.manifest['error'])

    def test_volume_conflict_also_preserves_resources(self):
        controller = self.controller()
        self.ready(controller)
        controller.docker = Mock(return_value=result())
        with self.assertRaisesRegex(RuntimeError, 'Volume Docker'):
            controller.main()
        controller.run.assert_not_called()
        self.assertFalse(controller.owner_path.exists())

    def test_failed_rest_is_not_skipped_on_restart(self):
        controller = self.controller()
        self.ready(controller)
        events = [dict(action='cooldown_start', path='repos/serie-1/docker/1'),
                  dict(action='campaigns_failed')]
        (controller.output / 'journal.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
        with self.assertRaisesRegex(RuntimeError, 'Repos non validé'):
            controller.main()
        controller.run.assert_not_called()
        controller.dc.assert_not_called()

    def test_completed_rest_allows_restart_validation(self):
        controller = self.controller()
        events = [dict(action='cooldown_start', path='repos/serie-1/docker/1'),
                  dict(action='cooldown_complete', path='repos/serie-1/docker/1')]
        (controller.output / 'journal.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
        controller.check_previous_rests()

    def test_owned_partial_preparation_can_resume_without_adopting_legacy_project(self):
        controller = self.controller()
        self.ready(controller)
        controller.preflight()
        resumed = self.controller()
        self.ready(resumed)
        resumed.dc.return_value = result(b'owned-container')
        resumed.preflight()
        resumed.dc.assert_not_called()
        self.assertEqual(controller.project, resumed.project)
        self.assertNotEqual(resumed.project, campaign.PROJECT)

    def test_foreign_port_owner_is_rejected_before_services_are_stopped(self):
        controller = self.controller()
        self.ready(controller)
        def docker(*parts, **kw):
            if parts[:2] == ('volume', 'inspect'):
                return result(code=1)
            return result(b'abc unrelated-project\n')
        controller.docker.side_effect = docker
        with self.assertRaisesRegex(RuntimeError, 'Port 8081'):
            controller.main()
        controller.run.assert_not_called()
        self.assertFalse(controller.owner_path.exists())

    def test_calibration_containers_are_stopped_then_restored_after_bootstrap_failure(self):
        controller = self.controller()
        self.ready(controller)
        def docker(*parts, **kw):
            if parts[:2] == ('volume', 'inspect'):
                return result(code=1)
            if 'publish=8081' in parts:
                return result(b'abc intern-mesure\n')
            if 'label=com.docker.compose.project=intern-mesure' in parts:
                return result(b'abc\ndef\n')
            return result()
        controller.docker.side_effect = docker
        controller.bootstrap = Mock(side_effect=RuntimeError('bootstrap failed'))
        with self.assertRaisesRegex(RuntimeError, 'bootstrap failed'):
            controller.main()
        controller.docker.assert_any_call('stop', 'abc', 'def')
        controller.docker.assert_any_call('start', 'abc', 'def')
        self.assertEqual(controller.run.call_count, 2)

    def test_vm_cleanup_error_does_not_skip_reference_or_hide_primary_error(self):
        controller = self.controller()
        self.ready(controller)
        controller.preflight = Mock()
        def fail_bootstrap():
            controller.vm_touched = True
            raise RuntimeError('original error')
        controller.bootstrap = fail_bootstrap
        controller.restore_vm = Mock(side_effect=RuntimeError('VM locked'))
        with self.assertRaisesRegex(RuntimeError, '^original error$'):
            controller.main()
        self.assertEqual(controller.run.call_count, 2)
        self.assertIn('VM locked', controller.manifest['restoration_errors'][0])
        self.assertEqual(controller.manifest['status'], 'failed')
        self.assertEqual(controller.manifest['error'], 'original error')

    @patch.object(campaign.time, 'sleep')
    def test_virtualbox_transient_lock_is_retried(self, sleep):
        controller = self.controller()
        controller.run = Mock(side_effect=[result(code=1, stderr=b'VBOX_E_INVALID_OBJECT_STATE'),
                                           result(b'VMState="poweroff"\n')])
        self.assertEqual(controller.vm_state('proxy'), 'poweroff')
        self.assertEqual(controller.run.call_count, 2)
        sleep.assert_called_once_with(2)

    @patch.object(campaign.time, 'sleep')
    def test_persistent_virtualbox_lock_has_bounded_retries(self, sleep):
        controller = self.controller()
        controller.run = Mock(return_value=result(code=1, stderr=b'VBOX_E_INVALID_OBJECT_STATE'))
        with self.assertRaisesRegex(RuntimeError, 'Cannot read vm-proxy'):
            controller.vm_state('proxy')
        self.assertEqual(controller.run.call_count, 6)
        self.assertEqual((controller.runtime / 'last-error.txt').read_bytes(), b'VBOX_E_INVALID_OBJECT_STATE')

    def test_failed_status_displays_log_without_running_external_commands(self):
        controller = self.controller()
        controller.manifest.update(status='failed', error='original error',
                                   restoration_errors=['VM locked'])
        controller.manifest_path.write_text(json.dumps(controller.manifest))
        (controller.runtime / 'configuration.json').write_text(json.dumps({'output': str(controller.output)}))
        (controller.runtime / 'controller.log').write_text('original traceback\n')
        output = io.StringIO()
        with patch.object(sys, 'argv', ['lancer17.py', 'status', '--runtime', str(controller.runtime)]), \
             patch.object(launcher.subprocess, 'run') as run, \
             patch.object(launcher.subprocess, 'Popen') as spawn, contextlib.redirect_stdout(output):
            launcher.main()
        run.assert_not_called()
        spawn.assert_not_called()
        for message in ('original error', 'VM locked', 'original traceback', 'controller.log'):
            self.assertIn(message, output.getvalue())

    def test_failed_preflight_never_starts_background_controller(self):
        controller = self.controller()
        (controller.runtime / 'configuration.json').write_text(json.dumps({'output': str(controller.output)}))
        with patch.object(sys, 'argv', ['lancer17.py', 'start', '--runtime', str(controller.runtime)]), \
             patch.object(launcher.subprocess, 'run', return_value=result(code=1)), \
             patch.object(launcher.subprocess, 'Popen') as spawn, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                launcher.main()
        spawn.assert_not_called()
        self.assertFalse((controller.runtime / 'controller.pid').exists())

    def test_running_status_does_not_display_errors_from_previous_attempt(self):
        controller = self.controller()
        controller.manifest.update(status='running', error='old error', restoration_errors=['old restoration'])
        controller.manifest_path.write_text(json.dumps(controller.manifest))
        (controller.runtime / 'configuration.json').write_text(json.dumps({'output': str(controller.output)}))
        output = io.StringIO()
        with patch.object(sys, 'argv', ['lancer17.py', 'status', '--runtime', str(controller.runtime)]), contextlib.redirect_stdout(output):
            launcher.main()
        self.assertNotIn('old error', output.getvalue())
        self.assertNotIn('old restoration', output.getvalue())

    def test_equivalent_nat_rule_is_reused_regardless_of_name(self):
        existing = ['ssh-verification,tcp,127.0.0.1,2221,,22']
        self.assertFalse(campaign.Campaigns.nat_rule_needed(campaign.NAT_RULES[0], existing))

    def test_incompatible_nat_target_or_wildcard_bind_is_rejected(self):
        for current in ('other,tcp,127.0.0.1,2221,,80', 'other,tcp,,2221,,22',
                        'ssh-mesure17,tcp,127.0.0.1,5555,,22'):
            with self.subTest(rule=current), self.assertRaisesRegex(RuntimeError, 'NAT incompatible'):
                campaign.Campaigns.nat_rule_needed(campaign.NAT_RULES[0], [current])

    def test_boot_and_stop_preserve_borrowed_nat_rule(self):
        controller = self.controller()
        self.ready(controller)
        info = 'Forwarding(0)="ssh-verification,tcp,127.0.0.1,2221,,22"\n'
        controller.vm_info.return_value = info
        controller.ssh = Mock(return_value=result())
        controller.boot_vm()
        added = [call.args[0] for call in controller.run.call_args_list]
        self.assertEqual(added, [['VBoxManage', 'controlvm', 'vm-proxy', 'natpf2', campaign.NAT_RULES[1]]])
        controller.vm_state.return_value = 'poweroff'
        controller.vm_info.return_value = info + 'Forwarding(1)="' + campaign.NAT_RULES[1] + '"\n'
        controller.run.reset_mock()
        controller.stop_vm()
        controller.run.assert_called_once_with(['VBoxManage', 'modifyvm', 'vm-proxy', '--natpf2', 'delete', 'http-mesure17'])
        self.assertEqual(json.loads(controller.nat_path.read_text()), [])

    def test_shutdown_uses_acpi_without_ssh(self):
        controller = self.controller()
        self.ready(controller)
        controller.vm_state.side_effect = ['running'] * 3 + ['poweroff'] * 3
        controller.ssh = Mock(side_effect=AssertionError('SSH must not be needed'))
        controller.stop_vm()
        commands = [call.args[0] for call in controller.run.call_args_list]
        self.assertEqual(commands, [['VBoxManage', 'controlvm', f'vm-{name}', 'acpipowerbutton']
                                    for name in ('metier', 'donnees', 'proxy')])
        controller.ssh.assert_not_called()

    @patch.object(campaign.time, 'sleep')
    def test_boot_waits_after_an_individual_ssh_timeout(self, sleep):
        controller = self.controller()
        self.ready(controller)
        controller.vm_info.return_value = '\n'.join(f'Forwarding({i})="{rule}"' for i, rule in enumerate(campaign.NAT_RULES))
        controller.ssh = Mock(side_effect=[subprocess.TimeoutExpired('ssh', 10), result(), result(), result()])
        controller.boot_vm()
        self.assertEqual(controller.ssh.call_count, 4)
        sleep.assert_called_once_with(3)

    @patch.object(campaign.time, 'sleep')
    @patch.object(campaign.time, 'monotonic', side_effect=[0, 0, 5, 10, 10])
    def test_acpi_is_repeated_if_guest_does_not_handle_first_request(self, monotonic, sleep):
        controller = self.controller()
        self.ready(controller)
        controller.vm_state.side_effect = ['running'] * 6 + ['poweroff'] * 3
        controller.stop_vm()
        commands = [call.args[0] for call in controller.run.call_args_list]
        self.assertEqual(len(commands), 6)
        self.assertTrue(all(command[-1] == 'acpipowerbutton' for command in commands))


if __name__ == '__main__':
    unittest.main()
