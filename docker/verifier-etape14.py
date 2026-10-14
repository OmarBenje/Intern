"""Measure the three-tier deployment on Docker Engine, preserving its database."""

import argparse
import json
import os
import platform
import socket
import statistics
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def process_map():
    result = {}
    for path in Path("/proc").glob("[0-9]*/status"):
        try:
            fields = dict(line.split(":", 1) for line in path.read_text().splitlines())
            result[int(path.parent.name)] = {
                "parent": int(fields["PPid"]),
                "name": fields["Name"].strip(),
                "rss_bytes": int(fields.get("VmRSS", "0 kB").split()[0]) * 1024,
            }
        except (OSError, ValueError):
            continue
    return result


def memory(engine_pid, container_pids, container_ids, data_root):
    processes = process_map()
    # Include rootless networking helpers as well as dockerd/containerd.
    engine_root = engine_pid
    parent = processes[engine_pid]["parent"]
    while parent in processes:
        if processes[parent]["name"] == "rootlesskit":
            engine_root = parent
        parent = processes[parent]["parent"]
    selected = {engine_root, *container_pids}
    # Shims and FUSE helpers may be reparented outside the daemon tree.
    for pid, data in processes.items():
        if data["name"].startswith(("containerd-shim", "fuse-overlayfs")):
            try:
                command = Path(f"/proc/{pid}/cmdline").read_bytes().decode()
            except OSError:
                continue
            if data_root in command or any(identifier in command for identifier in container_ids):
                selected.add(pid)
    while True:
        added = {pid for pid, data in processes.items() if data["parent"] in selected}
        if added <= selected:
            break
        selected |= added
    rows = [{"pid": pid, **processes[pid]} for pid in sorted(selected) if pid in processes]
    return {"rss_bytes": sum(row["rss_bytes"] for row in rows), "processes": rows}


