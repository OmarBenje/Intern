"""Wait for a VM over SSH, bounding and cleaning up every connection attempt."""

import argparse
import os
from pathlib import Path
import signal
import subprocess
import time


def wait_ssh(config, vm, seconds, log):
    deadline = time.monotonic() + seconds
    command = ["ssh", "-F", config.name, vm, "true"]
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        process = subprocess.Popen(command, cwd=config.parent, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, start_new_session=True)
        expired = False
        try:
            _, diagnostic = process.communicate(timeout=max(.01, min(15, remaining)))
        except subprocess.TimeoutExpired:
            expired = True
            # ProxyJump can leave a child holding stderr open after its parent exits.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _, diagnostic = process.communicate()
            diagnostic = (diagnostic or b"") + b"\nTentative SSH expiree ; processus de connexion termines.\n"
        log.write_bytes(diagnostic or b"")
        if not expired and process.returncode == 0:
            return
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(1, remaining))
    print(log.read_text(errors="replace"), end="")
    raise SystemExit(f"SSH indisponible : {vm} après {seconds} s. Voir {log}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--vm", required=True)
    parser.add_argument("--seconds", type=int, required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds doit être positif")
    args.log.parent.mkdir(parents=True, exist_ok=True)
    wait_ssh(args.config.resolve(), args.vm, args.seconds, args.log)


if __name__ == "__main__":
    main()
