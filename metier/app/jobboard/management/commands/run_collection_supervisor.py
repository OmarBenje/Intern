"""Local collector supervision; container deployments use Compose restart policies."""

import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def worker_commands():
    return {
        "catalogue": [
            "run_catalogue_worker",
            "--imports-only",
            "--limit",
            "20",
            "--poll-interval",
            "2",
        ],
        "maintenance": [
            "run_catalogue_worker",
            "--maintenance-only",
            "--limit",
            "5",
            "--poll-interval",
            "60",
        ],
        "probes": ["run_ats_probe_worker", "--limit", "1", "--poll-interval", "60"],
        **{
            name: [f"run_{name}_worker", "--limit", "1", "--poll-interval", "30"]
            for name in ("jobspy", "eures", "wttj", "jobtech", "bundesagentur", "nav")
        },
    }


def restart_delay(failures):
    return min(300, 5 * 2 ** min(failures - 1, 6))


class Command(BaseCommand):
    help = "Supervise local collection workers with exclusive lock and bounded restart backoff."

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR).resolve()
        key = hashlib.sha256(str(root).encode()).hexdigest()[:12]
        directory = Path(tempfile.gettempdir()) / f"intern-collectors-{key}"
        directory.mkdir(mode=0o700, exist_ok=True)
        with (directory / "supervisor.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CommandError(
                    "A collection supervisor already owns this workspace"
                ) from exc
            self.run_workers(root, directory)

    def run_workers(self, root, directory):
        stopping = False

        def stop(signum, frame):
            nonlocal stopping
            stopping = True

        previous = {
            sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)
        }
        children, failures, retry_at, started = {}, {}, {}, {}
        commands = worker_commands()
        self.stdout.write(f"Collector logs and status: {directory}")
        try:
            while not stopping:
                now = time.monotonic()
                for name, command in commands.items():
                    child = children.get(name)
                    if child and child.poll() is not None:
                        failures[name] = (
                            1
                            if now - started[name] >= 300
                            else failures.get(name, 0) + 1
                        )
                        retry_at[name] = now + restart_delay(failures[name])
                        self.stderr.write(
                            f"{name} exited {child.returncode}; restart in {restart_delay(failures[name])}s"
                        )
                        del children[name]
                    if name not in children and now >= retry_at.get(name, 0):
                        with (directory / f"{name}.log").open("ab") as log:
                            children[name] = subprocess.Popen(
                                [
                                    sys.executable,
                                    "-u",
                                    str(root / "manage.py"),
                                    *command,
                                ],
                                cwd=root,
                                stdin=subprocess.DEVNULL,
                                stdout=log,
                                stderr=log,
                                start_new_session=True,
                            )
                        started[name] = now
                status = {
                    "supervisor_pid": os.getpid(),
                    "updated_at": time.time(),
                    "workers": {
                        name: {
                            "pid": children[name].pid if name in children else None,
                            "running": name in children
                            and children[name].poll() is None,
                            "failures": failures.get(name, 0),
                        }
                        for name in commands
                    },
                }
                temporary = directory / "status.tmp"
                temporary.write_text(json.dumps(status, indent=2))
                temporary.replace(directory / "status.json")
                time.sleep(1)
        finally:
            # Only child process groups created by this supervisor are signalled.
            for child in children.values():
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
            deadline = time.monotonic() + 10
            for child in children.values():
                try:
                    child.wait(timeout=max(0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            for sig, handler in previous.items():
                signal.signal(sig, handler)
