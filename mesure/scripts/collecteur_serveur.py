"""Timestamp received server samples with the injector host's clock."""

import argparse
import json
import signal
import subprocess
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True, help="Trusted JSON argv; no shell evaluation")
    args = parser.parse_args()
    process = subprocess.Popen(json.loads(args.command), stdout=subprocess.PIPE, text=True)

    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    try:
        for line in process.stdout:
            row = json.loads(line)
            row["server_epoch_s"] = row["epoch_s"]
            row["epoch_s"] = time.time()
            row["time_basis"] = "host_receipt_time"
            print(json.dumps(row), flush=True)
        if process.wait():
            raise RuntimeError("Server collector failed")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    main()
