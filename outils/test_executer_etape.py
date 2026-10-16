"""Exercise the step launcher in an isolated project with simulated tools."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


campaign = module('configurer_campagne')
calibration = module('resumer_etalonnage')


class StepLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'Intern'
        tools = self.root / 'outils'
        tools.mkdir(parents=True)
        for name in ('executer_etape.sh', 'preparer_vm.sh', 'demarrer_docker.sh'):
            shutil.copy2(TOOLS / name, tools / name)
        shutil.copytree(TOOLS / 'etapes', tools / 'etapes')
        self.binary = Path(self.temp.name) / 'bin'
        self.binary.mkdir()
        self.log = Path(self.temp.name) / 'calls'
        self.workspace = Path(self.temp.name) / 'VMs with spaces'
        (self.workspace / 'access').mkdir(parents=True)
        (self.workspace / 'access/ssh-etape8-interne.conf').touch()
        self.stub('VBoxManage', '''case "$1" in
--version) echo test ;;
showvminfo) printf 'VMState="running"\\nintnet1="intnet-app"\\nForwarding(0)="ssh-verification,tcp,127.0.0.1,2221,,22"\\n' ;;
list) test "$2" = runningvms && exit 0; echo vm ;;
*) exit 90 ;;
esac''')
        self.stub('docker', '''case "$1" in
info) echo 28.3.3 ;;
compose) if [[ " $* " == *" exec "* ]]; then printf 'username,password\\nalice,demo\\n'; fi ;;
ps) echo intern-mesure ;;
esac''')
        for name in ('python3', 'curl', 'ssh', 'java', 'jmeter', 'npm'):
            self.stub(name, 'exit 0')
        for name in ('etape10.md', 'mesures.md', 'exports-etape10.json'):
            self.write(f'deploiement/docs/{name}', 'saved evidence')
        self.write('mesure/ETAPE16.md', 'saved calibration')
        self.write('mesure/comptes.csv', 'old accounts')
        self.write('mesure/scripts/preparer_comptes.py', '# fixture')
        self.write('mesure/resultats/etape17/verification.json', '{}')
        self.env = dict(os.environ, HOME=self.temp.name, PATH=f'{self.binary}:/usr/bin:/bin',
                        TEST_LOG=str(self.log), VM_WORK=str(self.workspace),
                        DOCKER_BIN=str(self.binary / 'docker'), DOCKER_ENV_FILE=str(self.root / 'test.env'),
                        EXECUTION_ENGINE_CONFIG=str(self.root / 'absent.env'),
                        JMETER_BIN=str(self.binary / 'jmeter'))
        self.env.pop('EXECUTION_PROJECT', None)
        self.env.pop('EXECUTION_MESURE', None)
        (self.root / 'test.env').touch()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def stub(self, name, body):
        path = self.binary / name
        path.write_text('#!/bin/bash\nprintf "%s %s\\n" "$(basename "$0")" "$*" >> "$TEST_LOG"\n' + body + '\n')
        path.chmod(0o755)

    def run_step(self, *args, env=None):
        return subprocess.run(['bash', str(self.root / 'outils/executer_etape.sh'), *map(str, args)],
                              cwd=self.temp.name, env=env or self.env, capture_output=True, text=True, timeout=15)

    def calls(self):
        return self.log.read_text() if self.log.exists() else ''

    def test_invalid_actions_fail_without_starting_tools(self):
        for step in range(8, 19):
            with self.subTest(step=step):
                self.assertNotEqual(self.run_step(step, 'invalid').returncode, 0)
        self.assertEqual(self.calls(), '')

    def test_help_and_invalid_step_do_not_start_services(self):
        self.assertEqual(self.run_step('--help').returncode, 0)
        self.assertNotEqual(self.run_step(99).returncode, 0)
        self.assertEqual(self.calls(), '')

    def test_step10_stop_only_calls_shutdown_helper(self):
        result = self.run_step(10, 'arreter')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('python3 outils/arreter_vm.py', self.calls())
        self.assertNotIn('docker ', self.calls())
        self.assertNotIn('VBoxManage ', self.calls())

    def test_jmeter_install_checks_official_and_digest_only_manifests(self):
        import hashlib
        import io
        import tarfile
        archive = Path(self.temp.name) / 'fixture.tgz'
        with tarfile.open(archive, 'w:gz') as bundle:
            payload = b'#!/bin/sh\nexit 0\n'
            member = tarfile.TarInfo('apache-jmeter-5.6.3/bin/jmeter')
            member.size, member.mode = len(payload), 0o755
            bundle.addfile(member, io.BytesIO(payload))
        checksum = hashlib.sha512(archive.read_bytes()).hexdigest()
        manifest = Path(self.temp.name) / 'fixture.sha512'
        self.stub('curl', f'''case "$*" in
*.sha512) cp '{manifest}' apache-jmeter-5.6.3.tgz.sha512 ;;
*) cp '{archive}' apache-jmeter-5.6.3.tgz ;;
esac''')
        for index, content in enumerate((checksum + '  apache-jmeter-5.6.3.tgz\n', checksum + '\n', '0' * 128 + '\n')):
            with self.subTest(manifest=content[:15], index=index):
                manifest.write_text(content)
                executable = self.root / f'jmeter-{index}/apache-jmeter-5.6.3/bin/jmeter'
                env = dict(self.env, JMETER_BIN=str(executable))
                result = subprocess.run(['bash', '-ec', 'source outils/etapes/commun.sh; jmeter_ready'],
                                        cwd=self.root, env=env, capture_output=True, text=True, timeout=15)
                if index == 2:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(executable.exists())
                else:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertTrue(executable.exists())

    def test_reading_proofs_never_uses_docker_or_virtualbox(self):
        for step in (10, 14, 16, 17):
            with self.subTest(step=step):
                result = self.run_step(step)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('docker ', self.calls())
        self.assertNotIn('VBoxManage ', self.calls())
        self.assertNotIn('lancer17.py start', self.calls())

    def test_existing_vm_deployment_is_not_restarted_or_reinstalled(self):
        result = self.run_step(9)
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ('startvm', 'controlvm', 'clonevm', 'deployer_etape9.py', 'reseau_etape8.py'):
            self.assertNotIn(command, self.calls())
        self.assertLess(self.calls().index('vm-proxy true'), self.calls().index('vm-donnees true'))
        self.assertIn('systemctl is-active', self.calls())
        self.assertIn('8080/health/ready/', self.calls())

    def test_hanging_ssh_readiness_has_a_real_deadline(self):
        self.stub('ssh', 'sleep 30')
        result = self.run_step(9, env=dict(self.env, VM_SSH_WAIT_SECONDS='1'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SSH indisponible : vm-proxy après 1 s', result.stderr)

    def test_network_verification_is_explicit(self):
        self.assertEqual(self.run_step(8).returncode, 0)
        self.assertNotIn('--verifier', self.calls())
        result = self.run_step(8, 'verifier')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('reseau_etape8.py', self.calls())
        self.assertIn('--verifier', self.calls())

    def test_docker_steps_use_no_recreate_and_correct_layers(self):
        for step, layer in ((11, 'donnees'), (12, 'metier'), (13, 'proxy')):
            with self.subTest(step=step):
                result = self.run_step(step)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'--no-recreate --wait --wait-timeout 180 {layer}', self.calls())
        self.assertNotIn(' restart ', self.calls())
        self.assertNotIn(' down ', self.calls())

    def test_existing_exports_refuse_before_touching_vms(self):
        (self.workspace / 'exports-etape10').mkdir()
        result = self.run_step(10, 'mesurer')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Exports déjà présents', result.stderr)
        self.assertEqual(self.calls(), '')

    def test_existing_calibration_refuses_before_starting_services(self):
        result = self.run_step(16, 'mesurer', env=dict(self.env, MESURE16_OUTPUT=str(self.root / 'mesure')))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Résultats déjà présents', result.stderr)
        self.assertEqual(self.calls(), '')

    def test_cli_jmeter_uses_fresh_output_and_preserves_account_csv(self):
        output = self.root / 'mesure/resultats/new-run'
        result = self.run_step(15, 'cli', env=dict(self.env, MESURE15_OUTPUT=str(output)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'-l {output}/reussite.jtl', self.calls())
        self.assertIn(f'-l {output}/echec.jtl', self.calls())
        self.assertEqual(len(list((self.root / '.execution').glob('comptes-avant-*.csv'))), 1)
        retry = self.run_step(15, 'cli', env=dict(self.env, MESURE15_OUTPUT=str(output)))
        self.assertNotEqual(retry.returncode, 0)
        self.assertIn('Résultats déjà présents', retry.stderr)

    def test_offline_analysis_does_not_start_services(self):
        for name in ('python', 'pip'):
            path = self.write(f'.execution/analyse/bin/{name}', '#!/bin/bash\necho "analysis $*" >> "$TEST_LOG"\n')
            path.chmod(0o755)
        result = self.run_step(18)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('analyser18.py', self.calls())
        self.assertNotIn('docker ', self.calls())
        self.assertNotIn('VBoxManage ', self.calls())


class EvidenceProtectionTests(unittest.TestCase):
    def test_existing_campaign_configuration_is_never_silently_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'runtime': directory, 'output': str(Path(directory) / 'out')}
            campaign.save(config)
            path = Path(directory) / 'configuration.json'
            original = path.read_bytes()
            campaign.save(config)
            with self.assertRaisesRegex(SystemExit, 'Configuration existante différente'):
                campaign.save(dict(config, output=str(Path(directory) / 'other')))
            self.assertEqual(path.read_bytes(), original)

    def test_complete_or_active_campaign_cannot_be_restarted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'configuration.json').write_text(json.dumps({'output': directory}))
            (root / 'manifest.json').write_text(json.dumps({'status': 'complete'}))
            with self.assertRaisesRegex(SystemExit, 'déjà complète'):
                campaign.check_start(root)
            (root / 'controller.pid').write_text(str(os.getpid()))
            with self.assertRaisesRegex(SystemExit, 'déjà active'):
                campaign.check_start(root)

    def test_calibration_detects_different_controls_and_records_raw_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = dict.fromkeys(('mode', 'users', 'ramp_s', 'warmup_s', 'plateau_s', 'duration_s', 'port',
                                 'reflection_ms', 'source_plan_sha256', 'run_plan_sha256', 'accounts_sha256',
                                 'sql_schema_sha256', 'sql_data_sha256', 'seed_script_sha256', 'protocol_sha256', 'host'), 'same')
            base.update(exit_code=0, started_epoch_s=1700000000)
            for name in ('statique-1', 'statique-20', 'controle-1', 'controle-2'):
                path = root / name
                path.mkdir()
                (path / 'configuration.json').write_text(json.dumps(base))
                (path / 'synthese.json').write_text(json.dumps({'successful_throughput_rps': 100, 'p95_ms': 50, 'all_errors': 0}))
                (path / 'brut.csv').write_text('synthetic fixture')
            data = calibration.summarize(root)
            self.assertTrue(data['repeatability_criteria_passed'])
            self.assertEqual(len(data['raw_files_sha256']), 4)
            calibration.write_report(root, data)
            self.assertIn('2023-11-14', (root / 'rapport.md').read_text())
            path = root / 'controle-2/configuration.json'
            path.write_text(json.dumps(dict(base, accounts_sha256='different')))
            with self.assertRaisesRegex(ValueError, 'accounts_sha256'):
                calibration.summarize(root)


if __name__ == '__main__':
    unittest.main()
