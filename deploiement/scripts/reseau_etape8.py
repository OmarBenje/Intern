#!/usr/bin/env python3
"""Configurer les trois VM de l'étape 7 et vérifier leur réseau après redémarrage.

Usage : python3 reseau_etape8.py /repertoire/local/des/VM
Les VM doivent être éteintes, en NAT de préparation, sans redirection existante.
Les accès SSH temporaires sont retirés en fin d'exécution.
"""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import shlex
import subprocess
import time


def run(args, *, input=None, check=True, timeout=60, cwd=None):
    result = subprocess.run(args, input=input, text=True, capture_output=True, timeout=timeout, cwd=cwd)
    if check and result.returncode:
        raise RuntimeError(f"{shlex.join(args)}\n{result.stdout}\n{result.stderr}")
    return result


def vbox(*args):
    print("VBoxManage " + shlex.join(args), flush=True)
    return run(["VBoxManage", *args]).stdout


def info(name):
    return {key.strip('"'): value.strip('"') for key, value in
            (line.split("=", 1) for line in vbox("showvminfo", name, "--machinereadable").splitlines()
             if "=" in line)}


def wait_off(name):
    end = time.monotonic() + 120
    while time.monotonic() < end:
        if info(name)["VMState"] == "poweroff":
            return
        time.sleep(3)
    raise RuntimeError(f"Arrêt non confirmé : {name}")


def ssh(config, name, command, *, input=None, check=True):
    # ProxyJump reconstruit une commande shell : utiliser un nom de config sans espaces.
    return run(["ssh", "-F", config.name, name, command], input=input, check=check,
               timeout=30, cwd=config.parent)


def wait_ssh(config, name):
    end = time.monotonic() + 240
    last = ""
    while time.monotonic() < end:
        result = ssh(config, name, "true", check=False)
        if result.returncode == 0:
            return
        last = result.stderr
        time.sleep(3)
    raise RuntimeError(f"SSH indisponible : {name}\n{last}")


def ssh_config(root, machines, *, internal):
    access = root / "access"
    config = access / ("ssh-etape8-interne.conf" if internal else "ssh-etape8-preparation.conf")
    lines = []
    for machine in machines:
        name = machine["name"]
        private = internal and name != "vm-proxy"
        lines.extend([f"Host {name}",
                      f"  HostName {machine['address'] if private else '127.0.0.1'}",
                      f"  Port {22 if private else machine['preparation_port']}",
                      f"  HostKeyAlias {name}"])
        if private:
            lines.append("  ProxyJump vm-proxy")
    lines.extend(["Host *", "  User adminvm", f'  IdentityFile "{access / "id_ed25519"}"',
                  f'  UserKnownHostsFile "{access / "known_hosts"}"',
                  "  BatchMode yes", "  IdentitiesOnly yes", "  ConnectTimeout 5",
                  "  ServerAliveInterval 5", "  ServerAliveCountMax 2",
                  "  StrictHostKeyChecking yes"])
    config.write_text("\n".join(lines) + "\n")
    config.chmod(0o600)
    return config


