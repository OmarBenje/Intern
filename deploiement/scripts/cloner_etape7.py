#!/usr/bin/env python3
"""Cloner un vm-modele préparé et éteint, puis vérifier les identités.

Usage : python3 cloner_etape7.py /chemin/vers/.local-vms
Aucun remplacement de VM existante. Les accès SSH temporaires sont retirés.
"""
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

root = Path(sys.argv[1]).resolve()
roles = [("vm-proxy", 1, 1024, 2221), ("vm-metier", 2, 2048, 2222),
         ("vm-donnees", 2, 2048, 2223)]


def run(*args, check=True):
    return subprocess.run(args, text=True, capture_output=True, check=check)


def vbox(*args):
    print("VBoxManage " + shlex.join(args), flush=True)
    result = run("VBoxManage", *args)
    return result.stdout


def info(name):
    values = {}
    for line in vbox("showvminfo", name, "--machinereadable").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip('"')] = value.strip('"')
    return values


def ssh(name, port, command, check=True):
    return run("ssh", "-i", str(root / "access/id_ed25519"), "-p", str(port),
               "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
               "-o", "StrictHostKeyChecking=accept-new", "-o", f"HostKeyAlias={name}",
               "-o", f'UserKnownHostsFile="{root / "access/known_hosts"}"',
               "adminvm@127.0.0.1", command, check=check)


def wait_ssh(name, port):
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        if ssh(name, port, "true", check=False).returncode == 0:
            return
        time.sleep(3)
    raise RuntimeError(f"SSH indisponible : {name}")


def wait_off(name):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if info(name)["VMState"] == "poweroff":
            return
        time.sleep(3)
    raise RuntimeError(f"Arrêt non confirmé : {name}")


if info("vm-modele")["VMState"] != "poweroff":
    raise SystemExit("Le modèle doit être préparé et éteint.")
registered = vbox("list", "vms")
report = root / "verification-etape7.json"
results = json.loads(report.read_text()) if report.exists() else []
completed = {row["name"]: row for row in results}
for name, *_ in roles:
    if f'"{name}"' in registered:
        current = info(name)
        saved = completed.get(name)
        if not saved or current.get("CurrentSnapshotUUID") != saved["snapshot_uuid"] or current["UUID"] != saved["uuid"] or current["VMState"] != "poweroff":
            raise SystemExit(f"{name} existe sans preuve de fin correspondante ; arrêt sans remplacement.")
    elif name in completed:
        raise SystemExit(f"La VM vérifiée {name} a disparu ; inspecter le rapport.")

for name, cpus, ram, port in roles:
    if name in completed:
        print(f"{name} déjà vérifiée, conservée.", flush=True)
        continue
    # Sans option Link : clone intégral ; sans KeepAllMACs : nouvelles MAC.
    vbox("clonevm", "vm-modele", "--name", name, "--basefolder",
         str(root / "machines"), "--mode", "machine", "--register")
    vbox("modifyvm", name, "--cpus", str(cpus), "--memory", str(ram),
         "--macaddress1", "auto", "--natpf1", f"ssh-install,tcp,127.0.0.1,{port},,22")
    vbox("startvm", name, "--type", "headless")
    wait_ssh(name, port)
    command = f"""sudo bash -se <<'GUEST'
test -f /var/lib/modele-prepare
test -f /etc/cloud/cloud-init.disabled
hostnamectl set-hostname {name}
printf '127.0.0.1 localhost\n127.0.1.1 {name}\n::1 localhost ip6-localhost ip6-loopback\n' > /etc/hosts
rm -f /var/lib/dbus/machine-id
truncate -s 0 /etc/machine-id
systemd-machine-id-setup
ln -s /etc/machine-id /var/lib/dbus/machine-id
rm -f /etc/ssh/ssh_host_*key /etc/ssh/ssh_host_*key.pub
ssh-keygen -A
sync
systemctl poweroff
GUEST"""
    changed = ssh(name, port, command, check=False)
    if changed.returncode not in (0, 255):
        raise RuntimeError(changed.stderr)
    wait_off(name)
    run("ssh-keygen", "-R", name, "-f", str(root / "access/known_hosts"))
    vbox("startvm", name, "--type", "headless")
    wait_ssh(name, port)
    identity = ssh(name, port, "hostname; cat /etc/machine-id; "
                   "systemctl get-default; cat /etc/hostname; "
                   "cat /var/lib/dbus/machine-id").stdout.splitlines()
    assert identity[0] == identity[3] == name, identity
    assert identity[2] == "multi-user.target", identity
    assert len(identity[1]) == 32 and identity[1] == identity[4], identity
    ssh(name, port, "sudo systemctl poweroff", check=False)
    wait_off(name)
    vbox("modifyvm", name, "--natpf1", "delete", "ssh-install")
    vbox("snapshot", name, "take", "base propre",
         "--description", "Ubuntu Server : identité distincte, avant réseau applicatif.")
    current = info(name)
    assert current["memory"] == str(ram) and current["cpus"] == str(cpus)
    results.append({"name": name, "cpus": cpus, "memory_mb": ram,
                    "machine_id": identity[1], "mac": current["macaddress1"],
                    "uuid": current["UUID"], "snapshot": "base propre",
                    "snapshot_uuid": current["CurrentSnapshotUUID"]})
    (root / "verification-etape7.json").write_text(json.dumps(results, indent=2) + "\n")

assert len({r["machine_id"] for r in results}) == 3
assert len({r["mac"] for r in results}) == 3
print(json.dumps(results, indent=2))
