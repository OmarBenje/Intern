"""Read Linux service process counters; stream JSON samples without command lines."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def snapshot(root):
    processes = {}
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            values = path.read_text().rsplit(")", 1)[1].split()
            processes[int(path.parent.name)] = {
                "parent": int(values[1]),
                "start_ticks": int(values[19]),
                "cpu_ticks": int(values[11]) + int(values[12]),
                "rss_bytes": int(values[21]) * os.sysconf("SC_PAGE_SIZE"),
            }
        except (OSError, ValueError, IndexError):
            continue
    selected = {root}
    while True:
        children = {pid for pid, row in processes.items() if row["parent"] in selected}
        if children <= selected:
            break
        selected |= children
    rows = {}
    for pid in selected:
        if pid not in processes:
            continue
        row = processes[pid]
        io = {}
        try:
            io = {key: int(value) for key, value in
                  (line.split(":", 1) for line in Path(f"/proc/{pid}/io").read_text().splitlines())}
        except OSError:
            pass
        row["read_bytes"] = io.get("read_bytes")
        row["write_bytes"] = io.get("write_bytes")
        rows[pid] = row
    if root not in rows:
        raise RuntimeError("Service root process disappeared")
    return rows


def interval(previous, current, seconds):
    delta = {}
    for field in ("cpu_ticks", "read_bytes", "write_bytes"):
        if any(row[field] is None for row in current.values()):
            delta[field] = None
            continue
        total = 0
        for pid, row in current.items():
            earlier = previous.get(pid)
            baseline = earlier[field] if earlier and earlier["start_ticks"] == row["start_ticks"] else 0
            total += max(0, row[field] - (baseline or 0))
        delta[field] = total
    return {
        "cpu_pct": delta["cpu_ticks"] / os.sysconf("SC_CLK_TCK") / seconds * 100,
        "rss_bytes": sum(row["rss_bytes"] for row in current.values()),
        "read_bytes_per_s": delta["read_bytes"] / seconds if delta["read_bytes"] is not None else None,
        "write_bytes_per_s": delta["write_bytes"] / seconds if delta["write_bytes"] is not None else None,
        "processes": len(current),
    }


def cgroup_snapshot(pid):
    try:
        entry = next(line[3:] for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines() if line.startswith("0::"))
        group = Path("/sys/fs/cgroup") / entry.lstrip("/")
        cpu = dict(line.split() for line in (group / "cpu.stat").read_text().splitlines())
        io = [dict(field.split("=", 1) for field in line.split()[1:])
              for line in (group / "io.stat").read_text().splitlines()]
        return {"cpu_us": int(cpu["usage_usec"]), "memory_bytes": int((group / "memory.current").read_text()),
                "read_bytes": sum(int(row.get("rbytes", 0)) for row in io),
                "write_bytes": sum(int(row.get("wbytes", 0)) for row in io)}
    except (OSError, StopIteration, KeyError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--service", required=True, choices=["proxy", "metier", "donnees"])
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--sql-command", help="JSON argv for a trusted local statistics query")
    args = parser.parse_args()
    previous, last = snapshot(args.pid), time.monotonic()
    group_before = cgroup_snapshot(args.pid)
    while True:
        time.sleep(args.interval)
        now, current = time.monotonic(), snapshot(args.pid)
        row = {"epoch_s": time.time(), "service": args.service,
               "interval_s": now - last, **interval(previous, current, now - last)}
        group_now = cgroup_snapshot(args.pid)
        row["cpu_io_method"] = "processes_currently_alive"
        if group_before and group_now:
            row.update({"cpu_pct": max(0, group_now["cpu_us"] - group_before["cpu_us"]) / 10000 / (now - last),
                        "memory_cgroup_bytes": group_now["memory_bytes"],
                        "read_bytes_per_s": max(0, group_now["read_bytes"] - group_before["read_bytes"]) / (now - last),
                        "write_bytes_per_s": max(0, group_now["write_bytes"] - group_before["write_bytes"]) / (now - last),
                        "cpu_io_method": "cgroup_v2"})
        if args.sql_command:
            result = subprocess.run(json.loads(args.sql_command), check=True, capture_output=True, text=True, timeout=10)
            row.update(json.loads(result.stdout))
        print(json.dumps(row), flush=True)
        previous, last = current, now
        group_before = group_now


if __name__ == "__main__":
    main()