def interface_for_mac(links, mac):
    normalized = mac.lower().replace(":", "")
    names = [link["ifname"] for link in links
             if link.get("address", "").lower().replace(":", "") == normalized]
    if len(names) != 1 or not re.fullmatch(r"[a-zA-Z0-9_-]+", names[0]):
        raise RuntimeError(f"Interface non identifiée pour {mac} : {names}")
    return names[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vm_directory", type=Path)
    parser.add_argument("--verifier", action="store_true",
                        help="Vérifier une topologie déjà configurée, puis retirer son accès SSH temporaire.")
    args = parser.parse_args()
    root = args.vm_directory.resolve()
    deployment = Path(__file__).resolve().parents[1]
    plan = json.loads((deployment / "reseau/plan.json").read_text())
    machines = plan["machines"]
    if not (root / "access/id_ed25519").is_file():
        raise RuntimeError("Clé d'administration de l'étape 7 absente.")
    if not args.verifier:
        for machine in machines:
            ipaddress.ip_interface(f"{machine['address']}/{plan['prefix']}")
            current = info(machine["name"])
            if current["VMState"] != "poweroff" or current["nic1"] != "nat" or current["nic2"] != "none":
                raise RuntimeError(f"État initial inattendu : {machine['name']} (ne pas réexécuter sur un réseau déjà configuré).")
            if any(key.startswith("Forwarding") for key in current):
                raise RuntimeError("Une redirection existe déjà ; inspecter avant modification.")
            if "avant reseau" in vbox("snapshot", machine["name"], "list", "--machinereadable"):
                raise RuntimeError("Le snapshot avant reseau existe déjà ; reprendre manuellement après inspection.")
    preparation = ssh_config(root, machines, internal=False)
    internal = ssh_config(root, machines, internal=True)
    observed = {}
    proof = ["Étape 8 — sorties réelles des VM après configuration et redémarrage", ""]
    if not args.verifier:
        for machine in machines:
            name = machine["name"]
            vbox("snapshot", name, "take", "avant reseau", "--description", "État avant configuration du réseau interne.")
            vbox("modifyvm", name, "--natpf1", f"ssh-preparation,tcp,127.0.0.1,{machine['preparation_port']},,22")
            if name == "vm-proxy":
                vbox("modifyvm", name, "--nic2", "nat", "--nictype2", "82540EM", "--cableconnected2", "on")
            vbox("startvm", name, "--type", "headless")

        for machine in machines:
            name = machine["name"]
            print(f"Relevé des interfaces et installation Netplan : {name}", flush=True)
            wait_ssh(preparation, name)
            links = json.loads(ssh(preparation, name, "ip -j link show").stdout)
            current = info(name)
            app = interface_for_mac(links, current["macaddress1"])
            nat = interface_for_mac(links, current["macaddress2"]) if name == "vm-proxy" else None
            observed[name] = {"internal_interface": app, "nat_interface": nat}
            yaml = f"network:\n  version: 2\n  renderer: networkd\n  ethernets:\n    {app}:\n      dhcp4: false\n      dhcp6: false\n      addresses: [{machine['address']}/{plan['prefix']}]\n"
            if nat:
                yaml += f"    {nat}:\n      dhcp4: true\n      dhcp6: false\n"
            (deployment / "reseau" / f"{name}.yaml").write_text(yaml)
            install = "\n".join([
                "set -eu",
                "test -f /etc/cloud/cloud-init.disabled",
                "test \"$(find /etc/netplan -maxdepth 1 -name '*.yaml' | wc -l)\" -eq 1",
                "test -f /etc/netplan/50-cloud-init.yaml",
                "command -v ping",
                "mkdir -p /var/backups/intern-etape8-netplan",
                "cp -n /etc/netplan/50-cloud-init.yaml /var/backups/intern-etape8-netplan/50-cloud-init.yaml",
                "cat > /etc/netplan/50-cloud-init.yaml <<'NETPLAN'",
            ]) + "\n" + yaml + "\n".join([
                "NETPLAN",
                "chmod 600 /etc/netplan/50-cloud-init.yaml",
                "netplan generate",
                "sync",
                "",
            ])
            ssh(preparation, name, "sudo bash -s", input=install)
            stopped = ssh(preparation, name, "sudo systemctl poweroff", check=False)
            if stopped.returncode not in (0, 255):
                raise RuntimeError(stopped.stderr)
            wait_off(name)
            vbox("modifyvm", name, "--natpf1", "delete", "ssh-preparation")
            vbox("modifyvm", name, "--nic1", "intnet", "--intnet1", plan["network"], "--cableconnected1", "on")
            if nat:
                vbox("modifyvm", name, "--natpf2", "http,tcp,127.0.0.1,8080,,80")
                vbox("modifyvm", name, "--natpf2", "ssh-verification,tcp,127.0.0.1,2221,,22")
            else:
                vbox("modifyvm", name, "--nic2", "none")
    for machine in machines:
        current = info(machine["name"])
        if current["nic1"] != "intnet" or current["intnet1"] != plan["network"]:
            raise RuntimeError("Configurer le réseau interne avant de le vérifier.")
        if current["VMState"] == "poweroff":
            vbox("startvm", machine["name"], "--type", "headless")
        elif current["VMState"] != "running":
            raise RuntimeError("État VM inattendu pour vérification.")
    for machine in machines:
        name = machine["name"]
        print(f"Vérification des adresses, routes et pings : {name}", flush=True)
        wait_ssh(internal, name)
        current = info(name)
        links = json.loads(ssh(internal, name, "ip -j link show").stdout)
        observed[name] = {
            "internal_interface": interface_for_mac(links, current["macaddress1"]),
            "nat_interface": interface_for_mac(links, current["macaddress2"]) if name == "vm-proxy" else None,
        }
        expected = (deployment / "reseau" / f"{name}.yaml").read_text()
        installed = ssh(internal, name, "sudo cat /etc/netplan/50-cloud-init.yaml").stdout
        if expected != installed:
            raise RuntimeError(f"Netplan installé différent du fichier livré : {name}")
        proof.append(f"=== {name} ===")
        for command in ("hostname", "ip -br address", "ip route", "sudo netplan get"):
            proof.extend(["$ " + command, ssh(internal, name, command).stdout.strip(), ""])
        addresses = json.loads(ssh(internal, name, "ip -j -4 address show").stdout)
        actual = {entry["local"] for link in addresses for entry in link.get("addr_info", [])}
        if machine["address"] not in actual:
            raise RuntimeError(f"Adresse statique absente sur {name}")
        routes = json.loads(ssh(internal, name, "ip -j -4 route show").stdout)
        default = any(route.get("dst") == "default" for route in routes)
        if default != (name == "vm-proxy"):
            raise RuntimeError(f"Route par défaut inattendue sur {name}")
        for peer in machines:
            if peer["name"] != name:
                command = f"ping -c 2 -W 2 {peer['address']}"
                proof.extend(["$ " + command, ssh(internal, name, command).stdout.strip(), ""])
        observed[name]["address"] = machine["address"]
        observed[name]["default_route"] = default
    # Arrêter les machines privées avant le proxy, qui sert de point d'administration.
    for name in ("vm-donnees", "vm-metier", "vm-proxy"):
        ssh(internal, name, "sudo systemctl poweroff", check=False)
        wait_off(name)
    vbox("modifyvm", "vm-proxy", "--natpf2", "delete", "ssh-verification")
    for machine in machines:
        current = info(machine["name"])
        expected_nat = "nat" if machine["name"] == "vm-proxy" else "none"
        if current["nic1"] != "intnet" or current["intnet1"] != plan["network"] or current["nic2"] != expected_nat:
            raise RuntimeError("Topologie finale inattendue.")
        forwarding = [value for key, value in current.items() if key.startswith("Forwarding")]
        if forwarding != (["http,tcp,127.0.0.1,8080,,80"] if expected_nat == "nat" else []):
            raise RuntimeError(f"Redirections finales inattendues : {forwarding}")
        proof.extend([f"=== VirtualBox : {machine['name']} ==="])
        for key in ("VMState", "nic1", "intnet1", "macaddress1", "nic2"):
            proof.append(f"{key}={current[key]}")
        proof.extend(["Redirections=" + json.dumps(forwarding), ""])
    docs = deployment / "docs"
    (docs / "preuves-etape8.txt").write_text("\n".join(line.rstrip() for line in proof) + "\n")
    (docs / "interfaces-etape8.json").write_text(json.dumps(observed, indent=2) + "\n")
    print("Réseau vérifié : six pings réussis, topologie finale contrôlée, VM éteintes.", flush=True)


if __name__ == "__main__":
    main()
