"""Controlled Docker or VM comparison: 2/4 workers, then 4/2, at fixed loads."""

import csv
import json
import re
import time

from capacite import CapacityCampaign, CalibrationRejected, acceptable, variation
from campagnes17 import SERVICES
from etalonnage import digest, save
from reprendre17 import cpu_capacity


ORDER = ((1, 2), (1, 4), (2, 4), (2, 2))
LEVELS = (150, 180, 200)


class WorkerCalibrationUnavailable(RuntimeError):
    """Two rejected attempts: skip this block without accepting invalid evidence."""


def block_name(series, workers):
    return f"{series}-workers-{workers}"


def command_for(workers):
    return [".venv/bin/gunicorn", "--chdir", "app", "config.wsgi:application",
            "--bind", "0.0.0.0:8000", "--workers", str(workers), "--timeout", "30",
            "--access-logfile", "-", "--error-logfile", "-"]


def write_report(output, manifest, policy):
    deployment = manifest.get('worker_deployment', 'docker')
    levels = manifest.get('worker_levels', list(LEVELS))
    rows = []
    for run in manifest['runs']:
        sample = json.loads((output / run['path'] / 'synthese.json').read_text())
        rows.append(dict(workers=run['workers'], series=run['repetition'], users=run['users'],
                         throughput=sample['successful_throughput_rps'], p95=sample['p95_ms'],
                         errors=sample['all_errors'], valid=sample['plateau_valid'],
                         acceptable=acceptable(sample, policy), path=run['path']))
    resources = ('Mêmes sources, mêmes ressources VM, même base restaurée pour chaque bloc.'
                 if deployment == 'vm' else 'Même image, mêmes quotas, même base restaurée pour chaque bloc.')
    lines = [f'# Comparatif {deployment.upper()} : 2 et 4 workers Gunicorn',
             f"Campagne : `{output.name}`. Statut : **{manifest['status']}**.",
             'Ordre : 2 puis 4 workers, puis 4 puis 2. Charges : ' + ', '.join(map(str, levels)) + ' utilisateurs. '
             + resources + ' '
             'Montée 30 s, stabilisation 15 s, plateau 120 s, pause utilisateur 1 s.',
             '| Workers | Série | Utilisateurs | Débit réussi (req/s) | p95 (ms) | Erreurs, essai entier | Plateau valide |\n'
             '|---:|---:|---:|---:|---:|---:|:---:|']
    for row in rows:
        p95 = 'absent' if row['p95'] is None else f"{row['p95']:.1f}"
        lines[-1] += (f"\n| {row['workers']} | {row['series']} | {row['users']} | {row['throughput']:.2f} | "
                      f"{p95} | {row['errors']} | {'oui' if row['valid'] else 'non'} |")
    lines.append('## Interprétation')
    for users in levels:
        pair = {w: [r for r in rows if r['users'] == users and r['workers'] == w] for w in (2, 4)}
        reliable = all(len(rs) == 2 and all(r['acceptable'] and r['errors'] == 0 for r in rs)
                       and all(variation(rs[0][k], rs[1][k]) <= policy['ecart_repetitions_max_pct']
                               for k in ('throughput', 'p95')) for rs in pair.values())
        if not reliable:
            lines.append(f'{users} utilisateurs : comparaison non concluante (mesures manquantes, '
                         'seuil dépassé, erreurs ou répétitions divergentes de plus de 10 %).')
            continue
        gains = [(next(r for r in pair[4] if r['series'] == s)['throughput'] /
                  next(r for r in pair[2] if r['series'] == s)['throughput'] - 1) * 100 for s in (1, 2)]
        lines.append(f'{users} utilisateurs : variation du débit avec 4 workers : '
                     f'{gains[0]:+.1f} % et {gains[1]:+.1f} %. '
                     + ('Une amélioration dans les deux séries soutient l’hypothèse d’une limite liée aux workers ; '
                        'croiser avec le p95 et les ressources serveur.' if min(gains) > 5 else
                        'Le test ne démontre pas un gain de débit supérieur à 5 % dans les deux séries.'))
    if manifest.get('skipped_loads'):
        lines.append('Charges supérieures annulées après un palier refusé : ' +
                     ', '.join(f"{b['block']} : {b['users']}" for b in manifest['skipped_loads']) +
                     '. Les autres blocs repartent de la charge la plus basse avec la base restaurée.')
    if manifest.get('calibration_attempts'):
        lines.append('## Étalonnages refusés et nouvelles tentatives\n\n' + '\n'.join(
            f"- {a['block']}, {a['users']} utilisateurs, tentative {a['attempt']} : " + '; '.join(a['reasons'])
            for a in manifest['calibration_attempts']))
    if manifest.get('calibration_warnings'):
        lines.append('## Requêtes lentes pendant l’étalonnage\n\n' + '\n'.join(
            f"- `{a['path']}` : maximum {a['max_elapsed_ms']} ms, "
            f"{a['boundary_crossing_requests']} requêtes chevauchant une borne."
            for a in manifest['calibration_warnings']))
    lines.append(f'Les relevés CPU, mémoire, E/S et PostgreSQL figurent dans `serie-*/{deployment}/*/serveurs.json`. '
                 'Un plateau invalide ne représente pas la charge demandée. '
                 'Ce diagnostic ne valide pas une capacité maximale VM/Docker.')
    (output / 'rapport-workers.md').write_text('\n\n'.join(lines) + '\n')
    with (output / 'comparatif-workers.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else
                                ['workers', 'series', 'users', 'throughput', 'p95', 'errors', 'valid', 'acceptable', 'path'])
        writer.writeheader()
        writer.writerows(rows)
    files = ['rapport-workers.md', 'comparatif-workers.csv', 'manifest.json', 'protocole.json']
    (output / 'SHA256SUMS-workers').write_text(''.join(f'{digest(output / f)}  {f}\n' for f in files))


