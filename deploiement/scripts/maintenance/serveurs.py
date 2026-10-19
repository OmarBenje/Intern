"""Maintenance of existing Ubuntu/Debian production servers over SSH."""

from contextlib import nullcontext
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from .machines import Maintenance, ROOT


def configuration(path):
    path = path.resolve()
    data = json.loads(path.read_text())
    ssh = Path(data['ssh_config']).expanduser()
    data['ssh_config'] = ssh if ssh.is_absolute() else (path.parent / ssh).resolve()
    if not data['ssh_config'].is_file():
        raise ValueError('Configuration SSH absente : ' + str(data['ssh_config']))
    if data.get('egress', 'direct') not in ('direct', 'ssh'):
        raise ValueError('egress doit être direct ou ssh')
    hosts = data['hosts']
    if not hosts or len({host['alias'] for host in hosts}) != len(hosts):
        raise ValueError('Définir des alias SSH distincts et au moins un serveur')
    for host in hosts:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', host['alias']):
            raise ValueError('Alias SSH invalide')
        units = host.get('services', [])
        if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9@_.:-]*', unit) for unit in units):
            raise ValueError('Nom de service systemd invalide')
        if not units and not host.get('health_url'):
            raise ValueError('Prévoir au moins un service ou une URL de santé par serveur')
        if not set(host.get('restart_services', [])) <= set(units):
            raise ValueError('Les services à redémarrer doivent figurer dans services')
        if host.get('health_url'):
            parsed = urlsplit(host['health_url'])
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('URL de santé HTTP(S) sans identifiants requise')
    return data


class Servers(Maintenance):
    def __init__(self, args, profile):
        super().__init__(args)
        self.profile = profile
        self.nodes = tuple(host['alias'] for host in profile['hosts'])
        self.units = {host['alias']: host.get('services', []) for host in profile['hosts']}
        self.restart_units = {host['alias']: host.get('restart_services', []) for host in profile['hosts']}
        self.health_urls = {host['alias']: host.get('health_url') for host in profile['hosts']}
        self.allow_reboot = args.redemarrer
        self.report_path = ROOT / '.execution/maintenance-production.json'
        self.report['target'] = 'production-ssh'
        self.report['aliases'] = list(self.nodes)

    def ssh(self, service, command, data=None, check=True, timeout=30):
        return self.run(['ssh', '-F', self.config.name, '-o', 'BatchMode=yes',
                         '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
                         service, command], input=data, cwd=self.config.parent,
                        check=check, timeout=timeout)

    def info(self, service):
        try:
            result = self.ssh(service, 'true', check=False, timeout=15)
            return '', 'running' if result.returncode == 0 else 'ssh-unreachable'
        except subprocess.TimeoutExpired:
            return '', 'ssh-unreachable'

    def boot(self):
        # These servers already run in production. Only verify SSH; no VM management.
        for service in self.nodes:
            self.event('ssh_waiting', service=service)
            self.wait_ssh(service)

    def update_network(self, service):
        return self.tunnel(service) if self.profile.get('egress') == 'ssh' else nullcontext(None)

    def shutdown_started(self):
        pass  # Production servers stay online after maintenance.
