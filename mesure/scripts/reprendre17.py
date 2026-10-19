"""Resume a completed plateau rejected by the injector guard, preserving attempts.

This is an interrupted campaign: its provenance explicitly retains the interruption
and the CPU-unit amendment. It is never described as one continuous experiment.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from campagnes17 import Campaigns, SERVICES
from capacite import CapacityCampaign, injector_blockers
from etalonnage import ROOT, digest, machine_snapshot, save
from deploiement.scripts.maintenance.commun import operation_lock
from lancer17 import alive


def cpu_capacity():
    """Logical CPU capacity available to the injector, including ancestor quotas."""
    capacity = float(len(os.sched_getaffinity(0)))
    relative = next(line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
                    if line.startswith('0::'))
    root = Path('/sys/fs/cgroup')
    current = root / relative.lstrip('/')
    while current.is_relative_to(root):
        quota = current / 'cpu.max'
        if quota.exists():
            value, period = quota.read_text().split()
            if value != 'max':
                capacity = min(capacity, int(value) / int(period))
        if current == root:
            break
        current = current.parent
    return capacity


def checked_protocol_hashes(root, manifest):
    """Allow historical hashes only for archived, CPU-unit-only amendments."""
    current = json.loads((root / 'protocole.json').read_text())
    if digest(root / 'protocole.json') != manifest['protocol_sha256']:
        raise RuntimeError('Current frozen protocol changed')
    hashes = {manifest['protocol_sha256']}
    for resume in manifest.get('resumptions', []):
        path = (root / resume['checkpoint'] / 'protocole.json').resolve()
        if not path.is_relative_to(root.resolve()) or digest(path) != resume['previous_protocol_sha256']:
            raise RuntimeError('Archived protocol changed')
        old = json.loads(path.read_text())
        amended = copy.deepcopy(current)
        old['capacite'].pop('injecteur_cpu_capacite_coeurs', None)
        amended['capacite'].pop('injecteur_cpu_capacite_coeurs', None)
        if old != amended:
            raise RuntimeError('Resume amendment changed the measurement scenario or thresholds')
        hashes.add(resume['previous_protocol_sha256'])
    return hashes


def effective_events(events, manifest):
    """Exclude replaced attempts from validation; the original journal is untouched."""
    for resume in manifest.get('resumptions', []):
        def replaced(event):
            if event['epoch_s'] >= resume['epoch_s']:
                return False
            if event.get('deployment') != resume['deployment'] or event.get('users') != resume['users']:
                return False
            action = event['action']
            if action in ('calibration_start', 'calibration_complete'):
                return True
            return (action in ('palier_start', 'palier_complete', 'cooldown_start', 'cooldown_complete')
                    and event.get('series') in (resume['series'], 'etalonnage-' + resume['deployment']))
        events = [event for event in events if not replaced(event)]
    return events


class ResumedCapacity(CapacityCampaign):
    def __init__(self, args):
        # The explicit resume command validates and archives the existing checkpoint.
        # Ordinary capacity creation retains its refusal to overwrite old evidence.
        Campaigns.__init__(self, args)
        self.resuming = True
        self.policy = self.protocol['capacite']
        self.health_failures = 0
        self.previous_machine = machine_snapshot()
        self.calibrated = {(r['deployment'], r['users']) for r in self.manifest['runs']}
        self.resume = self.manifest['resumptions'][-1]
        checked_protocol_hashes(self.output, self.manifest)
        self.compose.extend(['-f', str(self.runtime / 'resume-images.json')])

    def check_inputs(self):
        for path, key in ((self.runtime / 'base.sql', 'snapshot_sha256'),
                          (self.runtime / 'sources.tar', 'sources_sha256'),
                          (self.accounts, 'accounts_sha256'), (ROOT / 'plan.jmx', 'source_plan_sha256')):
            if digest(path) != self.manifest[key]:
                raise RuntimeError('Checkpoint input changed: ' + str(path))
        if cpu_capacity() != self.policy['injecteur_cpu_capacite_coeurs']:
            raise RuntimeError('Injector CPU allocation changed since checkpoint preparation')

    def event(self, action, **fields):
        if getattr(self, 'resume_reset', False) and action in ('database_restored', 'login_rate_limit_checked'):
            fields['resume_reset'] = True
        super().event(action, **fields)

    def reset(self, deployment):
        if getattr(self, 'skip_next_reset', False):
            self.skip_next_reset = False
            return
        self.resume_reset = (deployment == self.resume['deployment']
                             and not getattr(self, 'first_reset_done', False))
        try:
            super().reset(deployment)
        finally:
            self.first_reset_done = True
            self.resume_reset = False

    def resume_work(self):
        self.check_inputs()
        self.preflight()
        for service in SERVICES:
            if self.vm_state(service) not in ('poweroff', 'aborted'):
                raise RuntimeError('Resume requires stopped VMs; restore services first')
        self.manifest.pop('error', None)
        self.manifest.pop('restoration_errors', None)
        self.reference_touched = True
        self.run([*self.reference, 'stop'])
        if self.suspended_containers:
            self.calibration_touched = True
            self.docker('stop', *self.suspended_containers)
        self.measurement_touched = True
        self.dc('create', '--no-build')
        containers = json.loads(self.docker('inspect', *(f'{self.project}-{s}-1' for s in SERVICES)).stdout)
        for item in containers:
            service = item['Config']['Labels']['com.docker.compose.service']
            if (item['Image'] != self.manifest['images'][service]
                    or any(item['HostConfig'][k] != v for k, v in self.manifest['docker_resources'][service].items())):
                raise RuntimeError('Deployment image/resources changed: ' + service)
        self.manifest['status'] = 'running'
        self.event('capacity_resume_start', **{k: self.resume[k] for k in ('deployment', 'series', 'users', 'checkpoint')})
        order = [('vm', 1), ('docker', 1), ('docker', 2), ('vm', 2)]
        first = order.index((self.resume['deployment'], self.resume['series']))
        for deployment, series in order[first:]:
            if deployment == 'vm':
                self.boot_vm()
                self.prepare_vm()
            # Replay the interrupted plateau before choosing a new refinement.
            if (deployment, series) == order[first]:
                self.reset(deployment)
                self.cooldown(deployment, 'reprise', self.resume['users'])
                block = next(b for b in self.manifest['blocks'] if not b['completed'])
                block['targets'].append(self.resume['users'])
                self.measure(deployment, series, self.resume['users'])
                self.skip_next_reset = True
            self.campaign(deployment, series)
            if deployment == 'vm':
                self.stop_vm()
            else:
                self.dc('stop')
        self.manifest.update(status='complete', finished_epoch_s=time.time())
        self.event('campaigns_complete')


def prepare(runtime, configuration):
    output = Path(configuration['output']).resolve()
    if not output.is_relative_to(ROOT / 'resultats'):
        raise RuntimeError('Invalid capacity output')
    manifest = json.loads((output / 'manifest.json').read_text())
    if manifest.get('kind') != 'capacity' or manifest['status'] not in ('failed', 'stopped'):
        raise RuntimeError('Only interrupted capacity campaigns can be resumed')
    if not manifest.get('error', '').startswith('Injector/host limiting;'):
        raise RuntimeError('This resume command requires a completed plateau rejected by the injector guard')
    blocks = [b for b in manifest['blocks'] if not b['completed']]
    last = manifest['runs'][-1]
    if len(blocks) != 1 or (blocks[0]['deployment'], blocks[0]['series']) != (last['deployment'], last['series']):
        raise RuntimeError('Ambiguous checkpoint')
    # Refuse changed inputs before moving or changing any evidence.
    protocol_path = output / 'protocole.json'
    if digest(protocol_path) != manifest['protocol_sha256']:
        raise RuntimeError('Frozen protocol changed')
    for path, key in ((runtime / 'base.sql', 'snapshot_sha256'), (runtime / 'sources.tar', 'sources_sha256'),
                      (output / 'comptes.csv', 'accounts_sha256'), (ROOT / 'plan.jmx', 'source_plan_sha256')):
        if digest(path) != manifest[key]:
            raise RuntimeError('Checkpoint input changed: ' + str(path))
    protocol = json.loads(protocol_path.read_text())
    original = copy.deepcopy(protocol)
    protocol['capacite']['injecteur_cpu_capacite_coeurs'] = cpu_capacity()
    folder = output / last['path']
    sample = json.loads((folder / 'synthese.json').read_text())
    if not sample['plateau_valid']:
        raise RuntimeError('Last plateau incomplete; manual diagnosis required')
    blockers = injector_blockers(folder, protocol['capacite'])
    if blockers:
        raise RuntimeError('Resource limitation still present: ' + ', '.join(blockers))
    stamp = str(time.time_ns())
    checkpoint = output / 'reprises' / stamp
    checkpoint.mkdir(parents=True)
    for name in ('manifest.json', 'protocole.json', 'journal.jsonl', 'incident.json'):
        if (output / name).exists():
            shutil.copy2(output / name, checkpoint / name)
    resume = dict(deployment=last['deployment'], series=last['series'], users=last['users'],
                  checkpoint=str(checkpoint.relative_to(output)), epoch_s=time.time(),
                  previous_protocol_sha256=manifest['protocol_sha256'],
                  amendment='Injector CPU is divided by available logical CPU capacity; service thresholds/timing unchanged',
                  interrupted_campaign=True)
    save(checkpoint / 'reprise.json', resume)
    # Old raw files and private Java logs remain available under this attempt.
    paths = [last['path'], f"etalonnage/{last['deployment']}/{last['users']}",
             f"repos/serie-etalonnage-{last['deployment']}/{last['deployment']}/{last['users']}",
             f"repos/serie-{last['series']}/{last['deployment']}/{last['users']}"]
    for name in paths:
        source = output / name
        if source.exists():
            target = checkpoint / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), target)
    for name in (f"jmeter/serie-{last['series']}/{last['deployment']}/{last['users']}",
                 f"jmeter/etalonnage/{last['deployment']}/{last['users']}"):
        source = runtime / name
        if source.exists():
            target = runtime / 'reprises' / stamp / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), target)
    manifest['runs'].pop()
    blocks[0]['targets'].remove(last['users'])
    manifest.pop('incident', None)  # Archived above; a new failure needs its own cause.
    (output / 'incident.json').unlink(missing_ok=True)
    manifest.setdefault('resumptions', []).append(resume)
    if protocol != original:
        save(protocol_path, protocol)
    manifest['protocol_sha256'] = digest(protocol_path)
    manifest.update(status='preparing', progress=dict(action='resume_prepared', **resume))
    save(output / 'manifest.json', manifest)
    save(runtime / 'resume-images.json', {'services': {s: {'image': image} for s, image in manifest['images'].items()}})
    configuration['capacity_protocol'] = str(protocol_path)
    save(runtime / 'configuration.json', configuration)
    (runtime / 'stop-requested').unlink(missing_ok=True)
    return resume


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'controller'])
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    configuration = json.loads((runtime / 'configuration.json').read_text())
    if args.action == 'start':
        with operation_lock(ROOT.parent / '.execution/operations-vm.lock'):
            pid = runtime / 'controller.pid'
            if pid.exists() and alive(int(pid.read_text())):
                raise RuntimeError('A controller is still running')
            # This check is read-only and precedes checkpoint mutation.
            vm_check = subprocess.run(['VBoxManage', 'list', 'runningvms'], capture_output=True, check=True)
            if vm_check.stdout.strip():
                raise RuntimeError('Restore/stop VMs before resuming')
            resume = prepare(runtime, configuration)
            with (runtime / 'controller.log').open('a') as stream:
                process = subprocess.Popen([sys.executable, __file__, 'controller', '--runtime', str(runtime)],
                    stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                    start_new_session=True, cwd=ROOT.parent, close_fds=True)
            pid.write_text(str(process.pid) + '\n')
        print(json.dumps(dict(pid=process.pid, resumed_at=resume), ensure_ascii=False, indent=2))
        return
    for key in ('runtime', 'output', 'docker_config', 'env_file', 'ssh_config', 'capacity_protocol'):
        configuration[key] = Path(configuration[key])
    ResumedCapacity(argparse.Namespace(**configuration)).main()


if __name__ == '__main__':
    main()