class WorkerCampaign(CapacityCampaign):
    def __init__(self, args):
        protocol = json.loads(args.capacity_protocol.read_text())
        self.deployment = protocol.get('worker_deployment', 'docker')
        if self.deployment not in ('docker', 'vm'):
            raise RuntimeError('Unknown worker comparison deployment')
        if protocol.get('worker_comparison') != [2, 4]:
            raise RuntimeError('Worker comparison requires 2/4 workers')
        super().__init__(args)
        self.levels = tuple(self.protocol['paliers_utilisateurs'])
        self.policy = dict(self.policy, injecteur_cpu_capacite_coeurs=cpu_capacity())
        self.manifest.update(kind='worker', order=[dict(series=s, workers=w) for s, w in ORDER],
                             expected_plateaus=len(ORDER) * len(self.levels), worker_levels=list(self.levels), maintenance_guard=self.deployment == 'vm',
                             worker_deployment=self.deployment,
                             injector_cpu_capacity_cores=self.policy['injecteur_cpu_capacite_coeurs'])
        # Reuse the common controller's exception handling, operation lock and restoration.
        self.resuming = True

    def preflight(self):
        super().preflight()
        for service in SERVICES:
            if self.vm_state(service) not in ('poweroff', 'aborted'):
                raise RuntimeError('Worker comparison requires stopped VMs; no VM is stopped automatically')

    def select_workers(self, workers):
        if self.deployment == 'vm':
            # Only the dedicated measurement unit is changed; restore_vm removes it.
            script = f'''from pathlib import Path
import re
assert Path('/opt/intern-mesure17/.measurement-owned').is_file(), 'Unowned measurement service'
unit = Path('/etc/systemd/system/intern-mesure17.service')
text = unit.read_text()
assert text.count('ExecStart=') == 1 and '/opt/intern/metier/.venv/bin/gunicorn' in text
text, count = re.subn(r'--workers [0-9]+', '--workers {workers}', text)
assert count == 1, 'Unexpected worker configuration'
unit.write_text(text)
'''
            self.ssh('metier', 'sudo systemctl stop intern-mesure17')
            self.ssh('metier', 'sudo python3 -', data=script.encode())
            self.ssh('metier', 'sudo systemctl daemon-reload')
            return
        overlay = self.runtime / 'workers.json'
        save(overlay, {'services': {s: {'image': self.manifest['images'][s],
                    **({'command': command_for(workers)} if s == 'metier' else {})} for s in SERVICES}})
        if not getattr(self, 'worker_overlay', False):
            self.compose.extend(['-f', str(overlay)])
            self.worker_overlay = True

    def verify_configuration(self, workers):
        if self.deployment == 'vm':
            command = self.ssh('metier', 'sudo systemctl show intern-mesure17 -p ExecStart --value').stdout.decode()
            if not re.search(r'--workers ' + str(workers) + r'(?:\s|;)', command):
                raise RuntimeError('Effective VM Gunicorn command differs')
            count = self.ssh('metier', 'pid=$(systemctl show intern-mesure17 -p MainPID --value); '
                             'test "$pid" -gt 0; ps --no-headers -o pid= --ppid "$pid" | wc -l').stdout.decode().strip()
            if int(count) != workers:
                raise RuntimeError('Effective VM worker process count differs')
            configurations = {}
            for service in SERVICES:
                info = dict(line.split('=', 1) for line in self.vm_info(service).splitlines() if '=' in line)
                actual = {k: info[k].strip('"') for k in ('cpus', 'memory', 'paravirtprovider')}
                if actual != self.manifest['vm_configuration'][service]:
                    raise RuntimeError('VM resource allocation changed: ' + service)
                configurations[service] = actual
            save(self.output / f'configuration-workers-{workers}.json',
                 dict(command=command.strip(), active_workers=int(count), resources=configurations))
            return
        items = json.loads(self.docker('inspect', *(f'{self.project}-{s}-1' for s in SERVICES)).stdout)
        for item in items:
            service = item['Config']['Labels']['com.docker.compose.service']
            if (item['Image'] != self.manifest['images'][service] or
                    any(item['HostConfig'][k] != v for k, v in self.manifest['docker_resources'][service].items())):
                raise RuntimeError('Images or resource quotas changed: ' + service)
            if service == 'metier' and item['Config']['Cmd'] != command_for(workers):
                raise RuntimeError('Effective Gunicorn command differs')
        save(self.output / f'configuration-workers-{workers}.json', [
            dict(service=item['Config']['Labels']['com.docker.compose.service'],
                 image=item['Image'], command=item['Config']['Cmd'],
                 resources={k: item['HostConfig'][k] for k in ('NanoCpus', 'Memory')}) for item in items])

    def resume_work(self):
        self.preflight()
        self.reference_touched = True
        self.run([*self.reference, 'stop'])
        if self.suspended_containers:
            self.calibration_touched = True
            self.docker('stop', *self.suspended_containers)
        self.bootstrap()
        if self.deployment == 'vm':
            self.boot_vm()
            self.prepare_vm()
        self.manifest['status'] = 'running'
        for series, workers in ORDER:
            self.check_stop()
            self.select_workers(workers)
            self.reset(self.deployment)
            self.verify_configuration(workers)
            name = block_name(series, workers)
            self.cooldown(self.deployment, 'initial-' + name, 0)
            # Independently verify static headroom for both worker configurations.
            self.calibrated = set()
            self.calibration_prefix = 'calibrations/' + name
            self.event('worker_block_start', repetition=series, workers=workers)
            for users in self.levels:
                try:
                    self.measure(self.deployment, name, users)
                except WorkerCalibrationUnavailable as error:
                    skipped = [n for n in self.levels if n >= users]
                    self.manifest.setdefault('skipped_loads', []).append(
                        dict(block=name, users=skipped, reason='calibration_rejected'))
                    self.event('worker_block_calibration_unavailable', block=name,
                               users=users, skipped_users=skipped, reason=str(error))
                    break
                sample = json.loads((self.output / self.manifest['runs'][-1]['path'] / 'synthese.json').read_text())
                if not acceptable(sample, self.policy) or sample['all_errors']:
                    if self.deployment == 'vm':
                        skipped = [n for n in self.levels if n > users]
                        self.manifest.setdefault('skipped_loads', []).append(dict(block=name, users=skipped))
                        self.event('worker_block_rejected', repetition=series, workers=workers,
                                   users=users, skipped_users=skipped)
                        break
                    raise RuntimeError('Worker plateau invalid or rejected; higher loads cancelled')
            if self.deployment == 'docker':
                self.dc('stop')
        self.manifest.update(status='complete', finished_epoch_s=time.time())
        self.event('campaigns_complete')

    def run_plateau(self, deployment, series, users):
        super().run_plateau(deployment, series, users)
        repetition, workers = str(series).split('-workers-')
        self.manifest['runs'][-1].update(workers=int(workers), repetition=int(repetition))
        save(self.manifest_path, self.manifest)

    def calibrate(self, deployment, users):
        if (deployment, users) in self.calibrated:
            return
        prefix = self.calibration_prefix
        try:
            for attempt in (1, 2):
                self.calibration_prefix = prefix + f'/tentative-{attempt}'
                try:
                    super().calibrate(deployment, users)
                    self.manifest.pop('calibration_failure', None)
                    return
                except CalibrationRejected as error:
                    failure = dict(self.manifest['calibration_failure'],
                                   block=prefix.removeprefix('calibrations/'), attempt=attempt)
                    self.manifest.setdefault('calibration_attempts', []).append(failure)
                    self.event('worker_calibration_retry' if attempt == 1 else 'worker_calibration_exhausted', **failure)
                    # Always return to idle before a retry or a different block.
                    # Safety/collector/rest errors propagate and still stop the campaign.
                    self.cooldown(deployment, 'rejet-' + self.calibration_prefix.replace('/', '-'), users)
                    if attempt == 2:
                        raise WorkerCalibrationUnavailable(str(error)) from error
        finally:
            self.calibration_prefix = prefix

    def main(self):
        try:
            super().main()
        finally:
            if self.manifest_path.exists():
                write_report(self.output, self.manifest, self.policy)
                print('Rapport :', self.output / 'rapport-workers.md', flush=True)

    def restore(self):
        try:
            if self.deployment == 'vm' and self.vm_touched:
                directory = self.runtime / 'vm-logs'
                directory.mkdir(mode=0o700, exist_ok=True)
                for service in SERVICES:
                    try:
                        if self.vm_state(service) != 'running':
                            continue
                        since = int(self.manifest['started_epoch_s'])
                        result = self.ssh(service, 'sudo journalctl --no-pager -o short-iso '
                                          f'--since=@{since} -u intern-mesure17 -u nginx '
                                          '-u postgresql@16-main', timeout=20)
                        path = directory / f'{service}.log'
                        path.write_bytes(result.stdout)
                        path.chmod(0o600)
                    except Exception as error:
                        self.manifest.setdefault('diagnostic_errors', []).append(
                            f'VM journal {service}: {error}')
        finally:
            # Diagnostics must never prevent the restoration of services.
            super().restore()
