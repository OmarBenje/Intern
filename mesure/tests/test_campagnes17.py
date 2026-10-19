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
        controller.updates = Mock(touched=set())
        controller.dc = Mock(return_value=result())
        controller.run = Mock(return_value=result())
        controller.vm_state = Mock(return_value='running')
        controller.vm_info = Mock(return_value='')
        controller.docker = Mock(side_effect=lambda *parts, **kw:
            result(code=1) if parts[:2] == ('volume', 'inspect') else result())

    def test_failed_collector_names_service_and_preserves_diagnostic(self):
        controller = self.controller()
        folder = controller.output / 'serie-1/vm/5'
        folder.mkdir(parents=True)
        diagnostic = controller.runtime / 'proxy.log'
        diagnostic.write_text('Service root process disappeared (PID 123)')
        with (folder / 'serveur-proxy.jsonl').open('w') as stream, diagnostic.open('a') as errors:
            controller.collectors = [(Mock(poll=Mock(return_value=1)), stream, errors)]
            with self.assertRaisesRegex(RuntimeError, 'proxy.*exit 1.*proxy.log'):
                controller.check_collectors(folder)
        recorded = json.loads((folder / 'collecteurs-echec.json').read_text())
        self.assertEqual(recorded['collectors'][0]['service'], 'proxy')
        self.assertEqual(controller.manifest['collector_errors'], recorded['collectors'])
        self.assertIn('PID 123', diagnostic.read_text())

    def test_new_collector_does_not_overwrite_previous_plateau_logs(self):
        controller = self.controller()
        controller.ssh = Mock(return_value=result(b'123'))
        first = controller.output / 'serie-1/vm/1'
        second = controller.output / 'serie-1/vm/5'
        first.mkdir(parents=True)
        second.mkdir(parents=True)
        with patch.object(campaign.subprocess, 'Popen'):
            controller.collect('vm', first)
            path = Path(controller.collectors[0][2].name)
            controller.collectors[0][2].write('Original proxy diagnostic')
            controller.stop_collectors()
            controller.collect('vm', second)
            self.assertNotEqual(path, Path(controller.collectors[0][2].name))
            controller.stop_collectors()
        self.assertEqual(path.read_text(), 'Original proxy diagnostic')

    def test_bootstrap_and_resume_do_not_publish_the_vm_measurement_port(self):
        controller = self.controller()
        controller.pg_user = 'intern_user'
        controller.accounts.write_text('username,password,application_id\nmesure01,fake,1\n')
        (self.measure / 'scripts').mkdir()
        (self.measure / 'scripts/preparer_comptes.py').write_text('# Input to the mocked Django shell\n')
        created = set()
        def dc(*parts, **kwargs):
            if parts[0] == 'up':
                # Model a live VM occupying 8081: a broad up would fail here.
                self.assertEqual(parts[-2:], ('donnees', 'metier'))
                self.assertNotIn('proxy', parts)
            if parts[0] == 'create':
                self.assertEqual(parts, ('create', '--no-build', 'proxy'))
                created.add('proxy')
            if 'shell' in parts:
                return result(controller.accounts.read_bytes())
            if 'pg_dump' in parts:
                return result(b'-- dedicated fixture database\n')
            if '-c' in parts:
                return result(b'{"python":"test"}')
            return result()
        def docker(*parts, **kwargs):
            if parts[0] == 'cp':
                if '-proxy-1:' in parts[1]:
                    self.assertIn('proxy', created)
                target = Path(parts[2])
                target.mkdir()
                (target / 'asset.txt').write_text('fixture')
                return result()
            images = [{'Config': {'Labels': {'com.docker.compose.service': service}},
                       'Image': 'image-' + service, 'HostConfig': {'NanoCpus': 0, 'Memory': 0}}
                      for service in campaign.SERVICES]
            return result(json.dumps(images).encode())
        controller.dc = Mock(side_effect=dc)
        controller.docker = Mock(side_effect=docker)
        controller.stop_vm = Mock()
        controller.bootstrap()
        self.assertTrue((controller.runtime / 'base.sql').exists())
        self.assertTrue((controller.runtime / 'sources.tar').exists())
        controller.stop_vm.assert_not_called()
        # A resumed snapshot also starts only the private services for versions.
        controller.dc.reset_mock()
        controller.bootstrap()
        self.assertFalse(any(call.args[0] == 'create' for call in controller.dc.call_args_list))
        self.assertEqual(sum(call.args[0] == 'up' for call in controller.dc.call_args_list), 1)

    def test_update_guard_status_uses_events_instead_of_assuming_activation(self):
        controller = self.controller()
        self.assertEqual(launcher.update_guard_status(controller.output), 'protection pas encore activée')
        journal = controller.output / 'journal.jsonl'
        journal.write_text(json.dumps(dict(action='updates_paused', service='proxy')) + '\n')
        self.assertEqual(launcher.update_guard_status(controller.output), 'protection active pour proxy')
        with journal.open('a') as stream:
            stream.write(json.dumps(dict(action='updates_restored', service='proxy')) + '\n')
            stream.write('{"action":')  # Concurrent partial write must not break status.
        self.assertEqual(launcher.update_guard_status(controller.output), 'politique initiale restaurée')

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
        incident = json.loads((controller.output / 'incident.json').read_text())
        self.assertEqual(incident['message'], 'original error')
        self.assertIn('VM locked', incident['restoration_errors'][0])

    def test_capacity_cleanup_releases_networks_without_removing_volumes(self):
        controller = self.controller()
        self.ready(controller)
        controller.measurement_touched = True
        controller.manifest['kind'] = 'capacity'
        controller.restore()
        self.assertEqual(controller.dc.call_args_list[-1].args, ('down', '--timeout', '30'))
        self.assertEqual(controller.dc.call_args_list[-1].kwargs, dict(timeout=90))

    def test_docker_logs_are_archived_before_capacity_container_removal(self):
        controller = self.controller()
        self.ready(controller)
        controller.measurement_touched = True
        controller.manifest['kind'] = 'capacity'
        controller.dc = Mock(side_effect=lambda *parts, **kw: result(b'abc123\n') if parts[0] == 'ps' else result())
        controller.docker = Mock(return_value=result(b'application message\n', stderr=b'stderr diagnostic\n'))
        controller.restore()
        archive = controller.runtime / controller.manifest['docker_log_archives'][0]
        self.assertEqual(archive.read_text(), 'application message\nstderr diagnostic\n')
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
        controller.docker.assert_called_once_with('logs', '--timestamps', 'abc123', check=False)
        self.assertEqual(controller.dc.call_args_list[-1].args[0], 'down')

    def test_log_archival_failure_cannot_block_docker_cleanup(self):
        controller = self.controller()
        self.ready(controller)
        controller.measurement_touched = True
        controller.manifest['kind'] = 'capacity'
        controller.archive_measurement_logs = Mock(side_effect=OSError('disk full'))
        controller.restore()
        controller.dc.assert_called_once_with('down', '--timeout', '30', timeout=90)
        self.assertIn('disk full', controller.manifest['diagnostic_errors'][0])

    def test_failure_at_each_campaign_phase_always_attempts_restoration(self):
        for phase in ('preflight', 'bootstrap', 'boot_vm', 'prepare_vm', 'campaign', 'stop_vm'):
            with self.subTest(phase=phase):
                controller = self.controller('failure-' + phase)
                self.ready(controller)
                for name in ('preflight', 'bootstrap', 'boot_vm', 'prepare_vm', 'campaign', 'stop_vm', 'restore'):
                    setattr(controller, name, Mock())
                getattr(controller, phase).side_effect = RuntimeError('injected ' + phase)
                with self.assertRaisesRegex(RuntimeError, 'injected ' + phase):
                    controller.main()
                controller.restore.assert_called_once_with()
                self.assertEqual(controller.manifest['status'], 'failed')
                self.assertEqual(controller.manifest['error'], 'injected ' + phase)
                incident = json.loads((controller.output / 'incident.json').read_text())
                self.assertEqual(incident['message'], 'injected ' + phase)

    def test_full_diagnostic_disk_does_not_skip_restore_or_mask_initial_error(self):
        controller = self.controller()
        self.ready(controller)
        controller.preflight = Mock(side_effect=RuntimeError('original cause'))
        controller.record_incident = Mock(side_effect=OSError('disk full'))
        controller.restore = Mock()
        with self.assertRaisesRegex(RuntimeError, '^original cause$'):
            controller.main()
        controller.restore.assert_called_once_with()

    def test_requested_stop_records_stopped_and_still_restores(self):
        controller = self.controller()
        self.ready(controller)
        controller.preflight = Mock(side_effect=InterruptedError('Graceful stop requested'))
        controller.restore = Mock()
        with self.assertRaises(InterruptedError):
            controller.main()
        controller.restore.assert_called_once_with()
        self.assertEqual(controller.manifest['status'], 'stopped')
        self.assertEqual(json.loads((controller.output / 'incident.json').read_text())['type'], 'InterruptedError')

    def test_missing_manifest_does_not_claim_preparation_when_controller_has_exited(self):
        controller = self.controller()
        (controller.runtime / 'configuration.json').write_text(json.dumps({'output': str(controller.output)}))
        (controller.runtime / 'controller.pid').write_text('123')
        (controller.runtime / 'controller.log').write_text('startup failure diagnostic')
        for active in (False, True):
            output = io.StringIO()
            with patch.object(sys, 'argv', ['lancer17.py', 'status', '--runtime', str(controller.runtime)]), \
                    patch.object(launcher, 'alive', return_value=active), contextlib.redirect_stdout(output):
                launcher.main()
            if active:
                self.assertIn('Préparation en cours', output.getvalue())
            else:
                self.assertNotIn('Préparation en cours', output.getvalue())
                self.assertIn('Contrôleur inactif', output.getvalue())
                self.assertIn('startup failure diagnostic', output.getvalue())

    def test_restored_status_identifies_old_port_error_as_archived(self):
        controller = self.controller()
        controller.manifest.update(status='failed', error='injector_cpu_pct_sustained',
                                   progress=dict(action='reference_restored'))
        controller.manifest_path.write_text(json.dumps(controller.manifest))
        (controller.runtime / 'configuration.json').write_text(json.dumps({'output': str(controller.output)}))
        (controller.runtime / 'last-error.txt').write_text('8080: bind: address already in use')
        output = io.StringIO()
        with patch.object(sys, 'argv', ['lancer17.py', 'status', '--runtime', str(controller.runtime)]), \
                contextlib.redirect_stdout(output):
            launcher.main()
        self.assertIn('Restauration : confirmée', output.getvalue())
        self.assertIn('Diagnostic de commande archivé, antérieur', output.getvalue())
        self.assertIn('8080: bind', output.getvalue())
        self.assertIn('injector_cpu_pct_sustained', output.getvalue())

    def test_completed_status_still_displays_failure_to_archive_diagnostics(self):
        controller = self.controller()
        controller.manifest.update(status='complete', diagnostic_errors=['Docker logs: disk full'])
        controller.manifest_path.write_text(json.dumps(controller.manifest))
        (controller.runtime / 'configuration.json').write_text(json.dumps({'output': str(controller.output)}))
        output = io.StringIO()
        with patch.object(sys, 'argv', ['lancer17.py', 'status', '--runtime', str(controller.runtime)]), \
                contextlib.redirect_stdout(output):
            launcher.main()
        self.assertIn('Docker logs: disk full', output.getvalue())

    def test_resumable_campaign_cleanup_keeps_containers_and_networks(self):
        controller = self.controller()
        self.ready(controller)
        controller.measurement_touched = True
        controller.restore()
        controller.dc.assert_called_once_with('stop')

    @patch.object(campaign.time, 'sleep')
    def test_virtualbox_transient_lock_is_retried(self, sleep):
        controller = self.controller()
        controller.run = Mock(side_effect=[result(code=1, stderr=b'VBOX_E_INVALID_OBJECT_STATE'),
                                           result(b'VMState="poweroff"\n')])
        self.assertEqual(controller.vm_state('proxy'), 'poweroff')
        self.assertEqual(controller.run.call_count, 2)
        sleep.assert_called_once_with(2)

    @patch.object(campaign.time, 'sleep')
    def test_shutdown_usb_session_error_is_retried(self, sleep):
        controller = self.controller()
        error = b'The object is not ready; E_ACCESSDENIED; COMGETTER(RemoteUSBDevices)'
        controller.run = Mock(side_effect=[result(code=1, stderr=error),
                                           result(b'VMState="poweroff"\n')])
        self.assertEqual(controller.vm_state('donnees'), 'poweroff')
        self.assertEqual(controller.run.call_count, 2)
        sleep.assert_called_once_with(2)

    def test_real_access_denial_is_not_retried(self):
        controller = self.controller()
        controller.run = Mock(return_value=result(code=1, stderr=b'E_ACCESSDENIED: permission denied'))
        with self.assertRaisesRegex(RuntimeError, 'Cannot read vm-donnees'):
            controller.vm_state('donnees')
        self.assertEqual(controller.run.call_count, 1)

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
        for message in ('original error', 'VM locked', 'original traceback', 'controller.log', 'Restauration : non confirmée'):
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

    def test_preflight_failure_is_documented_before_detached_start(self):
        controller = self.controller()
        controller.preflight = Mock(side_effect=RuntimeError('foreign port owner'))
        with self.assertRaisesRegex(RuntimeError, 'foreign port owner'):
            controller.preflight_only()
        incident = json.loads((controller.output / 'incident.json').read_text())
        self.assertEqual(incident['phase'], 'preflight')
        self.assertEqual(incident['message'], 'foreign port owner')
        self.assertEqual(controller.manifest['status'], 'failed')
        self.assertEqual(controller.manifest['progress']['action'], 'preflight_failed')
        self.assertFalse(controller.reference_touched)
        self.assertFalse(controller.vm_touched)

    def test_lock_refusal_does_not_claim_failed_restoration(self):
        controller = self.controller()
        controller.manifest.update(status='failed', error='Mesure déjà active',
                                   progress=dict(action='campaigns_refused'))
        controller.manifest_path.write_text(json.dumps(controller.manifest))
        (controller.runtime / 'configuration.json').write_text(json.dumps({'output': str(controller.output)}))
        output = io.StringIO()
        with patch.object(sys, 'argv', ['lancer17.py', 'status', '--runtime', str(controller.runtime)]), \
                contextlib.redirect_stdout(output):
            launcher.main()
        self.assertIn('sans objet : contrôleur refusé avant modification', output.getvalue())
        self.assertNotIn('non confirmée', output.getvalue())
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

    def test_shutdown_race_accepts_confirmed_stopping_state(self):
        controller = self.controller()
        controller.vm_state = Mock(return_value='stopping')
        # Exercise the real command wrapper, including its private diagnostic.
        with patch.object(campaign.subprocess, 'run', return_value=result(
                code=1, stderr=b'Invalid machine state: Stopping')):
            controller.request_vm_shutdown('metier')
        self.assertEqual(len(controller.manifest['command_errors']), 1)

    def test_shutdown_command_failure_while_running_still_raises(self):
        controller = self.controller()
        controller.vm_state = Mock(return_value='running')
        with patch.object(campaign.subprocess, 'run', return_value=result(
                code=1, stderr=b'Permission denied')):
            with self.assertRaises(RuntimeError):
                controller.request_vm_shutdown('metier')

    def test_failed_ssh_recovery_still_attempts_acpi_shutdown(self):
        controller = self.controller()
        self.ready(controller)
        controller.updates.touched = {'proxy', 'metier', 'donnees'}
        controller.vm_state.return_value = 'poweroff'
        controller.boot_vm = Mock(side_effect=subprocess.TimeoutExpired('ssh', 10))
        controller.stop_vm = Mock()
        with self.assertRaises(subprocess.TimeoutExpired):
            controller.restore_vm()
        controller.stop_vm.assert_called_once_with()

    @patch.object(campaign.time, 'sleep')
    def test_real_command_timeout_still_reaches_ssh_boot_retry(self, sleep):
        controller = self.controller()
        controller.vm_state = Mock(return_value='running')
        controller.vm_info = Mock(return_value='\n'.join(
            f'Forwarding({i})="{rule}"' for i, rule in enumerate(campaign.NAT_RULES)))
        controller.dc = Mock()
        controller.updates = Mock()
        with patch.object(campaign.subprocess, 'run', side_effect=[
                subprocess.TimeoutExpired('ssh', 10), result(), result(), result()]):
            controller.boot_vm(restoring=True)
        sleep.assert_called_once_with(3)
        self.assertEqual(len(controller.manifest['command_errors']), 1)
        self.assertEqual(controller.updates.pause.call_count, 3)

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
