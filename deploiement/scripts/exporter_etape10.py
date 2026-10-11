#!/usr/bin/env python3
"""Arrêter proprement les VM, exporter et contrôler trois OVA sans écrasement.

Usage : python3 exporter_etape10.py /repertoire/local/des/VM
Les exports restent hors du dépôt, dans exports-etape10 du répertoire local.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import xml.etree.ElementTree as ET

from reseau_etape8 import info, ssh, vbox, wait_off, wait_ssh


NAMES = ("vm-donnees", "vm-metier", "vm-proxy")


def digest(stream, algorithm="sha256"):
    result = hashlib.new(algorithm)
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(chunk)
    return result.hexdigest()


def validate(path):
    with tarfile.open(path) as archive:
        members = {member.name: member for member in archive.getmembers()}
        manifests = [name for name in members if name.endswith(".mf")]
        descriptors = [name for name in members if name.endswith(".ovf")]
        if len(manifests) != 1 or len(descriptors) != 1:
            raise RuntimeError("Un descripteur et un manifeste sont attendus.")
        document = archive.extractfile(descriptors[0]).read()
        tree = ET.fromstring(document)
        if b"/home/" in document or b"ssh-verification" in document:
            raise RuntimeError("Chemin personnel ou accès temporaire présent dans l'OVF.")
        manifest = archive.extractfile(manifests[0]).read().decode()
        checked = []
        for line in manifest.splitlines():
            match = re.fullmatch(r"(SHA1|SHA256)\s*\((.+)\)\s*=\s*([a-fA-F0-9]+)", line)
            if not match:
                raise RuntimeError("Format du manifeste inattendu.")
            algorithm, name, expected = match.groups()
            with archive.extractfile(name) as stream:
                actual = digest(stream, algorithm.lower())
            if actual != expected.lower():
                raise RuntimeError(f"Empreinte interne incorrecte : {name}")
            checked.append(name)
        payload = {name for name in members if name.endswith((".ovf", ".vmdk"))}
        if not payload or payload != set(checked):
            raise RuntimeError("Le manifeste ne couvre pas tous les disques et l'OVF.")
        # Lire les caractéristiques conservées dans l'extension VirtualBox.
        machine = tree.find(".//{http://www.virtualbox.org/ovf/machine}Machine")
        if machine is None:
            raise RuntimeError("Configuration VirtualBox absente.")
        if machine.attrib.get('name') != path.stem:
            raise RuntimeError("Nom de machine différent du nom de l'archive.")
        adapters = [dict(element.attrib) for element in machine.findall(".//Adapter")]
        # L'extension peut placer tous ses éléments dans le même espace de noms.
        if not adapters:
            adapters = [dict(element.attrib) for element in machine.iter()
                        if element.tag.rsplit('}', 1)[-1] == 'Adapter']
        return {"members": list(members), "manifest_verified": checked,
                "adapters": adapters}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vm_directory", type=Path)
    parser.add_argument("--reprendre", action="store_true",
                        help="Contrôler les OVA déjà créés et exporter uniquement les archives absentes.")
    args = parser.parse_args()
    root = args.vm_directory.resolve()
    deployment = Path(__file__).resolve().parents[1]
    output = root / "exports-etape10"
    output.mkdir(exist_ok=True)
    if not args.reprendre and any((output / f"{name}.ova").exists() for name in NAMES):
        raise RuntimeError("Un OVA existe déjà ; choisir un autre répertoire ou examiner les exports existants.")
    config = root / "access/ssh-etape8-interne.conf"
    states = {name: info(name) for name in NAMES}
    if any(state["VMState"] not in {"running", "poweroff"} for state in states.values()):
        raise RuntimeError("Une VM n'est ni démarrée ni éteinte.")
    if states['vm-proxy']['VMState'] == 'running':
        vbox("controlvm", "vm-proxy", "natpf2", "ssh-verification,tcp,127.0.0.1,2221,,22")
        try:
            for name in NAMES:
                if states[name]['VMState'] == 'running':
                    wait_ssh(config, name)
                    ssh(config, name, "sudo systemctl poweroff", check=False)
                    wait_off(name)
        finally:
            state = info('vm-proxy')['VMState']
            if state == 'running':
                vbox("controlvm", "vm-proxy", "natpf2", "delete", "ssh-verification")
            else:
                vbox("modifyvm", "vm-proxy", "--natpf2", "delete", "ssh-verification")
    for name in NAMES:
        current = info(name)
        if current["VMState"] != "poweroff":
            raise RuntimeError("Éteindre les trois VM avant export.")
        if current['nic1'] != 'intnet' or current['intnet1'] != 'intnet-app' or current['nic2'] != ('nat' if name == 'vm-proxy' else 'none'):
            raise RuntimeError("Topologie exportée inattendue.")
        forwards = [v for k, v in current.items() if k.startswith('Forwarding')]
        if forwards != (["http,tcp,127.0.0.1,8080,,80"] if name == 'vm-proxy' else []):
            raise RuntimeError("Redirections exportées inattendues.")
    artifacts = []
    proof = ["Étape 10 — exports OVA de VM éteintes, état courant installé", ""]
    for name in NAMES:
        path = output / f"{name}.ova"
        if path.exists():
            print(f"Contrôle de l'export existant {name}...", flush=True)
            proof.append(f"Archive existante {name}.ova : contrôle sans réécriture.")
        else:
            print(f"Export de {name}...", flush=True)
            command = ["VBoxManage", "export", name, "--output", str(path), "--ovf20", "--manifest"]
            result = subprocess.run(command, text=True, capture_output=True, check=True, timeout=1800)
            text = result.stdout.replace(str(root), '/repertoire-local-des-VM').replace(str(Path.home()), '/repertoire-utilisateur')
            proof.extend([f"VBoxManage export {name} --output exports-etape10/{name}.ova --ovf20 --manifest",
                          text.strip()])
        contents = validate(path)
        with path.open('rb') as stream:
            sha256 = digest(stream)
        # Lecture réelle de l'appliance, sans créer de VM ni remplacer les originales.
        dry = subprocess.run(["VBoxManage", "import", str(path), "--dry-run"],
                             text=True, capture_output=True, check=True, timeout=180)
        text = dry.stdout + dry.stderr
        text = text.replace(str(root), '/repertoire-local-des-VM').replace(str(Path.home()), '/repertoire-utilisateur')
        proof.extend([f"VBoxManage import exports-etape10/{name}.ova --dry-run", text.strip(),
                      "Manifest interne : empreintes vérifiées.", f"SHA256={sha256}", ""])
        artifacts.append({"file": path.name, "bytes": path.stat().st_size,
                          "sha256": sha256, "dry_run": "passed", **contents})
        print(f"{path.name} : {path.stat().st_size} octets ; manifeste et lecture VirtualBox valides.", flush=True)
    (deployment / 'docs/exports-etape10.json').write_text(json.dumps(
        {"finished_utc": datetime.now(timezone.utc).isoformat(),
         "directory": "exports-etape10 (hors dépôt, dans le répertoire local des VM)",
         "artifacts": artifacts}, indent=2, ensure_ascii=False) + '\n')
    (deployment / 'docs/preuves-exports-etape10.txt').write_text('\n'.join(proof) + '\n')
    (output / 'SHA256SUMS').write_text(''.join(f"{item['sha256']}  {item['file']}\n" for item in artifacts))
    print('Trois OVA contrôlés ; VM originales éteintes.', flush=True)


if __name__ == '__main__':
    main()
