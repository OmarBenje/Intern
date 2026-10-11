#!/usr/bin/env python3
"""Vérifier les services, sources déployées et accès HTTP des trois VM.

Usage : python3 verifier_etape9.py /repertoire/local/des/VM --redemarrer
Nécessite l'accès SSH temporaire sur le proxy. Il est retiré en fin de contrôle.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.error import URLError
from urllib.request import urlopen

from reseau_etape8 import info, ssh, vbox, wait_off, wait_ssh


def hashes(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}}


def remote_hashes(config, name, folder):
    source = f"""import hashlib, json
from pathlib import Path
root = Path({folder!r})
result = {{str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted(root.rglob('*')) if p.is_file()
          and '__pycache__' not in p.parts and p.suffix not in {{'.pyc', '.pyo'}}}}
print(json.dumps(result))
"""
    return json.loads(ssh(config, name, "python3 -", input=source).stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vm_directory", type=Path)
    parser.add_argument("--redemarrer", action="store_true")
    args = parser.parse_args()
    root = args.vm_directory.resolve()
    deployment = Path(__file__).resolve().parents[1]
    project = deployment.parent
    config = root / "access/ssh-etape8-interne.conf"
    names = ("vm-donnees", "vm-metier", "vm-proxy")
    for name in names:
        wait_ssh(config, name)
    if args.redemarrer:
        for name in names:
            ssh(config, name, "sudo systemctl poweroff", check=False)
            wait_off(name)
        for name in names:
            vbox("startvm", name, "--type", "headless")
        for name in names:
            wait_ssh(config, name)

    proof = ["Étape 9 — contrôles réels sur les trois VM", "Redémarrage complet effectué=" + str(args.redemarrer), ""]
    commands = {
        "vm-donnees": [
            "psql --version", "systemctl is-active postgresql@16-main nftables",
            "systemctl is-enabled postgresql nftables", "sudo ss -tlnp",
            "sudo -u postgres psql -X -d intern -c \"SHOW listen_addresses; SHOW password_encryption; SELECT count(*) AS comptes FROM auth_user; SELECT count(*) AS offres FROM jobboard_offer; SELECT rolname, rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname='intern_user';\"",
            "sudo nft list table inet intern_db", "ip route",
        ],
        "vm-metier": [
            "python3 --version", "systemctl is-active intern", "systemctl is-enabled intern",
            "sudo ss -tlnp", "sudo stat -c '%U:%G %a' /etc/intern/intern.env",
            "/opt/intern/metier/.venv/bin/python -c 'import django, gunicorn, rest_framework; print(\"Django\", django.get_version()); print(\"Gunicorn\", gunicorn.__version__); print(\"DRF\", rest_framework.VERSION)'",
            "curl -fsS http://10.10.10.20:8000/health/ready/", "ip route",
        ],
        "vm-proxy": [
            "sudo nginx -v", "sudo nginx -t", "systemctl is-active nginx",
            "systemctl is-enabled nginx", "sudo ss -tlnp", "ip route",
            "curl -fsS -H 'Host: 127.0.0.1:8080' http://10.10.10.10/health/ready/",
        ],
    }
    for name, checks in commands.items():
        proof.append("=== " + name + " ===")
        for command in checks:
            result = ssh(config, name, command)
            proof.extend(["$ " + command, (result.stdout + result.stderr).strip(), ""])

    artifacts = {}
    for name, source, destination in [
        ("vm-metier", project / "metier/app", "/opt/intern/metier/app"),
        ("vm-proxy", project / "frontend/dist", "/var/www/intern/client"),
    ]:
        expected = hashes(source)
        actual = remote_hashes(config, name, destination)
        if expected != actual:
            raise RuntimeError(f"Contenu déployé différent des fichiers préparés : {name}")
        artifacts[name] = expected
        proof.append(f"{name} : {len(expected)} fichiers déployés identiques (SHA-256).")

    for name, source, installed in [
        ("vm-donnees", "donnees/intern.conf", "/etc/postgresql/16/main/conf.d/intern.conf"),
        ("vm-donnees", "donnees/pg_hba.conf", "/etc/postgresql/16/main/pg_hba.conf"),
        ("vm-donnees", "donnees/intern-db.nft", "/etc/nftables.d/intern-db.nft"),
        ("vm-metier", "metier/intern.service", "/etc/systemd/system/intern.service"),
        ("vm-proxy", "proxy/intern.conf", "/etc/nginx/sites-available/intern"),
    ]:
        expected = hashlib.sha256((deployment / source).read_bytes()).hexdigest()
        actual = ssh(config, name, "sudo sha256sum " + installed).stdout.split()[0]
        if actual != expected:
            raise RuntimeError(f"Configuration installée différente : {name} {source}")
        proof.append(f"Configuration conforme : {name}, {source}.")

    end = time.monotonic() + 90
    while True:
        try:
            with urlopen("http://127.0.0.1:8080/health/ready/", timeout=5) as response:
                if json.load(response) != {"status": "ok"}:
                    raise RuntimeError("Réponse readiness inattendue.")
                proof.append("Hôte → http://127.0.0.1:8080/health/ready/ : HTTP 200, status=ok.")
                break
        except URLError:
            if time.monotonic() >= end:
                raise
            time.sleep(2)
    with urlopen("http://127.0.0.1:8080/login", timeout=5) as response:
        body = response.read().decode()
        if '<div id="root"></div>' not in body:
            raise RuntimeError("Le client React n'est pas servi.")
        proof.append("Hôte → /login : HTTP 200, point de montage React présent.")

    vbox("controlvm", "vm-proxy", "natpf2", "delete", "ssh-verification")
    for name in names:
        current = info(name)
        if current["VMState"] != "running" or current["nic1"] != "intnet" or current["intnet1"] != "intnet-app":
            raise RuntimeError("Topologie finale inattendue.")
        expected_nat = "nat" if name == "vm-proxy" else "none"
        if current["nic2"] != expected_nat:
            raise RuntimeError("NAT temporaire encore présent.")
        expected_snapshot = "avant " + name.removeprefix("vm-")
        snapshots = vbox("snapshot", name, "list", "--machinereadable")
        if f'="{expected_snapshot}"' not in snapshots:
            raise RuntimeError(f"Snapshot avant déploiement absent : {name}")
        forwarding = [v for k, v in current.items() if k.startswith("Forwarding")]
        if forwarding != (["http,tcp,127.0.0.1,8080,,80"] if name == "vm-proxy" else []):
            raise RuntimeError("Redirection finale inattendue.")
        proof.extend(["", f"=== VirtualBox : {name} ===", "VMState=" + current["VMState"],
                      "nic1=" + current["nic1"], "intnet1=" + current["intnet1"],
                      "nic2=" + current["nic2"], "Redirections=" + json.dumps(forwarding),
                      "Snapshot=" + current["CurrentSnapshotName"],
                      "SnapshotUUID=" + current["CurrentSnapshotUUID"]])

    (deployment / "docs/preuves-etape9.txt").write_text("\n".join(line.rstrip() for line in proof) + "\n")
    (deployment / "docs/artefacts-etape9.json").write_text(json.dumps(artifacts, indent=2) + "\n")
    print("Services actifs, fichiers conformes, accès HTTP vérifié, NAT temporaires retirés.")


if __name__ == "__main__":
    main()
