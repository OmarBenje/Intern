# Préparation des machines virtuelles

Suite : [étape 8 — réseau interne, adressage et connectivité](../reseau/README.md).
Déploiement des services : [étape 9 — données, métier et proxy](../DEPLOIEMENT.md).

## Étape 7 — Objectif et prérequis

Préparer un modèle Ubuntu Server 24.04 LTS sans interface graphique et sans
données applicatives, puis trois clones intégraux avec des identités distinctes.
Le modèle est créé depuis l'image officielle Canonical lorsqu'aucune installation
serveur préalable n'est disponible. Il reste conservé, éteint, en plus des clones.

L'application comporte trois couches séparées : PostgreSQL, Django et React.
Les paramètres de connexion sont externalisés dans `metier/.env.example` et
`frontend/.env.example`. La recette locale est décrite dans `../tests/README.md` ;
elle ne démontre pas encore une installation sur des VM vierges.

Prévoir VirtualBox, `curl`, OpenSSH, Python 3 et un outil de création d'ISO.
La procédure utilise `pycdlib==1.22.0` dans un environnement Python isolé.
Les trois clones consomment ensemble 5 Gio de RAM et disposent chacun d'un
disque dynamique de 20 Gio. Prévoir également l'image téléchargée, le modèle,
les snapshots et l'espace nécessaire à leur croissance.

| Machine | vCPU | RAM | Disque logique |
| --- | ---: | ---: | ---: |
| vm-modele | 2 | 2 Gio | 20 Gio |
| vm-proxy | 1 | 1 Gio | 20 Gio |
| vm-metier | 2 | 2 Gio | 20 Gio |
| vm-donnees | 2 | 2 Gio | 20 Gio |

## Créer le modèle en ligne de commande

Exécuter depuis la racine du dépôt. Choisir un répertoire de stockage **hors du
dépôt** pour les images, disques, journaux et clés privées. La variable ci-dessous
est un exemple ; conserver sa valeur dans le terminal pour les commandes suivantes.
Ne pas exécuter VirtualBox avec `sudo`.

```bash
export VM_WORK="$HOME/VMs-intern"
mkdir -p "$VM_WORK/downloads" "$VM_WORK/access" "$VM_WORK/machines"
chmod 700 "$VM_WORK/access"
VBoxManage --version
VBoxManage list vms
```

Les noms `vm-modele`, `vm-proxy`, `vm-metier` et `vm-donnees` doivent être libres.
Ne pas remplacer une machine existante. Télécharger la version datée de l'image
pour pouvoir refaire la préparation avec le même point de départ :

```bash
IMAGE_URL=https://cloud-images.ubuntu.com/releases/noble/release-20260926
curl -fL --retry 3 "$IMAGE_URL/SHA256SUMS" -o "$VM_WORK/downloads/SHA256SUMS"
curl -fL --retry 3 "$IMAGE_URL/ubuntu-24.04-server-cloudimg-amd64.ova" \
  -o "$VM_WORK/downloads/ubuntu-24.04-server-cloudimg-amd64.ova"
(cd "$VM_WORK/downloads" && sha256sum --ignore-missing -c SHA256SUMS)
```

Continuer seulement si la somme est correcte. Le manifeste est récupéré par
HTTPS sur le même serveur officiel ; cette procédure ne vérifie pas sa signature GPG.
Les mises à jour installées ensuite dépendent de la date d'exécution.

Créer une clé d'administration dédiée, sans écraser une clé existante :

```bash
test -f "$VM_WORK/access/id_ed25519" || \
  ssh-keygen -q -t ed25519 -N '' -C administration-vm -f "$VM_WORK/access/id_ed25519"
python3 -m venv "$VM_WORK/tools"
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
```

Le compte invité est `adminvm`, accessible par cette clé SSH, avec `sudo` sans
mot de passe. L'authentification SSH par mot de passe et le compte root distant
sont désactivés. Protéger la clé privée : elle donne l'administration des VM.
Attendre que SSH soit disponible, puis finaliser le modèle :

```bash
ssh -i "$VM_WORK/access/id_ed25519" -p 2220 \
  -o StrictHostKeyChecking=accept-new \
  -o "UserKnownHostsFile=\"$VM_WORK/access/known_hosts\"" \
  adminvm@127.0.0.1 'sudo bash -s' < deploiement/scripts/finaliser_modele.sh
```

Ce script attend la fin de `cloud-init`, retire l'association DHCP à la MAC du
modèle, désactive les réinitialisations cloud-init et éteint le système.
Confirmer `VMState="poweroff"` avec `VBoxManage showvminfo vm-modele --machinereadable`.
Retirer le CD et redémarrer pour vérifier le noyau mis à jour :

