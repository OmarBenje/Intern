"""Checkpoint preservation, CPU units, and restart without replaying early loads."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reprendre17 as resume
from capacite import cpu_assessment
from etalonnage import digest, save
import test_capacite


class ResumeTests(unittest.TestCase):
    def test_prepare_archives_raw_attempt_and_refuses_changed_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            measure = root / 'mesure'
            output = measure / 'resultats/test'
            runtime = root / 'private'
            output.mkdir(parents=True)
            runtime.mkdir()
            files = [(runtime / 'base.sql', 'snapshot_sha256'),
                     (runtime / 'sources.tar', 'sources_sha256'),
                     (output / 'comptes.csv', 'accounts_sha256'),
                     (measure / 'plan.jmx', 'source_plan_sha256')]
            for path, _ in files:
                path.write_text('original')
            save(output / 'protocole.json', {'capacite': {'cpu_soutenu_s': 10}})
            folder = output / 'serie-1/docker/200'
            folder.mkdir(parents=True)
            save(folder / 'synthese.json', {'plateau_valid': True})
            (folder / 'brut.csv').write_text('original raw evidence')
            manifest = dict(kind='capacity', status='failed', error='Injector/host limiting; cpu',
                            protocol_sha256=digest(output / 'protocole.json'),
                            images={'metier': 'sha256:fixed'}, runs=[dict(series=1, deployment='docker',
                            users=200, path='serie-1/docker/200')], blocks=[dict(series=1, deployment='docker',
                            targets=[200], completed=False)], **{key: digest(path) for path, key in files})
            save(output / 'manifest.json', manifest)
            configuration = dict(output=str(output))
            with patch.object(resume, 'ROOT', measure), patch.object(resume, 'cpu_capacity', return_value=12), \
                    patch.object(resume, 'injector_blockers', return_value=[]):
                (runtime / 'base.sql').write_text('changed')
                with self.assertRaisesRegex(RuntimeError, 'input changed'):
                    resume.prepare(runtime, configuration)
                self.assertFalse((output / 'reprises').exists())
                (runtime / 'base.sql').write_text('original')
                checkpoint = resume.prepare(runtime, configuration)
            archived = output / checkpoint['checkpoint']
            self.assertEqual((archived / 'serie-1/docker/200/brut.csv').read_text(), 'original raw evidence')
            self.assertEqual(json.loads((archived / 'manifest.json').read_text()), manifest)
            self.assertFalse(folder.exists())
            current = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(current['runs'], [])
            self.assertEqual(current['blocks'][0]['targets'], [])
            self.assertEqual(len(resume.checked_protocol_hashes(output, current)), 2)

    def test_cpu_normalization_retains_legacy_and_host_units(self):
        rows = [dict(epoch_s=n, injector_cpu_pct=96, host_busy_pct=30) for n in range(13)]
        old = cpu_assessment(rows, {'cpu_soutenu_s': 10})
        new = cpu_assessment(rows, {'cpu_soutenu_s': 10, 'injecteur_cpu_capacite_coeurs': 12})
        self.assertEqual(old['injector_cpu_pct'], 96)
        self.assertEqual(new, dict(injector_cpu_pct=8, host_busy_pct=30))
        self.assertIsNone(cpu_assessment(rows[:2], {'cpu_soutenu_s': 10})['injector_cpu_pct'])

    def test_amendment_rejects_service_threshold_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = root / 'reprises/1'
            checkpoint.mkdir(parents=True)
            old = {'capacite': {'p95_max_ms': 1000}, 'plateau_s': 120}
            save(checkpoint / 'protocole.json', old)
            new = copy.deepcopy(old)
            new['capacite']['injecteur_cpu_capacite_coeurs'] = 12
            save(root / 'protocole.json', new)
            manifest = dict(protocol_sha256=digest(root / 'protocole.json'), resumptions=[dict(
                checkpoint='reprises/1', previous_protocol_sha256=digest(checkpoint / 'protocole.json'))])
            self.assertEqual(len(resume.checked_protocol_hashes(root, manifest)), 2)
            new['capacite']['p95_max_ms'] = 2000
            save(root / 'protocole.json', new)
            manifest['protocol_sha256'] = digest(root / 'protocole.json')
            with self.assertRaisesRegex(RuntimeError, 'scenario or thresholds'):
                resume.checked_protocol_hashes(root, manifest)

    def test_effective_journal_retains_raw_attempt_and_keeps_new_attempt(self):
        events = [dict(epoch_s=t, action='palier_start', deployment='docker', users=n, series=1)
                  for t, n in [(1, 160), (2, 200), (4, 200), (5, 220)]]
        original = copy.deepcopy(events)
        manifest = dict(resumptions=[dict(epoch_s=3, deployment='docker', series=1, users=200)])
        self.assertEqual([e['users'] for e in resume.effective_events(events, manifest)], [160, 200, 220])
        self.assertEqual(events, original)

    def test_resumed_search_reuses_existing_levels_and_block(self):
        fixture = test_capacite.CapacityTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        controller = fixture.controller(vm_threshold=150, docker_threshold=205)
        controller.campaign('vm', 1)
        # Simulate a Docker first series interrupted during refinement after 200.
        for users in [1, 5, 10, 20, 40, 80, 120, 140, 150, 160, 320, 240, 200]:
            controller.measure('docker', 1, users)
        existing = list(controller.manifest['runs'])
        targets = [r['users'] for r in existing if r['deployment'] == 'docker']
        block = dict(series=1, deployment='docker', targets=targets, completed=False)
        controller.manifest['blocks'].append(block)
        controller.resuming = True
        controller.campaign('docker', 1)
        added = controller.manifest['runs'][len(existing):]
        self.assertEqual([r['users'] for r in added], [220, 210])
        self.assertEqual(len(controller.manifest['blocks']), 2)
        self.assertTrue(block['completed'])
        self.assertEqual(controller.manifest['runs'][:len(existing)], existing)

    def test_resume_first_reset_is_tagged_and_second_reset_is_skipped(self):
        controller = resume.ResumedCapacity.__new__(resume.ResumedCapacity)
        controller.resume = dict(deployment='docker')
        with patch.object(resume.Campaigns, 'reset') as reset:
            controller.reset('docker')
            controller.skip_next_reset = True
            controller.reset('docker')
            controller.reset('docker')
        self.assertEqual(reset.call_count, 2)


if __name__ == '__main__':
    unittest.main()
