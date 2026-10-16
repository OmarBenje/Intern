#!/usr/bin/env python3
"""Installer une couche sur les VM existantes, sans restaurer de snapshot.

Depuis la racine du dépôt : python3 deploiement/scripts/deployer_etape9.py
/repertoire/local/des/VM donnees|metier|proxy
"""
import argparse
import io
import json
from pathlib import Path
import secrets
import subprocess
import tarfile

from reseau_etape8 import info, interface_for_mac, ssh, vbox, wait_off, wait_ssh


def archive(project, paths):
    buffer = io.BytesIO()

    def neutral(item):
        if any(part in {"__pycache__", ".venv", ".git", "node_modules"} for part in Path(item.name).parts):
            return None
        if item.name.endswith((".pyc", ".pyo")):
            return None
        item.uid = item.gid = 0
        item.uname = item.gname = ""
        return item

    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        for path in paths:
            bundle.add(project / path, arcname=path, filter=neutral)
    return buffer.getvalue()


def binary_ssh(config, name, command, *, input=None):
    result = subprocess.run(["ssh", "-F", config.name, name, command], cwd=config.parent,
                            input=input, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return result.stdout


def upload(config, name, folder, payload):
    ssh(config, name, f"sudo mkdir -p {folder}")
    binary_ssh(config, name, f"sudo tar -xzf - -C {folder}", input=payload)


def execute(config, name, source):
    # Les installations peuvent durer plusieurs minutes. La sortie ne contient
    # pas les secrets et sera conservée dans le journal local de l'opérateur.
    process = subprocess.run(["ssh", "-F", config.name, name, "sudo bash -s"],
                             cwd=config.parent, input=source.read_text(), text=True)
    if process.returncode:
        raise RuntimeError(f"Installation interrompue sur {name} ; inspecter le journal avant de reprendre.")


def prepare(config, name, snapshot, *, temporary_nat):
    current = info(name)
    snapshots = vbox("snapshot", name, "list", "--machinereadable")
    exists = f'="{snapshot}"' in snapshots
    need_adapter = temporary_nat and current["nic2"] != "nat"
    if not exists or need_adapter:
        if current["VMState"] == "running":
            ssh(config, name, "sudo systemctl poweroff", check=False)
            wait_off(name)
        if not exists:
            vbox("snapshot", name, "take", snapshot, "--description", "État avant déploiement de la couche.")
        if temporary_nat:
            vbox("modifyvm", name, "--nic2", "nat", "--nictype2", "82540EM", "--cableconnected2", "on")
    if info(name)["VMState"] == "poweroff":
        vbox("startvm", name, "--type", "headless")
    wait_ssh(config, name)
    if temporary_nat:
        current = info(name)
        links = json.loads(ssh(config, name, "ip -j link show").stdout)
        nic = interface_for_mac(links, current["macaddress2"])
        yaml = f"network:\n  version: 2\n  ethernets:\n    {nic}:\n      dhcp4: true\n      dhcp6: false\n"
        script = "set -eu\ncat > /etc/netplan/90-installation.yaml <<'YAML'\n" + yaml + "YAML\nchmod 600 /etc/netplan/90-installation.yaml\nnetplan generate\nnetplan apply\n"
        ssh(config, name, "sudo bash -s", input=script, timeout=120)


def close_nat(config, name):
    ssh(config, name, "sudo rm -f /etc/netplan/90-installation.yaml; sudo netplan apply", timeout=120)
    ssh(config, name, "sudo systemctl poweroff", check=False)
    wait_off(name)
    vbox("modifyvm", name, "--nic2", "none")
    vbox("startvm", name, "--type", "headless")
    wait_ssh(config, name)
    routes = json.loads(ssh(config, name, "ip -j -4 route show").stdout)
    if any(row.get("dst") == "default" for row in routes):
        raise RuntimeError(f"NAT temporaire non retiré sur {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vm_directory", type=Path)
    parser.add_argument("phase", choices=("donnees", "metier", "proxy"))
    args = parser.parse_args()
    root = args.vm_directory.resolve()
    deployment = Path(__file__).resolve().parents[1]
    project = deployment.parent
    config = root / "access/ssh-etape8-interne.conf"
    secret_path = root / "access/secrets-etape9.json"
    if not secret_path.exists():
        secret_path.write_text(json.dumps({"POSTGRES_PASSWORD": secrets.token_hex(32),
                                          "DJANGO_SECRET_KEY": secrets.token_urlsafe(64)}) + "\n")
        secret_path.chmod(0o600)
    private = json.loads(secret_path.read_text())
    name = "vm-" + args.phase
    prepare(config, name, "avant " + args.phase, temporary_nat=args.phase != "proxy")

    if args.phase == "donnees":
        payload = archive(project, ["donnees/schema.sql", "donnees/data.sql", "deploiement/donnees"])
        upload(config, name, "/var/tmp/intern-etape9", payload)
        ssh(config, name, "sudo install -d -m 0750 /etc/intern; sudo sh -c 'umask 077; cat > /etc/intern/database-password'",
            input=private["POSTGRES_PASSWORD"] + "\n")
        execute(config, name, deployment / "scripts/installer_donnees.sh")
        close_nat(config, name)
        print(ssh(config, name, "sudo systemctl is-active postgresql@16-main; sudo ss -tlnp | grep 5432").stdout)
    elif args.phase == "metier":
        payload = archive(project, ["metier/app", "metier/pyproject.toml", "metier/uv.lock",
                                    "donnees/verifier.py", "donnees/jeu_fictif.py", "donnees/cv_fictif.pdf", "deploiement/metier"])
        upload(config, name, "/opt/intern", payload)
        env = (deployment / "metier/intern.env.example").read_text()
        for key, value in private.items():
            env = env.replace("@" + key + "@", value)
        ssh(config, name, "sudo install -d -m 0750 /etc/intern; sudo sh -c 'umask 077; cat > /etc/intern/intern.env'", input=env)
        execute(config, name, deployment / "scripts/installer_metier.sh")
        close_nat(config, name)
        print(ssh(config, name, "systemctl is-active intern; curl -fsS http://10.10.10.20:8000/health/ready/").stdout)
    else:
        upload(config, name, "/var/tmp/intern-etape9", archive(project, ["deploiement/proxy"]))
        # Le client reste dans son sous-répertoire, séparé des statiques Django.
        ssh(config, name, "sudo mkdir -p /var/www/intern/client")
        upload(config, name, "/var/www/intern/client", archive(project / "frontend/dist", ["."]))
        statics = binary_ssh(config, "vm-metier", "sudo tar -czf - -C /opt/intern/staticfiles .")
        upload(config, name, "/var/www/intern/static", statics)
        execute(config, name, deployment / "scripts/installer_proxy.sh")
        print(ssh(config, name, "curl -fsS -H 'Host: 127.0.0.1:8080' http://10.10.10.10/health/ready/").stdout)


if __name__ == "__main__":
    main()
