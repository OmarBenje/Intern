#!/usr/bin/env python3
"""Créer un CD NoCloud pour le modèle Ubuntu (dépendance : pycdlib)."""
import argparse
import io
import json
from pathlib import Path

import pycdlib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("public_key", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
key = args.public_key.read_text().strip()
if not key.startswith("ssh-ed25519 ") or "\n" in key:
    parser.error("Fournir une clé publique Ed25519 unique.")

config = """#cloud-config
hostname: vm-modele
manage_etc_hosts: true
timezone: Europe/Paris
users:
  - name: adminvm
    gecos: Administration VM
    groups: [adm, sudo]
    shell: /bin/bash
    sudo: ['ALL=(ALL) NOPASSWD:ALL']
    lock_passwd: true
    ssh_authorized_keys:
      - KEY
ssh_pwauth: false
disable_root: true
package_update: true
package_upgrade: true
packages: [openssh-server, ca-certificates, curl, python3, nftables]
runcmd:
  - [systemctl, set-default, multi-user.target]
  - [touch, /var/lib/modele-prepare]
""".replace("KEY", json.dumps(key))
iso = pycdlib.PyCdlib()
iso.new(interchange_level=3, joliet=3, rock_ridge="1.09", vol_ident="cidata")
for name, content in {
    "user-data": config,
    "meta-data": "instance-id: intern-modele-01\nlocal-hostname: vm-modele\n",
}.items():
    data = content.encode()
    iso.add_fp(io.BytesIO(data), len(data), iso_path="/" + name.upper().replace("-", "_") + ";1",
               rr_name=name, joliet_path="/" + name)
iso.write(str(args.output))
iso.close()
