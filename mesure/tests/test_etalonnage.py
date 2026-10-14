"""Stable-window checks: ramp exclusion, boundary crossing, errors and effective load."""

import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("etalonnage", Path(__file__).parents[1] / "scripts/etalonnage.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AnalysisTests(unittest.TestCase):
    def samples(self, active=1):
        # Window is [1000, 61000] ms, with 0 ms as the first sampler start.
        return [
            [0, 10, "Connexion", "true", 1, "candidat-1"],
            [990, 20, "Lecture", "true", active, "candidat-1"],
            [1000, 10, "Lecture", "true", active, "candidat-1"],
            [60000, 20, "Lecture", "false", active, "candidat-1"],
            [60990, 20, "Lecture", "true", active, "candidat-1"],
        ]

    def analyse(self, rows):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "results.csv"
            with file.open("w") as stream:
                writer = csv.writer(stream)
                writer.writerow(["timeStamp", "elapsed", "label", "success", "allThreads", "threadName"])
                writer.writerows(rows)
            return module.analyse(file, 1, 1, 0, 60)

    def test_excludes_ramp_and_boundary_crossings(self):
        result = self.analyse(self.samples())
        self.assertEqual(result["requests"], 2)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["throughput_rps"], 2 / 60)
        self.assertEqual(result["successful_throughput_rps"], 1 / 60)
        self.assertEqual(result["p95_ms"], 19.5)

    def test_rejects_wrong_effective_load(self):
        with self.assertRaisesRegex(RuntimeError, "active users"):
            self.analyse(self.samples(active=2))

    def test_rejects_short_run(self):
        with self.assertRaisesRegex(RuntimeError, "left the plateau early"):
            self.analyse(self.samples()[:3])


if __name__ == "__main__":
    unittest.main()
