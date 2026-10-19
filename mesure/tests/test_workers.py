"""Worker comparison ordering, isolated overrides and cautious report conclusions."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from workers import WorkerCampaign, WorkerCalibrationUnavailable, ORDER, LEVELS, command_for, write_report


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.policy = dict(p95_max_ms=1000, erreurs_max_pct=1, ecart_repetitions_max_pct=10)

    def sample(self, series, workers, users, valid=True, errors=0):
        name = f'serie-{series}-workers-{workers}/docker/{users}'
        folder = self.output / name
        folder.mkdir(parents=True)
        (folder / 'synthese.json').write_text(json.dumps(dict(
            plateau_valid=valid, p95_ms=100, error_pct=0,
            successful_throughput_rps=100 if workers == 2 else 120, all_errors=errors)))
        return dict(path=name, workers=workers, repetition=series, users=users)

    def controller(self):
        c = WorkerCampaign.__new__(WorkerCampaign)
        c.deployment = 'docker'
        c.levels = LEVELS
        c.output = self.output
        c.runtime = self.output
        c.manifest_path = self.output / 'manifest.json'
        c.manifest = dict(runs=[], images={s: 'sha256:' + s for s in ('proxy', 'metier', 'donnees')})
        c.policy = self.policy
        c.suspended_containers = []
        c.reference = ['docker', 'compose']
        c.compose = ['docker', 'compose']
        for method in ('preflight', 'run', 'bootstrap', 'check_stop', 'reset', 'verify_configuration',
                       'cooldown', 'event', 'dc'):
            setattr(c, method, Mock())
        return c

    def test_balanced_order_and_same_loads_with_resets(self):
        c = self.controller()
        def measure(dep, name, users):
            series, workers = map(int, name.split('-workers-'))
            c.manifest['runs'].append(self.sample(series, workers, users))
        c.measure = Mock(side_effect=measure)
        c.resume_work()
        self.assertEqual(c.manifest['status'], 'complete')
        self.assertEqual(c.reset.call_count, 4)
        self.assertEqual([(r['repetition'], r['workers'], r['users']) for r in c.manifest['runs']],
                         [(s, w, n) for s, w in ORDER for n in LEVELS])
        self.assertEqual(c.compose.count('-f'), 1)
        overlay = json.loads((self.output / 'workers.json').read_text())
        self.assertEqual(overlay['services']['metier']['command'], command_for(2))
        self.assertEqual(overlay['services']['donnees'], {'image': 'sha256:donnees'})

    def test_custom_loads_are_used_in_all_four_blocks_and_report(self):
        c = self.controller()
        c.levels = (100, 130)
        c.manifest.update(worker_levels=list(c.levels))
        def measure(dep, name, users):
            series, workers = map(int, name.split('-workers-'))
            c.manifest['runs'].append(self.sample(series, workers, users))
        c.measure = Mock(side_effect=measure)
        c.resume_work()
        self.assertEqual([r['users'] for r in c.manifest['runs']], [100, 130] * 4)
        (self.output / 'protocole.json').write_text('{}')
        (self.output / 'manifest.json').write_text(json.dumps(c.manifest))
        write_report(self.output, c.manifest, c.policy)
        report = (self.output / 'rapport-workers.md').read_text()
        self.assertIn('Charges : 100, 130 utilisateurs', report)
        self.assertNotIn('200 utilisateurs', report)

    def test_invalid_plateau_cancels_higher_loads(self):
        c = self.controller()
        c.measure = Mock(side_effect=lambda dep, name, users: c.manifest['runs'].append(
            self.sample(1, 2, users, valid=False)))
        with self.assertRaisesRegex(RuntimeError, 'higher loads cancelled'):
            c.resume_work()
        self.assertEqual(c.measure.call_count, 1)

    def test_reports_only_reproducible_error_free_pairs(self):
        runs = [self.sample(s, w, n) for s, w in ORDER for n in LEVELS]
        # A failed load must not be interpreted as a performance improvement.
        f = self.output / runs[-1]['path'] / 'synthese.json'
        data = json.loads(f.read_text())
        data.update(plateau_valid=False, p95_ms=None)
        f.write_text(json.dumps(data))
        manifest = dict(status='complete', runs=runs)
        for filename, value in [('manifest.json', manifest), ('protocole.json', {})]:
            (self.output / filename).write_text(json.dumps(value))
        write_report(self.output, manifest, self.policy)
        report = (self.output / 'rapport-workers.md').read_text()
        self.assertIn('+20.0 % et +20.0 %', report)
        self.assertIn('200 utilisateurs : comparaison non concluante', report)
        self.assertEqual(len((self.output / 'comparatif-workers.csv').read_text().splitlines()), 13)

    def test_verification_rejects_wrong_worker_count(self):
        c = self.controller()
        c.project = 'isolated'
        c.manifest['docker_resources'] = {s: dict(NanoCpus=0, Memory=0) for s in c.manifest['images']}
        items = [dict(Config=dict(Labels={'com.docker.compose.service': s}, Cmd=command_for(2)),
                      Image=image, HostConfig=dict(NanoCpus=0, Memory=0))
                 for s, image in c.manifest['images'].items()]
        c.docker = Mock(return_value=Mock(stdout=json.dumps(items).encode()))
        del c.verify_configuration
        with self.assertRaisesRegex(RuntimeError, 'command differs'):
            c.verify_configuration(4)

    def test_vm_uses_same_four_blocks_without_docker_worker_override(self):
        c = self.controller()
        c.deployment = 'vm'
        c.boot_vm = Mock()
        c.prepare_vm = Mock()
        c.ssh = Mock()
        calls = []
        def measure(dep, name, users):
            calls.append((dep, name, users))
            series, workers = map(int, name.split('-workers-'))
            c.manifest['runs'].append(self.sample(series, workers, users))
        c.measure = Mock(side_effect=measure)
        c.resume_work()
        c.boot_vm.assert_called_once()
        c.prepare_vm.assert_called_once()
        self.assertTrue(all(call[0] == 'vm' for call in calls))
        self.assertEqual(len(calls), 12)
        self.assertFalse((self.output / 'workers.json').exists())
        self.assertEqual(c.reset.call_count, 4)
        self.assertTrue(all(call.args == ('vm',) for call in c.reset.call_args_list))
        self.assertTrue(any('systemctl daemon-reload' in call.args[1] for call in c.ssh.call_args_list))

    def test_vm_rejected_load_skips_higher_loads_but_compares_other_workers(self):
        c = self.controller()
        c.deployment = 'vm'
        c.boot_vm = Mock()
        c.prepare_vm = Mock()
        c.ssh = Mock()
        def measure(dep, name, users):
            series, workers = map(int, name.split('-workers-'))
            c.manifest['runs'].append(self.sample(series, workers, users, valid=workers == 4))
        c.measure = Mock(side_effect=measure)
        c.resume_work()
        self.assertEqual(len(c.manifest['runs']), 8)
        self.assertEqual(c.manifest['skipped_loads'], [
            dict(block='1-workers-2', users=[180, 200]),
            dict(block='2-workers-2', users=[180, 200])])

    def test_vm_verification_rejects_incorrect_process_count(self):
        c = self.controller()
        c.deployment = 'vm'
        del c.verify_configuration
        c.ssh = Mock(side_effect=[Mock(stdout=b'gunicorn --workers 4 --timeout 30'), Mock(stdout=b'2')])
        with self.assertRaisesRegex(RuntimeError, 'process count differs'):
            c.verify_configuration(4)

    def test_exhausted_calibration_skips_load_and_continues_other_blocks(self):
        c = self.controller()
        def measure(dep, name, users):
            if name == '1-workers-2' and users == 180:
                raise WorkerCalibrationUnavailable('both attempts invalid')
            series, workers = map(int, name.split('-workers-'))
            c.manifest['runs'].append(self.sample(series, workers, users))
        c.measure = Mock(side_effect=measure)
        c.resume_work()
        self.assertEqual(c.manifest['status'], 'complete')
        self.assertEqual(len(c.manifest['runs']), 10)
        self.assertEqual(c.manifest['skipped_loads'], [dict(
            block='1-workers-2', users=[180, 200], reason='calibration_rejected')])


if __name__ == '__main__':
    unittest.main()
