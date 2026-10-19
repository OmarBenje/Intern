"""Prepare a separate application venv and switch it with rollback on failed readiness.

Run as root in vm-metier, outside measurements; never changes /usr/bin/python3.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request

PROJECT = Path('/opt/intern/metier')


def run(*parts, **kwargs):
    return subprocess.run(parts, check=True, **kwargs)


def version(interpreter):
    return run(str(interpreter), '-c', 'import platform;print(platform.python_version())',
               capture_output=True, text=True).stdout.strip()


def prepare(interpreter, expected):
    if version(interpreter) != expected:
        raise RuntimeError('Downloaded interpreter does not match the pinned Python version')
    stage = PROJECT / ('.venv-python-' + expected)
    current = PROJECT / '.venv'
    if current.is_symlink() and current.resolve() == stage.resolve():
        raise RuntimeError('This version is already active; inspect it before modifying its environment')
    if stage.is_symlink():
        raise RuntimeError('Stage must be a real directory, not a symbolic link')
    (stage / '.python-validation.json').unlink(missing_ok=True)
    run('install', '-d', '-o', 'intern', '-g', 'intern', '-m', '0755', str(stage))
    run('runuser', '-u', 'intern', '--', 'env', 'UV_CACHE_DIR=/var/cache/intern-uv',
        'UV_PYTHON_DOWNLOADS=never', 'UV_PROJECT_ENVIRONMENT=' + str(stage),
        'uv', 'sync', '--project', str(PROJECT), '--frozen', '--no-dev', '--offline',
        '--python', str(interpreter))
    if version(stage / 'bin/python') != expected:
        raise RuntimeError('Prepared environment uses a different Python version')
    return stage


def activate(stage):
    current = PROJECT / '.venv'
    expected = (PROJECT / '.python-version').read_text().strip()
    if version(stage / 'bin/python') != expected:
        raise RuntimeError('Stage Python does not match the pin')
    if current.is_symlink() and current.resolve() == stage.resolve():
        return dict(already_active=True, python=expected)
    validation = json.loads((stage / '.python-validation.json').read_text())
    if validation.get('exit_code') != 0 or validation.get('python') != expected:
        raise RuntimeError('Successful tests for this Python version are required before activation')
    if not current.exists():
        raise RuntimeError('No existing environment available for rollback')
    backup = PROJECT / ('.venv-before-python-' + str(time.time_ns()))
    temporary = PROJECT / ('.venv-switch-' + str(time.time_ns()))
    active = subprocess.run(['systemctl', 'is-active', '--quiet', 'intern']).returncode == 0
    temporary.symlink_to(stage)
    moved = False
    try:
        if active:
            run('systemctl', 'stop', 'intern')
        os.replace(current, backup)
        moved = True
        os.replace(temporary, current)
        if active:
            run('systemctl', 'start', 'intern')
            deadline = time.monotonic() + 60
            while True:
                try:
                    with urllib.request.urlopen('http://10.10.10.20:8000/health/ready/', timeout=3) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError('Application not ready after Python switch')
                time.sleep(1)
    except BaseException:
        if moved:
            current.unlink(missing_ok=True)
            os.replace(backup, current)
        if active:
            run('systemctl', 'restart', 'intern')
        raise
    finally:
        temporary.unlink(missing_ok=True)
    return dict(python=expected, backup=str(backup), stage=str(stage), service_was_active=active)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preparer', 'activer'))
    parser.add_argument('--interpreter', type=Path)
    args = parser.parse_args()
    expected = (PROJECT / '.python-version').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', expected):
        raise RuntimeError('Pin must be an exact Python version')
    if args.action == 'preparer':
        if args.interpreter is None:
            parser.error('--interpreter is required for preparer')
        print(prepare(args.interpreter, expected))
    else:
        print(json.dumps(activate(PROJECT / ('.venv-python-' + expected))))


if __name__ == '__main__':
    main()
