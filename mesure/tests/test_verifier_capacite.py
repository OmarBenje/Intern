"""Exercise the raw capacity verifier with synthetic evidence, then tamper with it."""

import contextlib
import csv
import io
import json
import statistics
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import analyser_capacite as analysis
import campagnes17
import etalonnage
import verifier17


class CapacityEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.measure = Path(self.temp.name) / 'mesure'
        self.measure.mkdir()
        self.root = self.measure / 'resultats/capacite-test'
        self.root.mkdir(parents=True)
        self.protocol = json.loads((etalonnage.ROOT / 'protocole-capacite.json').read_text())
        self.protocol['paliers_utilisateurs'] = [1]
        etalonnage.save(self.root / 'protocole.json', self.protocol)
        (self.root / 'comptes.csv').write_text('username,password,application_id\nmesure01,fake,1\n')
        (self.measure / 'plan.jmx').write_bytes((etalonnage.ROOT / 'plan.jmx').read_bytes())
        self.manifest = dict(kind='capacity', status='complete', source_plan_sha256=etalonnage.digest(self.measure / 'plan.jmx'),
                             protocol_sha256=etalonnage.digest(self.root / 'protocole.json'),
                             accounts_sha256=etalonnage.digest(self.root / 'comptes.csv'), snapshot_sha256='snapshot', runs=[], blocks=[])
        self.events = []
        self.clock = 1000
        for module in (verifier17, etalonnage, analysis):
            mock = patch.object(module, 'ROOT', self.measure)
            mock.start()
            self.addCleanup(mock.stop)
        for series, dep in ((1, 'vm'), (1, 'docker'), (2, 'docker'), (2, 'vm')):
            self.manifest['blocks'].append(dict(series=series, deployment=dep, targets=[1], completed=True))
            self.event('database_restored', deployment=dep, snapshot_sha256='snapshot')
            self.event('login_rate_limit_checked', deployment=dep, enabled=False)
            if series == 1:
                self.write_run(self.root / f'etalonnage/{dep}/1', static=True)
                self.event('calibration_complete', deployment=dep, users=1)
                self.rest(f'etalonnage-{dep}', dep)
            self.event('palier_start', series=series, deployment=dep, users=1)
            relative = f'serie-{series}/{dep}/1'
            self.write_run(self.root / relative)
            self.manifest['runs'].append(dict(series=series, deployment=dep, users=1, path=relative, errors=0))
            self.event('palier_complete', series=series, deployment=dep, users=1)
            self.rest(series, dep)
        self.event('reference_restored')
        etalonnage.save(self.root / 'manifest.json', self.manifest)
        (self.root / 'journal.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in self.events))

    def event(self, action, **fields):
        self.clock += 1
        self.events.append(dict(action=action, epoch_s=self.clock, **fields))

    def rest(self, series, dep):
        path = f'repos/serie-{series}/{dep}/1'
        folder = self.root / path
        folder.mkdir(parents=True)
        self.event('cooldown_start', series=series, deployment=dep, users=1, path=path)
        self.clock += 30
        for service in campagnes17.SERVICES:
            rows = [dict(epoch_s=self.clock - n * 5, interval_s=5, cpu_pct=0,
                         read_bytes_per_s=0, write_bytes_per_s=0, db_active_connections=0) for n in range(5, -1, -1)]
            (folder / f'serveur-{service}.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
        self.event('cooldown_complete', series=series, deployment=dep, users=1, path=path,
                   ready=True, idle_epoch_s=self.clock)

    def write_run(self, folder, static=False):
        folder.mkdir(parents=True)
        ramp, warmup, plateau = (10, 5, 60) if static else (30, 15, 120)
        etalonnage.make_plan(folder / 'plan.jmx', 'static' if static else 'application', 1, ramp, ramp + warmup + plateau + 5)
        start, end = (ramp + warmup) * 1000, (ramp + warmup + plateau) * 1000
        with (folder / 'brut.csv').open('w') as stream:
            writer = csv.writer(stream)
            writer.writerow(['timeStamp', 'elapsed', 'label', 'success', 'allThreads', 'threadName'])
            writer.writerow([0, 10, 'Statique' if static else 'Connexion', 'true', 1, 'candidat-1'])
            writer.writerows([t, 10, 'Statique' if static else 'Lecture', 'true', 1, 'candidat-1']
                             for t in range(start, end, 100 if static else 1000))
        sample = etalonnage.analyse(folder / 'brut.csv', 1, ramp, warmup, plateau, capacity=True)
        for field, value in (('injector_cpu_pct', 2), ('injector_rss_bytes', 1024), ('host_busy_pct', 5)):
            sample[field + '_mean'] = sample[field + '_max'] = value
        etalonnage.save(folder / 'synthese.json', sample)
        config = dict(mode='static' if static else 'application', users=1, ramp_s=ramp, warmup_s=warmup, plateau_s=plateau,
                      duration_s=ramp+warmup+plateau+5, port=8081, reflection_ms=0 if static else 1000,
                      protocol_sha256=self.manifest['protocol_sha256'], source_plan_sha256=self.manifest['source_plan_sha256'],
                      accounts_sha256=self.manifest['accounts_sha256'], run_plan_sha256=etalonnage.digest(folder / 'plan.jmx'),
                      sql_schema_sha256='schema', sql_data_sha256='data', seed_script_sha256='seed', host={'logical_cpus': 4}, exit_code=0)
        etalonnage.save(folder / 'configuration.json', config)
        machine = dict(host_memory_total_bytes=4*2**30, host_memory_available_bytes=2**30,
                       host_swap_pages=0, host_oom_kills=0, host_memory_pressure_pct=0)
        with (folder / 'ressources.csv').open('w') as stream:
            fields = ['epoch_s', 'injector_cpu_pct', 'injector_rss_bytes', 'host_busy_pct', *machine]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(dict(epoch_s=t, injector_cpu_pct=2, injector_rss_bytes=1024, host_busy_pct=5, **machine)
                             for t in range(start//1000, end//1000 + 1, 2))
        (folder / 'console.txt').write_text('Synthetic verification fixture\n')
        if not static:
            for service in campagnes17.SERVICES:
                rows = [dict(epoch_s=t, interval_s=5, cpu_io_method='cgroup_v2', cpu_pct=2,
                             rss_bytes=1024, read_bytes_per_s=0, write_bytes_per_s=0, db_active_connections=0)
                        for t in range(start//1000 + 5, end//1000 + 1, 5)]
                (folder / f'serveur-{service}.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
            controller = campagnes17.Campaigns.__new__(campagnes17.Campaigns)
            controller.server_summary(folder)
            etalonnage.save(folder / 'injecteur.json', dict(valid=True, blockers=[]))

    def test_full_raw_verification_and_tampering(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = verifier17.main(['--output', str(self.root)])
        self.assertEqual(result['plateaus'], 4)
        self.assertIn('etalonnage/vm/1/brut.csv', result['raw_files_sha256'])
        path = self.root / 'serie-2/vm/1/synthese.json'
        value = json.loads(path.read_text())
        value['p95_ms'] *= 2
        etalonnage.save(path, value)
        with self.assertRaisesRegex(RuntimeError, 'Client summary differs'):
            verifier17.main(['--output', str(self.root)])

    def set_cpu_readings(self, field, function):
        folder = self.root / 'serie-2/vm/1'
        path = folder / 'ressources.csv'
        with path.open() as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames
            rows = list(reader)
        for index, row in enumerate(rows):
            row[field] = function(index)
        with path.open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        sample = json.loads((folder / 'synthese.json').read_text())
        values = [float(row[field]) for row in rows]
        sample[field + '_mean'] = statistics.mean(values)
        sample[field + '_max'] = max(values)
        etalonnage.save(folder / 'synthese.json', sample)
        return folder

    def test_short_cpu_spike_does_not_reject_a_new_campaign(self):
        self.set_cpu_readings('injector_cpu_pct', lambda index: 95 if index == 10 else 2)
        with contextlib.redirect_stdout(io.StringIO()):
            result = verifier17.main(['--output', str(self.root)])
        self.assertEqual(result['status'], 'verified')

    def test_sustained_injector_load_still_stops_the_campaign(self):
        self.set_cpu_readings('injector_cpu_pct', lambda index: 95 if 10 <= index <= 20 else 2)
        with self.assertRaisesRegex(RuntimeError, 'Injector/host limiting'):
            verifier17.main(['--output', str(self.root)])

    def test_sustained_host_load_still_stops_the_campaign(self):
        self.set_cpu_readings('host_busy_pct', lambda index: 95 if 10 <= index <= 20 else 5)
        with self.assertRaisesRegex(RuntimeError, 'Injector/host limiting'):
            verifier17.main(['--output', str(self.root)])

    def test_legacy_protocol_retains_its_maximum_sample_rule(self):
        from capacite import injector_blockers
        folder = self.set_cpu_readings('injector_cpu_pct', lambda index: 95 if index == 10 else 2)
        policy = dict(self.protocol['capacite'])
        policy.pop('cpu_soutenu_s')
        self.assertIn('injector_cpu_pct_max', injector_blockers(folder, policy))

    def test_cpu_window_weights_time_and_rejects_sampling_gaps(self):
        from capacite import sustained_cpu_max
        rows = [dict(epoch_s=t, cpu=cpu) for t, cpu in ((0, 0), (1, 100), (5, 0))]
        self.assertEqual(sustained_cpu_max(rows, 'cpu', 5), 20)
        self.assertIsNone(sustained_cpu_max([dict(epoch_s=0, cpu=0), dict(epoch_s=20, cpu=100)], 'cpu', 10))

    def test_saturated_injector_prevents_capacity_verification(self):
        path = self.root / 'serie-2/vm/1/synthese.json'
        value = json.loads(path.read_text())
        value['injector_cpu_pct_max'] = 100
        etalonnage.save(path, value)
        with self.assertRaisesRegex(RuntimeError, 'Injector/host limiting'):
            verifier17.main(['--output', str(self.root)])


if __name__ == '__main__':
    unittest.main()
