#!/usr/bin/env bash
# Prepare the step-7 model and clones, preserving existing virtual machines.
# Usage: bash outils/preparer_vm.sh
# Optional: VM_WORK=/existing/workspace bash outils/preparer_vm.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export PATH="$HOME/.local/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
# An existing deployment needs no download, import, clone or restart.
VBoxManage --version
if VBoxManage showvminfo vm-proxy >/dev/null 2>&1 && \
   VBoxManage showvminfo vm-metier >/dev/null 2>&1 && \
   VBoxManage showvminfo vm-donnees >/dev/null 2>&1; then
  echo 'Les trois VM existent : conservées sans modification.'
  exit 0
fi
mkdir -p "$VM_WORK/downloads" "$VM_WORK/access" "$VM_WORK/machines"
chmod 700 "$VM_WORK/access"
if ! VBoxManage showvminfo vm-modele >/dev/null 2>&1; then

IMAGE_URL=https://cloud-images.ubuntu.com/releases/noble/release-20260926
curl -fL --retry 3 "$IMAGE_URL/SHA256SUMS" -o "$VM_WORK/downloads/SHA256SUMS"
if [ ! -f "$VM_WORK/downloads/ubuntu-24.04-server-cloudimg-amd64.ova" ]; then
  curl -fL --retry 3 "$IMAGE_URL/ubuntu-24.04-server-cloudimg-amd64.ova" \
    -o "$VM_WORK/downloads/modele.ova.part"
  mv "$VM_WORK/downloads/modele.ova.part" "$VM_WORK/downloads/ubuntu-24.04-server-cloudimg-amd64.ova"
fi
(cd "$VM_WORK/downloads" && sha256sum --ignore-missing -c SHA256SUMS)

test -f "$VM_WORK/access/id_ed25519" || \
  ssh-keygen -q -t ed25519 -N '' -C administration-vm -f "$VM_WORK/access/id_ed25519"
test -x "$VM_WORK/tools/bin/python" || python3 -m venv "$VM_WORK/tools"
"$VM_WORK/tools/bin/pip" install pycdlib==1.22.0
"$VM_WORK/tools/bin/python" deploiement/scripts/seed_modele.py \
  "$VM_WORK/access/id_ed25519.pub" "$VM_WORK/access/seed-modele.iso"
VBoxManage import "$VM_WORK/downloads/ubuntu-24.04-server-cloudimg-amd64.ova" \
  --options importtovdi --vsys 0 --vmname vm-modele \
  --basefolder "$VM_WORK/machines" --cpus 2 --memory 2048
VBoxManage modifyvm vm-modele --nic1 nat \
  --natpf1 'ssh-install,tcp,127.0.0.1,2220,,22' \
  --boot1 disk --boot2 dvd --boot3 none --boot4 none --graphicscontroller vboxvga
VBoxManage modifymedium disk \
  "$VM_WORK/machines/vm-modele/ubuntu-noble-24.04-cloudimg.vdi" --resize 20480
VBoxManage storagectl vm-modele --name Floppy --remove
VBoxManage storageattach vm-modele --storagectl IDE --port 0 --device 0 \
  --type dvddrive --medium "$VM_WORK/access/seed-modele.iso"
VBoxManage startvm vm-modele --type headless

  deadline=$((SECONDS + 600))
  until ssh -i "$VM_WORK/access/id_ed25519" -p 2220 -o BatchMode=yes \
    -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new \
    -o "UserKnownHostsFile=$VM_WORK/access/known_hosts" adminvm@127.0.0.1 true; do
    if (( SECONDS >= deadline )); then
      echo 'SSH du modèle indisponible après 600 s ; inspecter vm-modele dans VirtualBox.' >&2
      exit 1
    fi
    sleep 3
  done
  ssh -i "$VM_WORK/access/id_ed25519" -p 2220 \
    -o "UserKnownHostsFile=$VM_WORK/access/known_hosts" \
    adminvm@127.0.0.1 'sudo bash -s' < deploiement/scripts/finaliser_modele.sh
  deadline=$((SECONDS + 180))
  until VBoxManage showvminfo vm-modele --machinereadable | rg -q '^VMState="poweroff"$'; do
    if (( SECONDS >= deadline )); then
      echo 'Arrêt du modèle non confirmé après 180 s ; inspecter son état.' >&2
      exit 1
    fi
    sleep 2
  done
  VBoxManage storageattach vm-modele --storagectl IDE --port 0 --device 0 --type dvddrive --medium emptydrive
  VBoxManage modifyvm vm-modele --natpf1 delete ssh-install
else
  echo 'Modèle existant conservé ; vérifier sa préparation et son état éteint.'
fi
if ! VBoxManage showvminfo vm-proxy >/dev/null 2>&1 || \
   ! VBoxManage showvminfo vm-metier >/dev/null 2>&1 || \
   ! VBoxManage showvminfo vm-donnees >/dev/null 2>&1; then
  python3 deploiement/scripts/cloner_etape7.py "$VM_WORK"
fi
echo 'Préparation terminée. Vérifier avec : VBoxManage list vms'
