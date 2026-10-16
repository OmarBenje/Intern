"""Adaptive rests require complete, fresh and quiet service readings."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from campagnes17 import Campaigns
from etalonnage import PERFORMANCE_PROTOCOL, digest, saved_protocol
from repos import SERVICES, idle_window, idle_blockers


class AdaptiveRestTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(PERFORMANCE_PROTOCOL.read_text())["repos_dynamique"]
        self.samples = {
            service: [dict(epoch_s=t, interval_s=5, cpu_pct=1,
                           read_bytes_per_s=0, write_bytes_per_s=0,
                           db_active_connections=0) for t in range(75, 101, 5)]
            for service in SERVICES
        }

    def test_quiet_continuous_window_is_ready(self):
        self.assertTrue(idle_window(self.samples, 100, self.policy))

    def test_busy_cpu_io_or_database_requires_more_rest(self):
        for field, value in [("cpu_pct", 20), ("write_bytes_per_s", 2000000),
                             ("db_active_connections", 1)]:
            with self.subTest(field=field):
                row = self.samples["donnees"][-1]
                original = row[field]
                row[field] = value
                self.assertFalse(idle_window(self.samples, 100, self.policy))
                row[field] = original

    def test_short_window_is_not_enough(self):
        self.samples["proxy"] = self.samples["proxy"][-3:]
        self.assertFalse(idle_window(self.samples, 100, self.policy))

    def test_stale_readings_do_not_allow_restart(self):
        self.assertFalse(idle_window(self.samples, 111, self.policy))

    def test_missing_service_does_not_allow_restart(self):
        del self.samples["metier"]
        self.assertFalse(idle_window(self.samples, 100, self.policy))

    def test_missing_io_is_not_zero_activity(self):
        self.samples["proxy"][-1]["read_bytes_per_s"] = None
        self.assertFalse(idle_window(self.samples, 100, self.policy))

    def test_gap_in_readings_breaks_stability(self):
        del self.samples["donnees"][-3]
        self.assertFalse(idle_window(self.samples, 100, self.policy))

    def test_memory_cache_does_not_prevent_restart(self):
        self.samples["donnees"][-1]["rss_bytes"] = 2000000000
        self.assertTrue(idle_window(self.samples, 100, self.policy))

    def test_nonfinite_counters_do_not_allow_restart(self):
        self.samples["metier"][-1]["cpu_pct"] = float("nan")
        self.assertFalse(idle_window(self.samples, 100, self.policy))

    def test_historical_protocol_is_kept_with_its_original_hash(self):
        historical = PERFORMANCE_PROTOCOL.with_name("protocole.json")
        self.assertEqual(saved_protocol(digest(historical))["repos_minimal_entre_paliers_s"], 900)
        self.assertIn("repos_dynamique", saved_protocol(digest(PERFORMANCE_PROTOCOL)))
        with self.assertRaises(RuntimeError):
            saved_protocol("changed")

    def test_diagnostic_identifies_only_busy_service_and_frozen_threshold(self):
        self.samples['metier'][-1]['cpu_pct'] = 8
        blockers = idle_blockers(self.samples, 100, self.policy)
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0]['service'], 'metier')
        self.assertEqual(blockers[0]['metric'], 'cpu_pct')
        self.assertEqual(blockers[0]['value'], 8)
        self.assertEqual(blockers[0]['maximum'], 5)


class CampaignRestTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.campaign = Campaigns.__new__(Campaigns)
        self.campaign.output = Path(self.folder.name)
        self.campaign.protocol = json.loads(PERFORMANCE_PROTOCOL.read_text())
        self.campaign.event = Mock()
        self.campaign.stop_collectors = Mock()
        self.campaign.check_stop = Mock()
        self.campaign.collect = self.collect
        self.elapsed = 0
        self.busy = False
        self.clock = Mock()
        self.clock.monotonic.side_effect = lambda: self.elapsed
        self.clock.time.side_effect = lambda: self.elapsed
        self.clock.sleep.side_effect = self.sleep

    def sleep(self, seconds):
        self.elapsed += seconds

    def collect(self, deployment, folder):
        # Equivalent to six five-second readings becoming available by t=30.
        for service in SERVICES:
            rows = [dict(epoch_s=t, interval_s=5, cpu_pct=99 if self.busy else 1,
                         read_bytes_per_s=0, write_bytes_per_s=0,
                         db_active_connections=0) for t in range(5, 31, 5)]
            (folder / f"serveur-{service}.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows))

    def test_returns_as_soon_as_minimum_rest_and_stability_are_met(self):
        with patch("campagnes17.time", self.clock), patch("campagnes17.urllib.request.urlopen") as http:
            http.return_value.__enter__.return_value.status = 200
            self.campaign.cooldown("docker", 1, 5)
        self.assertEqual(self.elapsed, 30)
        self.assertEqual(self.campaign.event.call_args.args[0], "cooldown_complete")
        self.campaign.stop_collectors.assert_called_once()

    def test_busy_or_stale_services_abort_at_maximum_instead_of_starting_load(self):
        self.busy = True
        with patch("campagnes17.time", self.clock):
            with self.assertRaisesRegex(RuntimeError, "did not return to idle"):
                self.campaign.cooldown("vm", 1, 5)
        self.assertEqual(self.elapsed, 180)
        self.campaign.stop_collectors.assert_called_once()
        self.assertEqual(self.campaign.event.call_args.args[0], 'cooldown_failed')
        diagnostic = json.loads((self.campaign.output / 'repos/serie-1/vm/5/diagnostic.json').read_text())
        self.assertTrue(diagnostic['blockers'])

    def test_failed_readiness_prevents_restart(self):
        with patch("campagnes17.time", self.clock), patch("campagnes17.urllib.request.urlopen", side_effect=OSError):
            with self.assertRaises(RuntimeError):
                self.campaign.cooldown("docker", 1, 5)
        self.campaign.stop_collectors.assert_called_once()

    def test_stop_request_also_cleans_up_collectors(self):
        self.campaign.check_stop.side_effect = InterruptedError
        with patch("campagnes17.time", self.clock):
            with self.assertRaises(InterruptedError):
                self.campaign.cooldown("vm", 1, 5)
        self.campaign.stop_collectors.assert_called_once()


if __name__ == "__main__":
    unittest.main()
