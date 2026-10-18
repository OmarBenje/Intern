"""Capacity search decisions, raw evidence and failure boundaries without live load."""

import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from capacite import CapacityCampaign, acceptable, bracket, refinement
from analyser_capacite import conclusions, validate_design
from etalonnage import ROOT, analyse, memory_blockers


def sample(users, threshold):
    return dict(users=users, plateau_valid=True, p95_ms=100 if users <= threshold else 1500,
                error_pct=0, successful_throughput_rps=users * .9, all_errors=0,
                request_types={'Lecture': dict(samples=120, errors=0, stable_samples=120,
                                               stable_errors=0, stable_error_pct=0)})


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.protocol = json.loads((ROOT / 'protocole-capacite.json').read_text())
        self.policy = self.protocol['capacite']

    def controller(self, vm_threshold=95, docker_threshold=45):
        controller = CapacityCampaign.__new__(CapacityCampaign)
        controller.output = self.root
        controller.protocol = self.protocol
        controller.policy = self.policy
        controller.manifest = dict(runs=[], blocks=[])
        controller.check_stop = Mock()
        controller.event = Mock()
        controller.reset = Mock()
        thresholds = dict(vm=vm_threshold, docker=docker_threshold)
        def measure(dep, series, users):
            folder = self.root / f'serie-{series}/{dep}/{users}'
            folder.mkdir(parents=True)
            (folder / 'synthese.json').write_text(json.dumps(sample(users, thresholds[dep])))
            controller.manifest['runs'].append(dict(series=series, deployment=dep, users=users,
                                                  path=str(folder.relative_to(self.root)), errors=0))
        controller.measure = measure
        with (self.root / 'comptes.csv').open('w') as stream:
            writer = csv.writer(stream)
            writer.writerow(['username', 'password', 'application_id'])
            writer.writerows((f'mesure{n:02d}', 'fake', n) for n in range(1, 321))
        return controller

    def run_campaigns(self, controller):
        for dep, series in (('vm', 1), ('docker', 1), ('docker', 2), ('vm', 2)):
            controller.campaign(dep, series)
        validate_design(self.root, controller.manifest, self.protocol)
        actual = [(r['series'], r['deployment'], r['users']) for r in controller.manifest['runs']]
        expected = [(b['series'], b['deployment'], n) for b in controller.manifest['blocks'] for n in b['targets']]
        self.assertEqual(actual, expected)

    def test_exploration_refines_and_confirms_without_replaying_above_breach(self):
        controller = self.controller()
        self.run_campaigns(controller)
        self.assertEqual(len(controller.manifest['blocks']), 5)  # VM gains Docker refinement points.
        for dep in ('vm', 'docker'):
            first = controller.samples(dep, 1)
            good, bad = bracket(first, self.policy)
            self.assertLessEqual(bad - good, 10)
            second = controller.samples(dep, 2)
            self.assertEqual(set(second), {n for n in first if n <= bad})
            self.assertTrue(all(acceptable(r, self.policy) for n, r in second.items() if n < bad))
            self.assertFalse(acceptable(second[bad], self.policy))
        result = conclusions(self.root, controller.manifest, self.protocol)
        self.assertEqual(result['vm']['validated_users'], 90)
        self.assertEqual(result['docker']['validated_users'], 40)

    def test_reverse_capacity_relationship_keeps_comparable_safe_levels(self):
        controller = self.controller(45, 95)
        self.run_campaigns(controller)
        self.assertEqual(len(controller.manifest['blocks']), 4)

    def test_no_degradation_reports_lower_bound_and_requests_extension(self):
        controller = self.controller(1000, 1000)
        self.run_campaigns(controller)
        result = conclusions(self.root, controller.manifest, self.protocol)
        self.assertIsNone(result['vm']['first_rejected_users'])
        self.assertIn('limite non atteinte', result['vm']['conclusion'])
        self.assertEqual(result['vm']['validated_users'], 320)

    def test_divergent_repetitions_never_validate_capacity(self):
        controller = self.controller(1000, 1000)
        self.run_campaigns(controller)
        path = self.root / 'serie-2/vm/320/synthese.json'
        row = json.loads(path.read_text())
        row['p95_ms'] *= 2
        path.write_text(json.dumps(row))
        result = conclusions(self.root, controller.manifest, self.protocol)
        self.assertFalse(result['vm']['valid'])
        self.assertIsNone(result['vm']['validated_users'])
        self.assertTrue(result['vm']['divergence'])

    def test_early_rejection_in_confirmation_stops_progression(self):
        controller = self.controller()
        controller.campaign('vm', 1)
        original = controller.measure
        def earlier(dep, series, users):
            original(dep, series, users)
            if series == 2:
                path = self.root / f'serie-2/{dep}/{users}/synthese.json'
                path.write_text(json.dumps(sample(users, 0)))
        controller.measure = earlier
        with self.assertRaisesRegex(RuntimeError, 'Earlier threshold breach'):
            controller.campaign('vm', 2)
        self.assertEqual(set(controller.samples('vm', 2)), {1})

    def test_threshold_edges_and_nonmonotonic_results(self):
        row = sample(1, 10)
        row.update(p95_ms=1000, error_pct=1)
        self.assertTrue(acceptable(row, self.policy))
        row['plateau_valid'] = False
        self.assertFalse(acceptable(row, self.policy))
        with self.assertRaisesRegex(RuntimeError, 'Non-monotonic'):
            bracket({1: sample(1, 0), 5: sample(5, 10)}, self.policy)
        self.assertEqual(refinement(40, 80, 10), 60)
        self.assertIsNone(refinement(40, 50, 10))

    def test_missing_plateau_preserves_failure_and_request_errors(self):
        path = self.root / 'brut.csv'
        with path.open('w') as stream:
            writer = csv.writer(stream)
            writer.writerow(['timeStamp', 'elapsed', 'label', 'success', 'allThreads', 'threadName'])
            writer.writerows([[0, 20, 'Connexion', 'false', 1, 'candidat-1']])
        with self.assertRaisesRegex(RuntimeError, 'Empty stable window'):
            analyse(path, 1, 30, 15, 120)
        result = analyse(path, 1, 30, 15, 120, capacity=True)
        self.assertFalse(result['plateau_valid'])
        self.assertEqual(result['all_errors'], 1)
        self.assertEqual(result['request_types']['Connexion']['errors'], 1)
        self.assertIsNone(result['p95_ms'])

    def test_memory_swap_oom_and_pressure_each_stop_escalation(self):
        before = dict(host_memory_available_bytes=2**30, host_memory_total_bytes=4 * 2**30,
                      host_swap_pages=0, host_oom_kills=0, host_memory_pressure_pct=0)
        self.assertEqual(memory_blockers(before, before, self.policy), [])
        for field, value, reason in (
            ('host_memory_available_bytes', 1, 'host_memory_low'),
            ('host_swap_pages', 1, 'host_swapping'),
            ('host_oom_kills', 1, 'host_oom'),
            ('host_memory_pressure_pct', 20, 'host_memory_pressure')):
            self.assertIn(reason, memory_blockers({**before, field: value}, before, self.policy))

    def test_missing_confirmation_evidence_is_rejected(self):
        controller = self.controller(1000, 1000)
        self.run_campaigns(controller)
        controller.manifest['runs'].pop()
        with self.assertRaisesRegex(RuntimeError, 'not confirmed'):
            validate_design(self.root, controller.manifest, self.protocol)


if __name__ == '__main__':
    unittest.main()
