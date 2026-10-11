#!/usr/bin/env python3
"""Matrice réelle et trois séries de mesures sur les VM existantes.

Usage : python3 verifier_etape10.py /repertoire/local/des/VM
Les trois VM doivent fonctionner. L'accès SSH temporaire est géré ici.
"""
import argparse
from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
import platform
import socket
import statistics
import subprocess
import time
from urllib.request import urlopen

from reseau_etape8 import info, ssh, vbox, wait_off, wait_ssh


NAMES = ("vm-donnees", "vm-metier", "vm-proxy")
URL = "http://127.0.0.1:8080/api/v1/offers/"


def request(url):
    with urlopen(url, timeout=5) as response:
        body = json.load(response)
        if response.status != 200:
            raise RuntimeError("HTTP 200 attendu")
        return body


def connect(address, port):
    start = time.monotonic()
    try:
        with socket.create_connection((address, port), timeout=2):
            return {"reachable": True, "elapsed_s": time.monotonic() - start}
    except OSError as error:
        return {"reachable": False, "elapsed_s": time.monotonic() - start,
                "error": str(error)}


def memory(identities):
    result = {}
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            args = (process / "cmdline").read_bytes().split(b"\0")
            if not args or Path(args[0].decode()).name not in {"VBoxHeadless", "VirtualBoxVM"}:
                continue
            for name, identity in identities.items():
                if identity.encode() not in args:
                    continue
                status = (process / "status").read_text()
                rss = next(int(line.split()[1]) * 1024 for line in status.splitlines()
                           if line.startswith("VmRSS:"))
                result[name] = {"rss_bytes": rss}
        except (OSError, StopIteration):
            continue
    if set(result) != set(identities):
        raise RuntimeError("Les trois processus VirtualBox n'ont pas été identifiés.")
    return result


def disk(root):
    files = []
    for name in NAMES:
        for path in sorted((root / "machines" / name).rglob("*")):
            if path.suffix.lower() in {".vdi", ".vmdk", ".vhd"}:
                stat = path.stat()
                files.append({"file": str(path.relative_to(root / "machines")),
                              "file_bytes": stat.st_size,
                              "allocated_bytes": stat.st_blocks * 512})
    if not files:
        raise RuntimeError("Aucun disque de VM trouvé.")
    return {"files": files,
            "file_bytes": sum(item["file_bytes"] for item in files),
            "allocated_bytes": sum(item["allocated_bytes"] for item in files)}


