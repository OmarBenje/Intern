"""Root-only VM maintenance helper: owned APT pause, status and explicit updates."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess

STATE = Path('/var/lib/intern-maintenance')
UNITS = ('apt-daily.timer', 'apt-daily-upgrade.timer', 'apt-daily.service', 'apt-daily-upgrade.service')
TIMERS = UNITS[:2]
LOCKS = ('/var/lib/dpkg/lock-frontend', '/var/lib/dpkg/lock', '/var/lib/apt/lists/lock', '/var/cache/apt/archives/lock')


def now():
    return datetime.now(timezone.utc).isoformat()


def save(name, data):
    path = STATE / name
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def read(name):
    path = STATE / name
    return json.loads(path.read_text()) if path.exists() else None


def run(*command, check=True):
    return subprocess.run(command, text=True, capture_output=True, check=check)


def property_of(unit, key):
    return run('systemctl', 'show', unit, '--property=' + key, '--value').stdout.strip()


def busy():
    reasons = [unit for unit in UNITS[2:] if property_of(unit, 'ActiveState') in ('active', 'activating', 'deactivating')]
    for name in LOCKS:
        if not Path(name).exists():
            continue
        with open(name, 'r+') as stream:
            try:
                fcntl.lockf(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                reasons.append(name)
    return reasons


def packages():
    result = run('dpkg-query', '-W', '-f=${binary:Package}\t${Version}\n').stdout
    return hashlib.sha256(result.encode()).hexdigest()


def log_activity(path):
    source = Path(path)
    return datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat() if source.exists() else None


def status():
    return dict(last_apt_activity_utc=log_activity('/var/log/apt/history.log'),
                last_auto_update_activity_utc=log_activity('/var/log/unattended-upgrades/unattended-upgrades.log'),pause=read('pause.json'), last_update=read('last-update.json'), busy=busy(),
                reboot_required=Path('/var/run/reboot-required').exists(),
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                kernel=os.uname().release,
                timers={unit: dict(active=property_of(unit, 'ActiveState'),
                                   next=property_of(unit, 'NextElapseUSecRealtime')) for unit in TIMERS})


@contextmanager
def exclusive():
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / 'operation.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('A maintenance operation is already running; inspect status') from None
        yield


def pause(owner, purpose):
    previous = read('pause.json')
    if previous and previous['owner'] != owner:
        raise RuntimeError('Updates already paused by ' + previous['owner'] + '; restore that operation explicitly')
    if previous is None:
        present = [unit for unit in UNITS if property_of(unit, 'LoadState') != 'not-found']
        previous = dict(owner=owner, purpose=purpose, started_utc=now(),
                        active_timers=[unit for unit in TIMERS if property_of(unit, 'ActiveState') == 'active'],
                        runtime_masks=[unit for unit in present if property_of(unit, 'UnitFileState') == 'masked-runtime'],
                        owned_masks=[unit for unit in present if property_of(unit, 'UnitFileState') != 'masked'])
        # Persist ownership before any mutation, including a failure part way through.
        save('pause.json', previous)
    for timer in TIMERS:
        if property_of(timer, 'LoadState') != 'not-found':
            run('systemctl', 'stop', timer)
    if previous['owned_masks']:
        # Persistent masks survive VM shutdown between repetitions. No active APT service is stopped.
        run('systemctl', 'mask', *previous['owned_masks'])
    result = status()
    if not result['busy']:
        result['packages_sha256'] = packages()
        result['dpkg_audit'] = run('dpkg', '--audit').stdout.strip()
    return result


def restore(owner, start_timers=True):
    state = read('pause.json')
    if not state:
        return status()
    if state['owner'] != owner:
        raise RuntimeError('Refuse to restore another operation: ' + state['owner'])
    if busy():
        raise RuntimeError('APT/dpkg still active; wait before restoring update timers')
    if state['owned_masks']:
        run('systemctl', 'unmask', *state['owned_masks'])
    if state.get('runtime_masks'):
        run('systemctl', 'mask', '--runtime', *state['runtime_masks'])
    if start_timers and state['active_timers']:
        run('systemctl', 'start', *state['active_timers'])
    save('last-pause.json', dict(**state, restored_utc=now(), timers_started=start_timers))
    (STATE / 'pause.json').unlink()
    return dict(status(), restored_timers=state['active_timers'])


def update(owner, proxy):
    state = read('pause.json')
    if not state or state['owner'] != owner or state['purpose'] != 'maintenance':
        raise RuntimeError('Explicit maintenance pause required before updating')
    if busy():
        raise RuntimeError('APT/dpkg still active; no upgrade started')
    report = dict(owner=owner, status='running', started_utc=now(), packages_before_sha256=packages())
    save('last-update.json', report)
    try:
        audit = run('dpkg', '--audit').stdout.strip()
        if audit:
            raise RuntimeError('dpkg audit requires repair before upgrading: ' + audit)
        options = ['-o', 'DPkg::Lock::Timeout=60', '-o', 'Acquire::Retries=2',
                   '-o', 'Acquire::http::Timeout=30', '-o', 'Acquire::https::Timeout=30',
                   '-o', 'Dpkg::Options::=--force-confdef', '-o', 'Dpkg::Options::=--force-confold']
        if proxy:
            options += ['-o', 'Acquire::http::Proxy=' + proxy, '-o', 'Acquire::https::Proxy=' + proxy]
        environment = dict(os.environ, DEBIAN_FRONTEND='noninteractive', NEEDRESTART_MODE='a')
        with (STATE / 'apt.log').open('a') as log:
            for command in (['apt-get', *options, '-o', 'APT::Update::Error-Mode=any', 'update'],
                            ['apt-get', *options, '-y', 'upgrade']):
                log.write('\n' + now() + ' ' + ' '.join(command) + '\n')
                log.flush()
                subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
        audit = run('dpkg', '--audit').stdout.strip()
        if audit:
            raise RuntimeError('Post-update dpkg audit: ' + audit)
        report.update(status='complete', packages_after_sha256=packages(),
                      reboot_required=Path('/var/run/reboot-required').exists())
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        report['finished_utc'] = now()
        save('last-update.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('pause', 'restore', 'status', 'update'))
    parser.add_argument('--owner', default='')
    parser.add_argument('--purpose', choices=('measurement', 'maintenance'), default='measurement')
    parser.add_argument('--poweroff', action='store_true')
    parser.add_argument('--proxy', default='')
    args = parser.parse_args()
    if args.action == 'status':
        print(json.dumps(status()))
        return
    if not args.owner:
        parser.error('An operation owner is required')
    with exclusive():
        if args.action == 'pause':
            result = pause(args.owner, args.purpose)
        elif args.action == 'restore':
            result = restore(args.owner, start_timers=not args.poweroff)
        else:
            result = update(args.owner, args.proxy)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