def disk_usage(paths):
    # Count physical hard links once; never walk merged overlay views twice.
    seen = set()
    total = allocated = files = 0
    for base in paths:
        def error(exc):
            raise exc
        for folder, _, names in os.walk(base, onerror=error):
            for name in names:
                path = Path(folder) / name
                st = path.lstat()
                if (st.st_dev, st.st_ino) in seen:
                    continue
                seen.add((st.st_dev, st.st_ino))
                total += st.st_size
                allocated += st.st_blocks * 512
                files += 1
    return {"file_bytes": total, "allocated_bytes": allocated, "files": files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--engine-pidfile", required=True)
    args = parser.parse_args()
    out = ROOT / "docker/docs"
    out.mkdir(exist_ok=True)
    docker = [args.docker]
    compose = docker + ["compose", "--env-file", args.env_file,
                        "-f", "docker/compose.yaml", "-p", args.project]

    def run(cmd, check=True):
        return subprocess.run(cmd, cwd=ROOT, check=check, capture_output=True, text=True)

    def inspect():
        ids = run(compose + ["ps", "-q"]).stdout.split()
        if len(ids) != 3:
            raise RuntimeError("Exactly three running containers are required")
        data = json.loads(run(docker + ["inspect", *ids]).stdout)
        return {d["Config"]["Labels"]["com.docker.compose.service"]: d for d in data}

    info = json.loads(run(docker + ["info", "--format", "{{json .}}"]).stdout)
    if "podman" in info["ServerVersion"].lower():
        raise RuntimeError("This campaign requires Docker Engine")
    services = inspect()
    assert set(services) == {"proxy", "metier", "donnees"}
    assert all(d["State"]["Health"]["Status"] == "healthy" for d in services.values())
    networks = {s: set(d["NetworkSettings"]["Networks"]) for s, d in services.items()}
    assert not networks["proxy"] & networks["donnees"]
    assert len(networks["proxy"]) == len(networks["donnees"]) == 1
    assert len(networks["metier"]) == 2
    assert services["proxy"]["HostConfig"]["PortBindings"] == {
        "80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8080"}]
    }
    assert not services["metier"]["HostConfig"]["PortBindings"]
    assert not services["donnees"]["HostConfig"]["PortBindings"]

    def address(service, shared_with=None):
        nets = services[service]["NetworkSettings"]["Networks"]
        network = next(iter(nets)) if shared_with is None else next(iter(networks[service] & networks[shared_with]))
        return nets[network]["IPAddress"]

    matrix = []
    for source in ["hote", "proxy", "metier", "donnees"]:
        for target, port in [("proxy", 80), ("metier", 8000), ("donnees", 5432)]:
            if source == target:
                continue
            expected = source == "hote" and target == "proxy" or source != "hote" and bool(networks[source] & networks[target])
            host = "127.0.0.1" if source == "hote" and target == "proxy" else address(target, source if source != "hote" and expected else None)
            actual_port = 8080 if source == "hote" and target == "proxy" else port
            reason = ""
            if source == "hote":
                try:
                    with socket.create_connection((host, actual_port), timeout=2):
                        actual = True
                except OSError as exc:
                    actual, reason = False, str(exc)
            else:
                name = services[source]["Id"]
                if source == "proxy":
                    cmd = ["nc", "-z", "-v", "-w", "2", host, str(port)]
                elif source == "donnees":
                    cmd = ["timeout", "2", "bash", "-c", 'exec 3<>/dev/tcp/"$1"/"$2"', "probe", host, str(port)]
                else:
                    cmd = [".venv/bin/python", "-c", "import socket,sys; socket.create_connection((sys.argv[1],int(sys.argv[2])),timeout=2).close()", host, str(port)]
                result = run(docker + ["exec", name, *cmd], check=False)
                actual = result.returncode == 0
                reason = (result.stderr or result.stdout).strip()[-600:]
                if result.returncode == 124:
                    reason = "Connection timeout (2 seconds)"
            matrix.append({"source": source, "target": target, "host": host, "port": actual_port,
                           "expected": bool(expected), "connected": actual, "detail": reason})
            if actual != bool(expected):
                save(out / "joignabilite-etape14.json", matrix)
                raise RuntimeError(f"Unexpected reachability: {source} -> {target}")
    save(out / "joignabilite-etape14.json", matrix)
    print("PASS : neuf liaisons, services sains et isolation", flush=True)

    sql = run(docker + ["exec", services["metier"]["Id"], "sh", "-c",
        'export PGHOST="$POSTGRES_HOST" PGPORT="$POSTGRES_PORT" PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB" PGPASSWORD="$POSTGRES_PASSWORD"; exec .venv/bin/python /app/donnees/verifier.py']).stdout
    assert "PASS — 34" in sql
    (out / "sql-etape14.txt").write_text(sql)
    images = json.loads(run(docker + ["image", "inspect", *{d["Image"] for d in services.values()}]).stdout)
    engine_pid = int(Path(args.engine_pidfile).read_text())
    trials = []
    url = "http://127.0.0.1:8080/api/v1/offers/"

    def catalogue():
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read())
            assert response.status == 200 and data["count"] == 4
            return data

    for trial in range(1, 4):
        run(compose + ["stop"])
        old = json.loads(run(docker + ["inspect", *[d["Id"] for d in services.values()]]).stdout)
        assert all(not d["State"]["Running"] for d in old)
        start = time.monotonic()
        proc = subprocess.Popen(compose + ["up", "-d", "--no-build"], cwd=ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            while True:
                try:
                    catalogue()
                    startup = time.monotonic() - start
                    break
                except (OSError, AssertionError, ValueError):
                    if time.monotonic() - start > 180 or proc.poll() not in (None, 0):
                        raise RuntimeError("Startup failed")
                    time.sleep(0.5)
            _, error = proc.communicate(timeout=180)
            if proc.returncode:
                raise RuntimeError(error)
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.communicate(timeout=10)
        time.sleep(30)
        services = inspect()
        assert all(d["State"]["Health"]["Status"] == "healthy" for d in services.values())
        container_pids = [d["State"]["Pid"] for d in services.values()]
        rss = memory(engine_pid, container_pids,
                     [d["Id"] for d in services.values()], info["DockerRootDir"])
        paths = set()
        for item in [*images, *services.values()]:
            driver = item["GraphDriver"]["Data"]
            if "UpperDir" not in driver:
                raise RuntimeError("Disk measurement requires overlay/fuse-overlayfs metadata")
            paths.add(driver["UpperDir"])
            paths.update(filter(None, driver.get("LowerDir", "").split(":")))
        for d in services.values():
            for mount in d["Mounts"]:
                if mount["Type"] == "volume":
                    paths.add(mount["Source"])
        disk = disk_usage(paths)
        latencies = []
        for _ in range(10):
            began = time.monotonic()
            catalogue()
            latencies.append((time.monotonic() - began) * 1000)
        trials.append({"trial": trial, "startup_s": startup, "memory": rss,
                       "disk": disk, "latency_ms": latencies,
                       "latency_median_ms": statistics.median(latencies)})
        print(f"Série {trial} : démarrage {startup:.3f} s ; RSS {rss['rss_bytes']} octets ; latence {statistics.median(latencies):.3f} ms", flush=True)

    medians = {
        "startup_s": statistics.median(t["startup_s"] for t in trials),
        "rss_bytes": statistics.median(t["memory"]["rss_bytes"] for t in trials),
        "disk_file_bytes": statistics.median(t["disk"]["file_bytes"] for t in trials),
        "disk_allocated_bytes": statistics.median(t["disk"]["allocated_bytes"] for t in trials),
        "latency_ms": statistics.median(t["latency_median_ms"] for t in trials),
    }
    save(out / "mesures-etape14.json", {
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "host": {"release": platform.release(), "system": platform.system(), "logical_cpus": os.cpu_count()},
        "docker": info["ServerVersion"], "compose": run(docker + ["compose", "version", "--short"]).stdout.strip(),
        "security_options": info["SecurityOptions"], "storage_driver": info["Driver"],
        "images": [{"id": d["Id"], "tags": d["RepoTags"], "size_bytes": d["Size"]} for d in images],
        "protocol": {"trials": 3, "idle_s": 30, "requests_per_trial": 10,
                     "url": url, "timeout_s": 5, "startup_poll_s": 0.5,
                     "memory": "Somme RSS des conteneurs et du moteur, avec ses auxiliaires rootless.",
                     "disk": "Fichiers des couches uniques des trois images et conteneurs, plus volume ; caches de build, archives et snapshots exclus.",
                     "setup_time": "Non chronométré depuis zéro ; aucun résultat reconstitué."},
        "trials": trials, "medians": medians,
    })
    print("PASS : trois séries, médianes et trente latences conservées", flush=True)


if __name__ == "__main__":
    main()