def off(config):
    for name in NAMES:
        ssh(config, name, "sudo systemctl poweroff", check=False)
        wait_off(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vm_directory", type=Path)
    args = parser.parse_args()
    root = args.vm_directory.resolve()
    docs = Path(__file__).resolve().parents[1] / "docs"
    config = root / "access/ssh-etape8-interne.conf"
    identities = {}
    configuration = {}
    for name in NAMES:
        state = info(name)
        if state["VMState"] != "running" or state["nic1"] != "intnet" or state["intnet1"] != "intnet-app":
            raise RuntimeError("Les trois VM doivent fonctionner sur intnet-app.")
        if state["nic2"] != ("nat" if name == "vm-proxy" else "none"):
            raise RuntimeError("NAT inattendu.")
        identities[name] = state["UUID"]
        configuration[name] = {key: state[key] for key in ("memory", "cpus", "nic1", "nic2", "intnet1", "paravirtprovider", "effparavirtprovider")}
    proxy = info("vm-proxy")
    if any(key.startswith("Forwarding") and "ssh-verification" in value for key, value in proxy.items()):
        raise RuntimeError("Retirer l'ancien accès SSH temporaire avant de commencer.")
    vbox("controlvm", "vm-proxy", "natpf2", "ssh-verification,tcp,127.0.0.1,2221,,22")
    try:
        for name in NAMES:
            wait_ssh(config, name)
        off(config)
        for name in NAMES:
            if "avant verification" not in vbox("snapshot", name, "list", "--machinereadable"):
                vbox("snapshot", name, "take", "avant verification", "--description", "Services installés avant matrice et mesures.")
        for name in NAMES:
            vbox("startvm", name, "--type", "headless")
        for name in NAMES:
            wait_ssh(config, name)

        matrix = []
        targets = {"proxy": ("10.10.10.10", 80), "metier": ("10.10.10.20", 8000),
                   "donnees": ("10.10.10.30", 5432)}
        proof = ["Étape 10 — matrice réelle et écoutes des services", ""]
        for source in ("hote", "vm-proxy", "vm-metier", "vm-donnees"):
            for target, (address, port) in targets.items():
                if source == "vm-" + target:
                    continue
                expected = (source, target) not in {("hote", "metier"), ("hote", "donnees"), ("vm-proxy", "donnees")}
                if source == "hote":
                    if target == "proxy":
                        address, port = "127.0.0.1", 8080
                    observed = connect(address, port)
                else:
                    code = "import json, socket, time\n" + inspect.getsource(connect)
                    code += f"\nprint(json.dumps(connect({address!r}, {port})))\n"
                    observed = json.loads(ssh(config, source, "python3 -", input=code).stdout)
                item = {"source": source, "target": target, "address": address,
                        "port": port, "expected": expected, **observed}
                matrix.append(item)
                proof.append(json.dumps(item, ensure_ascii=False))
                if observed["reachable"] != expected:
                    raise RuntimeError(f"Accès inattendu : {source} → {target}")
        for name in NAMES:
            for command in ("sudo ss -tlnp", "ip route", "systemctl is-active nginx" if name == "vm-proxy"
                            else "systemctl is-active intern" if name == "vm-metier"
                            else "systemctl is-active postgresql@16-main nftables"):
                proof.extend(["", name + " $ " + command, ssh(config, name, command).stdout.rstrip()])
        sql = "sudo bash -ec 'set -a; . /etc/intern/intern.env; set +a; export PGHOST=\"$POSTGRES_HOST\" PGPORT=\"$POSTGRES_PORT\" PGUSER=\"$POSTGRES_USER\" PGDATABASE=\"$POSTGRES_DB\" PGPASSWORD=\"$POSTGRES_PASSWORD\"; runuser -u intern -- psql -X -w -c \"SELECT 1 AS connexion_base;\"'"
        proof.extend(["", "vm-metier $ psql (environnement privé) SELECT 1", ssh(config, "vm-metier", sql).stdout.rstrip()])
        (docs / "joignabilite-etape10.json").write_text(json.dumps(matrix, indent=2, ensure_ascii=False) + "\n")
        (docs / "preuves-etape10.txt").write_text("\n".join(line.rstrip() for line in proof) + "\n")
        print("Matrice : neuf liaisons conformes, dont trois refusées.", flush=True)

        trials = []
        for index in range(1, 4):
            off(config)
            start = time.monotonic()
            for name in NAMES:
                vbox("startvm", name, "--type", "headless")
            while True:
                try:
                    body = request(URL)
                    offers = body.get("results", body) if isinstance(body, dict) else body
                    if not isinstance(offers, list) or not offers:
                        raise RuntimeError("Catalogue vide ou inattendu.")
                    break
                except (OSError, ValueError):
                    if time.monotonic() - start > 240:
                        raise RuntimeError("Catalogue indisponible après 240 secondes.")
                    time.sleep(0.5)
            startup = time.monotonic() - start
            for name in NAMES:
                wait_ssh(config, name)
            print(f"Série {index} : démarrage {startup:.3f} s ; repos 30 s.", flush=True)
            time.sleep(30)
            ram = memory(identities)
            disks = disk(root)
            latency = []
            for _ in range(10):
                begin = time.monotonic()
                request(URL)
                latency.append((time.monotonic() - begin) * 1000)
            trial = {"trial": index, "startup_s": startup, "memory": ram,
                     "rss_bytes": sum(item["rss_bytes"] for item in ram.values()),
                     "disk": disks, "latency_ms": latency,
                     "latency_median_ms": statistics.median(latency)}
            trials.append(trial)
            print(f"Série {index} enregistrée : RSS={trial['rss_bytes']} octets, latence médiane={trial['latency_median_ms']:.3f} ms.", flush=True)
        host = {"system": platform.system(), "release": platform.release(),
                "distribution": platform.freedesktop_os_release().get('PRETTY_NAME'),
                "cpu": next(line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                            if line.startswith('model name')),
                "logical_cpus": os.cpu_count(),
                "memory_bytes": int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                                         if line.startswith('MemTotal:'))) * 1024}
        result = {"finished_utc": datetime.now(timezone.utc).isoformat(),
                  "virtualbox": subprocess.check_output(["VBoxManage", "--version"], text=True).strip(),
                  "host": host, "configuration": configuration,
                  "protocol": {"trials": 3, "idle_s": 30, "requests_per_trial": 10,
                               "url": URL, "timeout_s": 5, "startup_poll_s": 0.5,
                               "memory": "Somme VmRSS des trois processus VBoxHeadless/VirtualBoxVM, hors VBoxSVC.",
                               "disk": "Fichiers VDI/VMDK/VHD des trois clones, snapshots inclus, modèle et OVA exclus.",
                               "startup": "Avant premier startvm jusqu’au premier HTTP 200 avec catalogue non vide ; démarrages séquentiels ; cache hôte conservé.",
                               "latency": "Dix GET séquentiels, client urllib sans session ni cache, lecture complète JSON ; médiane par série puis médiane des trois séries."},
                  "trials": trials,
                  "medians": {"startup_s": statistics.median(t['startup_s'] for t in trials),
                              "rss_bytes": statistics.median(t['rss_bytes'] for t in trials),
                              "disk_file_bytes": statistics.median(t['disk']['file_bytes'] for t in trials),
                              "disk_allocated_bytes": statistics.median(t['disk']['allocated_bytes'] for t in trials),
                              "latency_ms": statistics.median(t['latency_median_ms'] for t in trials)}}
        (docs / "mesures-etape10.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    finally:
        if info("vm-proxy")["VMState"] == "running":
            vbox("controlvm", "vm-proxy", "natpf2", "delete", "ssh-verification")
        else:
            vbox("modifyvm", "vm-proxy", "--natpf2", "delete", "ssh-verification")
    print("Matrice et trois séries enregistrées ; accès SSH temporaire retiré.", flush=True)


if __name__ == "__main__":
    main()
