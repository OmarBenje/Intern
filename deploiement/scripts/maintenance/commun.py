"""Host helpers shared by measurement campaigns and explicit VM maintenance."""

from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import shlex
import time

ROOT = Path(__file__).resolve().parents[3]

REMOTE = '/opt/intern-maintenance/maintenance_invite.py'


@contextmanager
def operation_lock(path=None):
    path = path or ROOT / '.execution/operations-vm.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Mesure ou maintenance déjà active ; attendre sa fin') from None
        yield


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


class VMUpdates:
    def __init__(self, ssh, owner, event=None):
        self.ssh = ssh
        self.owner = owner
        self.event = event or (lambda action, **fields: print(json.dumps(dict(action=action, **fields)), flush=True))
        self.touched = set()
        self.fingerprints = {}

    def install(self, service):
        self.ssh(service, 'sudo install -d -m 0755 /opt/intern-maintenance')
        self.ssh(service, 'sudo tee ' + REMOTE + ' >/dev/null', data=Path(__file__).with_name('invite.py').read_bytes())
        self.ssh(service, 'sudo chmod 0644 ' + REMOTE)

    def call(self, service, action, *extra):
        command = ['sudo', 'python3', REMOTE, action]
        if action != 'status':
            command += ['--owner', self.owner]
        command += list(extra)
        result = self.ssh(service, shlex.join(command), timeout=30)
        return json.loads(result.stdout)

    def pause(self, service, purpose='measurement', check_stop=lambda: None):
        self.install(service)
        self.touched.add(service)
        deadline = time.monotonic() + 900
        self.event('updates_pausing', service=service, purpose=purpose)
        while True:
            check_stop()
            state = self.call(service, 'pause', '--purpose', purpose)
            if not state['busy']:
                break
            self.event('updates_waiting', service=service, busy=state['busy'])
            if time.monotonic() >= deadline:
                raise RuntimeError('Mise à jour toujours active sur ' + service + ' après 900 s ; aucune mesure lancée')
            time.sleep(5)
        if purpose == 'measurement':
            if state.get('reboot_required') or state.get('dpkg_audit'):
                raise RuntimeError('Maintenance requise sur ' + service + ' : voir deploiement/MAINTENANCE.md et deploiement/maintenance.py')
            fingerprint = state['packages_sha256']
            previous = self.fingerprints.setdefault(service, fingerprint)
            if fingerprint != previous:
                raise RuntimeError('Paquets modifiés entre séries sur vm-' + service + '; refaire une campagne après maintenance')
        self.event('updates_paused', service=service, packages_sha256=state['packages_sha256'])
        return state

    def restore(self, service, poweroff=False):
        extra = ['--poweroff'] if poweroff else []
        result = self.call(service, 'restore', *extra)
        self.touched.discard(service)
        self.event('updates_restored', service=service, timers_started=not poweroff)
        return result
