"""Verify real Linux process counters and clock alignment of remote samples."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("metrics", SCRIPTS / "metrics_serveur.py")
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


class ServerMetricsTests(unittest.TestCase):
    def test_linux_cpu_counter_tracks_actual_work(self):
        before = metrics.snapshot(os.getpid())
        start = time.monotonic()
        value = 0
        while time.monotonic() - start < .15:
            value += 1
        after = metrics.snapshot(os.getpid())
        row = metrics.interval(before, after, time.monotonic() - start)
        self.assertGreater(value, 0)
        self.assertGreater(row["cpu_pct"], 0)
        self.assertGreater(row["rss_bytes"], 0)

    def test_remote_clock_does_not_shift_host_window(self):
        code = 'import json; print(json.dumps({"epoch_s":1,"service":"proxy","cpu_pct":0}))'
        before = time.time()
        result = subprocess.run([sys.executable, str(SCRIPTS / "collecteur_serveur.py"),
                                 "--command", json.dumps([sys.executable, "-c", code])],
                                check=True, capture_output=True, text=True)
        after = time.time()
        row = json.loads(result.stdout)
        self.assertEqual(row["server_epoch_s"], 1)
        self.assertLessEqual(before, row["epoch_s"])
        self.assertLessEqual(row["epoch_s"], after)
        self.assertEqual(row["time_basis"], "host_receipt_time")


if __name__ == "__main__":
    unittest.main()