```bash
VBoxManage storageattach vm-modele --storagectl IDE --port 0 --device 0 \
  --type dvddrive --medium emptydrive
VBoxManage startvm vm-modele --type headless
ssh -i "$VM_WORK/access/id_ed25519" -p 2220 \
  -o "UserKnownHostsFile=\"$VM_WORK/access/known_hosts\"" adminvm@127.0.0.1 \
  'hostname; uname -r; systemctl get-default; systemctl --failed --no-pager; sudo apt-get -s upgrade'
```

Attendre SSH au besoin. Vérifier le nom `vm-modele`, la cible `multi-user.target`,
l'absence de service en échec et de mise à jour immédiatement applicable avant
d'arrêter. Consigner séparément les paquets différés par le déploiement progressif
d'Ubuntu, sans forcer ce mécanisme :

```bash
ssh -i "$VM_WORK/access/id_ed25519" -p 2220 \
  -o "UserKnownHostsFile=\"$VM_WORK/access/known_hosts\"" adminvm@127.0.0.1 'sudo systemctl poweroff'
```

Confirmer l'arrêt, puis retirer la redirection temporaire du modèle :

```bash
VBoxManage modifyvm vm-modele --natpf1 delete ssh-install
```

## Cloner et vérifier

```bash
python3 deploiement/scripts/cloner_etape7.py "$VM_WORK"
```

Le script conserve les clones déjà vérifiés lorsque leur UUID, leur snapshot
et leur état éteint correspondent au rapport. Il refuse les autres noms déjà
enregistrés. En cas d'interruption, inspecter
les VM créées et reprendre les commandes nécessaires ; ne pas les supprimer
automatiquement. Il réalise pour chaque rôle :

1. Un clone intégral (`clonevm --mode machine`, sans option `Link`) et de nouvelles MAC.
2. Le dimensionnement et un accès SSH local temporaire sur 2221, 2222 ou 2223.
3. La modification de `/etc/hostname` et `/etc/hosts`, la régénération de
   `/etc/machine-id`, du lien D-Bus et des clés hôtes SSH.
4. Un redémarrage et la vérification du nom, de l'identifiant et du mode serveur.
5. L'arrêt propre, le retrait de la redirection SSH et le snapshot `base propre`.

Il enregistre les identités vérifiées dans `$VM_WORK/verification-etape7.json`.
Les clés hôtes SSH sont distinctes ; la clé d'administration reste commune.

```bash
VBoxManage list vms
for vm in vm-proxy vm-metier vm-donnees; do
  VBoxManage showvminfo "$vm" --machinereadable
  VBoxManage snapshot "$vm" list --machinereadable
done
```

Conserver les résultats pertinents sans chemins personnels dans le
[rapport de vérification](../docs/etape7.md). Une capture de la liste VirtualBox
peut compléter ces preuves CLI pour la remise.

## Ouvrir une session d'administration après préparation

À ce stade, les machines sont éteintes et aucune redirection SSH n'est conservée.
Pour ouvrir temporairement une session sur le proxy :

```bash
VBoxManage modifyvm vm-proxy --natpf1 'ssh-install,tcp,127.0.0.1,2221,,22'
VBoxManage startvm vm-proxy --type headless
ssh -i "$VM_WORK/access/id_ed25519" -p 2221 \
  -o HostKeyAlias=vm-proxy -o StrictHostKeyChecking=accept-new \
  -o "UserKnownHostsFile=\"$VM_WORK/access/known_hosts\"" adminvm@127.0.0.1
# Dans la VM, en fin de session :
sudo systemctl poweroff
# Sur l'hôte, une fois la VM éteinte :
VBoxManage modifyvm vm-proxy --natpf1 delete ssh-install
```

Le compte n'a pas de mot de passe de console configuré : utiliser la clé SSH.
Ce mode d'accès temporaire concerne la préparation ; il faudra l'adapter à
l'isolation réseau de l'étape suivante.

## Limite de cette étape

Les machines gardent un adaptateur NAT de préparation sans redirection à la fin
de cette étape. Le réseau applicatif n'est pas encore construit. À l'étape 8,
seul le proxy conservera un NAT, et les trois machines utiliseront le réseau
interne pour les échanges applicatifs. Aucun service Intern n'est installé ici.

Source technique : [Canonical — démarrer une OVA avec VirtualBox](https://ubuntu.com/docs/public-images/public-images-how-to/run-an-ova-using-virtualbox/).
