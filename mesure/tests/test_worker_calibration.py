"""Boundary activity and bounded worker calibration recovery."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from etalonnage import analyse
from capacite import CapacityCampaign, CalibrationRejected
from workers import WorkerCampaign, WorkerCalibrationUnavailable


class BoundaryActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'brut.csv'

    def write(self, samples):
        with self.path.open('w') as stream:
            writer = csv.writer(stream)
            writer.writerow(['timeStamp', 'elapsed', 'label', 'success', 'allThreads', 'threadName'])
            for start, duration in samples:
                writer.writerow([start, duration, 'static', 'true', 1, 'user-1'])

    def test_spanning_request_is_activity_and_slow_request_stays_visible(self):
        self.write([(0, 10), (1000, 10), (3000, 10), (5000, 7000)])
        legacy = analyse(self.path, 1, 1, 0, 10, capacity=True)
        corrected = analyse(self.path, 1, 1, 0, 10, capacity=True, boundary_activity=True)
        self.assertFalse(legacy['plateau_valid'])
        self.assertTrue(corrected['plateau_valid'])
        self.assertEqual(corrected['requests'], legacy['requests'])
        self.assertEqual(corrected['p95_ms'], legacy['p95_ms'])
        self.assertEqual(corrected['max_elapsed_ms'], 7000)
        self.assertEqual(corrected['boundary_crossing_requests'], 1)

    def test_real_departure_still_invalid_even_if_user_returns_after_window(self):
        self.write([(0, 10), (1000, 10), (3000, 10), (12000, 10)])
        sample = analyse(self.path, 1, 1, 0, 10, capacity=True, boundary_activity=True)
        self.assertIn('A user left the plateau early', sample['plateau_issues'])

    def test_spanning_start_boundary_is_not_a_late_arrival(self):
        self.write([(0, 7000), (8000, 10), (10000, 10)])
        self.assertFalse(analyse(self.path, 1, 1, 0, 10, capacity=True)['plateau_valid'])
        self.assertTrue(analyse(self.path, 1, 1, 0, 10, capacity=True, boundary_activity=True)['plateau_valid'])


class CalibrationRecoveryTests(unittest.TestCase):
    def controller(self):
        c = WorkerCampaign.__new__(WorkerCampaign)
        c.calibrated = set()
        c.calibration_prefix = 'calibrations/2-workers-4'
        c.manifest = dict(calibration_failure=dict(reasons=['boundary evidence missing'], users=180))
        c.event = Mock()
        c.cooldown = Mock()
        return c

    def test_rejection_retries_after_rest_and_preserves_both_paths(self):
        c = self.controller()
        paths = []
        def attempt(dep, users):
            paths.append(c.calibration_prefix)
            if len(paths) == 1:
                raise CalibrationRejected('invalid window')
            c.calibrated.add((dep, users))
        with patch.object(CapacityCampaign, 'calibrate', side_effect=attempt):
            c.calibrate('vm', 180)
        self.assertEqual(paths, ['calibrations/2-workers-4/tentative-1', 'calibrations/2-workers-4/tentative-2'])
        c.cooldown.assert_called_once()
        self.assertNotIn('calibration_failure', c.manifest)
        self.assertEqual(len(c.manifest['calibration_attempts']), 1)

    def test_second_rejection_is_bounded_and_cannot_validate_measurement(self):
        c = self.controller()
        with patch.object(CapacityCampaign, 'calibrate', side_effect=CalibrationRejected('bad')) as run:
            with self.assertRaises(WorkerCalibrationUnavailable):
                c.calibrate('vm', 180)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(c.cooldown.call_count, 2)
        self.assertFalse(c.calibrated)

    def test_safety_failure_is_not_retried(self):
        c = self.controller()
        with patch.object(CapacityCampaign, 'calibrate', side_effect=RuntimeError('OOM')) as run:
            with self.assertRaisesRegex(RuntimeError, 'OOM'):
                c.calibrate('vm', 180)
        run.assert_called_once()
        c.cooldown.assert_not_called()

    def test_log_archive_failure_cannot_skip_restoration(self):
        c = self.controller()
        with tempfile.TemporaryDirectory() as directory:
            c.runtime = Path(directory)
            c.deployment = 'vm'
            c.vm_touched = True
            c.vm_state = Mock(side_effect=RuntimeError('SSH unavailable'))
            with patch.object(CapacityCampaign, 'restore') as restore:
                c.restore()
            restore.assert_called_once()
            self.assertEqual(len(c.manifest['diagnostic_errors']), 3)


if __name__ == '__main__':
    unittest.main()
