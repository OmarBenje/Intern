"""Explicit maintenance orchestration with a local-VM adapter and SSH egress."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import shlex
import signal
import subprocess
import tempfile
import time

from .commun import VMUpdates, REMOTE, operation_lock, save

ROOT = Path(__file__).resolve().parents[3]
SERVICES = ('proxy', 'donnees', 'metier')
REPORT = ROOT / '.execution/maintenance-vm.json'


def utc():
    return datetime.now(timezone.utc).isoformat()


class Maintenance:
    def __init__(self, args):
        self.args = args
        self.nodes = SERVICES
        self.units = {'proxy': ['nginx'], 'metier': ['intern'], 'donnees': ['postgresql@16-main']}
        self.health_urls = {}
        self.restart_units = {}
        self.allow_reboot = True
        self.report_path = REPORT
        self.config = args.config.resolve()
        self.owner = 'maintenance-' + secrets.token_hex(8)
        self.updates = VMUpdates(self.ssh, self.owner, self.event)
        self.report = dict(owner=self.owner, status='preparing', started_utc=utc(), hosts={})
        self.started = []
        self.created_rule = False

    def event(self, action, **fields):
        value = dict(utc=utc(), action=action, **fields)
        self.report['progress'] = value
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        save(self.report_path, self.report)
        print(json.dumps(value, ensure_ascii=False), flush=True)

    def run(self, command, check=True, timeout=30, **kwargs):
        result = subprocess.run(command, check=False, capture_output=True, timeout=timeout, **kwargs)
        if check and result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace'))
        return result

    def ssh(self, service, command, data=None, check=True, timeout=30):
        return self.run(['ssh', '-F', self.config.name, 'vm-' + service, command],
                        input=data, cwd=self.config.parent, check=check, timeout=timeout)

    def info(self, service):
        raw = self.run(['VBoxManage', 'showvminfo', 'vm-' + service, '--machinereadable']).stdout.decode()
        return raw, next(line.split('=', 1)[1].strip('"') for line in raw.splitlines() if line.startswith('VMState='))

    def wait_ssh(self, service, old_boot=None):
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            try:
                result = self.ssh(service, 'cat /proc/sys/kernel/random/boot_id', check=False, timeout=10)
                if result.returncode == 0 and result.stdout.decode().strip() != old_boot:
                    return
            except subprocess.TimeoutExpired:
                pass
            time.sleep(2)
        raise RuntimeError('SSH indisponible sur ' + service + ' après 240 s')

    def boot(self):
        raw, state = self.info('proxy')
        # VM-specific imports stay out of the production SSH path.
        from .reseau import nat_rule_needed, nat_rules, SSH_RULE
        if nat_rule_needed(SSH_RULE, nat_rules(raw)):
            if state not in ('running', 'poweroff'):
                raise RuntimeError('vm-proxy dans un état transitoire : ' + state)
            command = ['VBoxManage', 'controlvm', 'vm-proxy', 'natpf2', SSH_RULE] if state == 'running' else [
                       'VBoxManage', 'modifyvm', 'vm-proxy', '--natpf2', SSH_RULE]
            self.run(command)
            self.created_rule = True
        for service in self.nodes:
            _, state = self.info(service)
            if state == 'poweroff':
                self.started.append(service)
                self.run(['VBoxManage', 'startvm', 'vm-' + service, '--type', 'headless'])
            elif state != 'running':
                raise RuntimeError('État inattendu pour vm-' + service + ': ' + state)
            self.event('ssh_waiting', service=service)
            self.wait_ssh(service)

    @contextmanager
    def tunnel(self, service):
        with tempfile.TemporaryFile() as errors:
            command = ['ssh', '-F', self.config.name, '-N', '-o', 'ExitOnForwardFailure=yes',
                       '-R', '127.0.0.1:18765', 'vm-' + service]
            process = subprocess.Popen(command, cwd=self.config.parent, stdout=subprocess.DEVNULL,
                                       stderr=errors, start_new_session=True)
            try:
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None:
                        errors.seek(0)
                        raise RuntimeError('Tunnel APT interrompu : ' + errors.read().decode(errors='replace'))
                    result = self.ssh(service, "python3 -c 'import socket; socket.create_connection((\"127.0.0.1\",18765),2).close()'", check=False, timeout=10)
                    if result.returncode == 0 and process.poll() is None:
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Tunnel APT non disponible après 30 s')
                    time.sleep(1)
                yield 'socks5h://127.0.0.1:18765'
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()

    def update_network(self, service):
        return self.tunnel(service)

    def update(self, service):
        self.updates.pause(service, purpose='maintenance')
        self.event('upgrade_start', service=service)
        unit = 'intern-' + self.owner + '-' + service
        command = ['sudo', 'systemd-run', '--unit=' + unit, '--collect', '--property=Type=exec',
                   '/usr/bin/python3', REMOTE, 'update', '--owner', self.owner]
        with self.update_network(service) as proxy:
            if proxy:
                command += ['--proxy', proxy]
            self.ssh(service, shlex.join(command))
            deadline = time.monotonic() + 3600
            while True:
                try:
                    state = self.updates.call(service, 'status')
                except (RuntimeError, subprocess.TimeoutExpired):
                    state = None  # SSH itself can restart during an OpenSSH package upgrade.
                last = state.get('last_update') if state else None
                if last and last['owner'] == self.owner and last['status'] in ('complete', 'failed'):
                    if last['status'] != 'complete':
                        raise RuntimeError('Mise à jour échouée sur ' + service + '; voir /var/lib/intern-maintenance/apt.log')
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('Maintenance toujours active après une heure ; inspecter son unité systemd avant reprise')
                time.sleep(5)
        self.report['hosts'][service] = dict(update=last, rebooted=False)
        if state['reboot_required'] and self.allow_reboot:
            self.event('reboot_start', service=service)
            self.ssh(service, 'sudo systemctl reboot', check=False)
            self.wait_ssh(service, old_boot=state['boot_id'])
            state = self.updates.call(service, 'status')
            if state['reboot_required']:
                raise RuntimeError('Redémarrage encore requis après reboot de ' + service)
            self.report['hosts'][service]['rebooted'] = True
        for unit in self.restart_units.get(service, []):
            self.ssh(service, shlex.join(['sudo', 'systemctl', 'restart', unit]))
        for unit in self.units[service]:
            self.ssh(service, shlex.join(['sudo', 'systemctl', 'is-active', '--quiet', unit]))
        if self.health_urls.get(service):
            self.ssh(service, shlex.join(['curl', '--fail', '--silent', '--show-error', '--max-time', '15', self.health_urls[service]]))
        self.report['hosts'][service]['reboot_required'] = state['reboot_required']
        if state['reboot_required'] and not self.allow_reboot:
            self.event('reboot_pending', service=service, message='Redémarrage requis ; choisir une fenêtre puis utiliser --redemarrer')
        self.report['hosts'][service].update(kernel=state['kernel'], packages_sha256=last['packages_after_sha256'])
        self.event('upgrade_complete', service=service, rebooted=self.report['hosts'][service]['rebooted'])

    def shutdown_started(self):
        from .reseau import SSH_RULE
        for service in reversed(self.nodes):
            if service not in self.started:
                continue
            self.run(['VBoxManage', 'controlvm', 'vm-' + service, 'acpipowerbutton'])
            deadline = time.monotonic() + 120
            while self.info(service)[1] != 'poweroff':
                if time.monotonic() >= deadline:
                    raise RuntimeError('Arrêt non confirmé pour vm-' + service)
                time.sleep(2)
        if self.created_rule:
            _, state = self.info('proxy')
            command = ['VBoxManage', 'controlvm', 'vm-proxy', 'natpf2', 'delete', SSH_RULE.split(',')[0]] if state == 'running' else [
                       'VBoxManage', 'modifyvm', 'vm-proxy', '--natpf2', 'delete', SSH_RULE.split(',')[0]]
            self.run(command)

    def main(self):
        with operation_lock():
            self.event('maintenance_start')
            try:
                self.boot()
                for service in self.nodes:
                    if self.args.action == 'restaurer':
                        self.updates.install(service)
                        state = self.updates.call(service, 'status')
                        if state['pause']:
                            self.updates.owner = state['pause']['owner']
                            self.updates.touched.add(service)
                            self.updates.restore(service, poweroff=service in self.started)
                    else:
                        self.update(service)
                pending = any(h.get('reboot_required') for h in self.report['hosts'].values())
                self.report.update(status='reboot-required' if pending else 'complete', finished_utc=utc())
            except BaseException as error:
                self.report.update(status='failed', error=str(error), finished_utc=utc())
                raise
            finally:
                cleanup_errors = []
                for service in list(self.updates.touched):
                    try:
                        self.updates.restore(service, poweroff=service in self.started)
                    except Exception as error:
                        cleanup_errors.append(service + ': ' + str(error))
                if not cleanup_errors:
                    try:
                        self.shutdown_started()
                    except Exception as error:
                        cleanup_errors.append(str(error))
                if cleanup_errors:
                    self.report.update(status='failed', cleanup_errors=cleanup_errors)
                self.event('maintenance_finished', status=self.report['status'])
                if cleanup_errors:
                    raise RuntimeError('Restauration non terminée ; consulter deploiement/maintenance.py statut')


    def status(self):
        if self.report_path.exists():
            print(self.report_path.read_text())
        else:
            print('Aucune maintenance explicite enregistrée pour cette cible.')
        for service in self.nodes:
            _, state = self.info(service)
            print(service + ': ' + state)
            if state == 'running':
                found = self.ssh(service, 'test -f ' + REMOTE, check=False)
                if found.returncode == 0:
                    print(json.dumps(self.updates.call(service, 'status'), ensure_ascii=False, indent=2))
