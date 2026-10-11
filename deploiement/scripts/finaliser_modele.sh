#!/usr/bin/env bash
# Dans vm-modele, après cloud-init ; exécuter en root via SSH.
set -euo pipefail
cloud-init status --wait
test -f /var/lib/modele-prepare
# La configuration initiale contient la MAC de l'image : ne pas la cloner.
cat > /etc/netplan/50-cloud-init.yaml <<'NETPLAN'
network:
  version: 2
  ethernets:
    enp0s3:
      dhcp4: true
NETPLAN
chmod 600 /etc/netplan/50-cloud-init.yaml
netplan generate
# L'initialisation ne doit pas rétablir le nom ou les clés du modèle.
touch /etc/cloud/cloud-init.disabled
systemctl set-default multi-user.target
apt-get clean
sync
systemctl poweroff
