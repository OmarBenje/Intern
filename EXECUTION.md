# Exécution — les 18 étapes

Ce guide se lance depuis la racine du dépôt **Intern**, dans un terminal Bash.
Chaque étape répète ses préparations : ne pas supposer qu'un terminal précédent,
une base, une API ou un client est encore disponible. Les étapes se réalisent
dans l'ordre ; si un livrable prerequisite manque, sa commande de préparation
est indiquée. Les fichiers livrés se consultent aussi sans relancer les mesures.

## Installation des outils sur une machine neuve

Le dépôt doit être présent : ouvrir un terminal dans son dossier `Intern`.
Vérifier son emplacement avant toute commande :

```bash
pwd
test -f LIVRABLES.md && test -f metier/uv.lock && test -f frontend/package-lock.json
```

Installer les outils absents. Choisir le bloc correspondant au système hôte.
Ces installations demandent les droits administrateur ; elles ne sont pas
exécutées automatiquement par les lanceurs du projet.

Ubuntu 24.04 :

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip curl git openssh-client \
  postgresql-client-16 docker.io docker-compose-v2 xz-utils unzip \
  poppler-utils virtualbox default-jre ripgrep
```

Fedora, avec les dépôts nécessaires activés :

```bash
sudo dnf install -y python3 python3-pip curl git openssh-clients \
  postgresql docker-cli moby-engine docker-compose xz unzip poppler-utils \
  java-21-openjdk VirtualBox ripgrep
```

VirtualBox nécessite aussi ses modules noyau fonctionnels. Vérifier
`VBoxManage --version` avant les étapes VM. Si un paquet n'existe pas dans les
dépôts du poste, installer cet outil pour ce système avant de poursuivre.
Le client `docker` doit joindre **Docker Engine**, pas l'émulation Podman.

Installer `uv` seulement s'il manque et Node 22 si sa version est incompatible :

```bash
if ! command -v uv >/dev/null; then
  python3 -m venv "$HOME/.local/share/intern-uv"
  "$HOME/.local/share/intern-uv/bin/pip" install uv==0.11.29
  mkdir -p "$HOME/.local/bin"
  ln -s "$HOME/.local/share/intern-uv/bin/uv" "$HOME/.local/bin/uv"
fi
export PATH="$HOME/.local/bin:$PATH"
if ! node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit((a===20&&b>=19)||(a===22&&b>=12)||a>22?0:1)' 2>/dev/null; then
  mkdir -p "$HOME/.local/share/intern-node"
  cd "$HOME/.local/share/intern-node"
  curl -fLO https://nodejs.org/dist/v22.17.0/node-v22.17.0-linux-x64.tar.xz
  curl -fLO https://nodejs.org/dist/v22.17.0/SHASUMS256.txt
  sha256sum --ignore-missing -c SHASUMS256.txt
  tar -xf node-v22.17.0-linux-x64.tar.xz
  cd -
  export PATH="$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
fi
python3 --version
uv --version
node --version
npm --version
psql --version
```

L'archive Node ci-dessus concerne Linux x86_64. Le client PostgreSQL doit
comprendre les commandes `\restrict` du SQL exporté : utiliser une version
16 à jour. Conserver le PATH Node dans chaque nouveau terminal, ou dans sa
configuration de shell. Les dépendances Python du projet sont installées par
`uv sync --frozen`, avec une version Python compatible avec `metier/uv.lock`.

## Règle de démarrage conditionnel

Les scripts ci-dessous ne font pas de `restart`. Un service disponible est
conservé ; un service en cours de démarrage est attendu ; un service arrêté
est démarré. Si un autre programme occupe le port ou si les identifiants sont
incorrects, le lanceur s'arrête avec un diagnostic et garde les données.

Les étapes 3–6 utilisent [outils/demarrer_local.py](outils/demarrer_local.py).
Il exécute `uv sync --project metier --frozen`, vérifie la connexion SQL,
lance `docker compose up -d --no-recreate db` seulement si PostgreSQL manque,
attend une connexion SQL, crée `intern_execution` seulement si elle manque,
et importe `schema.sql` puis `data.sql` seulement si cette base n'a aucune table.
Il copie alors les CV fictifs dans `.execution/media/`. Une base déjà peuplée
est conservée. Il lance Django seulement si son API ne répond pas, puis Vite
seulement si son client et son proxy API ne répondent pas. Les processus restent
en arrière-plan, avec journaux et PID dans `.execution/` (ignoré par Git).

Les valeurs par défaut sont locales et fictives : PostgreSQL `127.0.0.1:5433`,
utilisateur `intern_user`, mot de passe `1234`, base dédiée `intern_execution`.
Pour une installation existante différente, créer `.execution/local.env` avant
le lancement, avec une ligne `CLE=valeur` par paramètre `POSTGRES_*` et
`PRIVATE_STORAGE_ROOT`. Ne pas y mettre de guillemets ni `export`. Ce fichier
n'est jamais écrasé. Le lanceur ne charge pas implicitement `metier/.env`.
Une API existante doit utiliser cette même base ; les captures vérifient les
comptes et les ressources via l’API réelle. Les étapes 3 et 6 réservent
respectivement `intern_donnees_execution` et `intern_recette_execution`.
Les paramètres `--database`, `--api-port` et `--frontend-port` permettent
d’isoler une autre démonstration sans arrêter les services existants.

Pour Docker natif installé ailleurs, définir `DOCKER_BIN` vers son exécutable,
et si nécessaire `DOCKER_HOST` / `DOCKER_CONFIG`, dans chaque terminal.
Ne pas changer le répertoire des volumes d'un moteur déjà installé.
Une configuration explicite du moteur peut être conservée dans
`.execution/moteur.env` (ignoré par Git), sous forme de lignes `export CLE=valeur`.
Les blocs de chaque étape la chargent si elle existe. Pour un moteur rootless
manuel, y définir `DOCKER_BIN`, `DOCKER_HOST`, `DOCKER_CONFIG`,
`DOCKER_ENGINE_BIN`, `DOCKER_ENGINE_RUNTIME` et `DOCKER_ENGINE_DATA` selon
son installation existante. Le répertoire des données doit déjà exister :
un lancement ne crée pas un autre stockage à la place du premier.

Les comptes du jeu d'essai utilisent le mot de passe **`Intern-Demo-2026!`** :
`alice@example.test` (candidat), `recruteur_a@example.test` (recruteur),
`recruteur_non_verifie@example.test` (vérification entreprise),
`vide@example.test` (liste vide). L'administration utilise le login `admin`.

## Étape 1 — Analyse

Aucun serveur nécessaire pour lire le livrable. Depuis Intern :

```bash
test -f LIVRABLES.md
xdg-open analyse/cas_d_usage.pdf
```

Pour générer le PDF si nécessaire, installer les outils Python du bloc initial :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ ! -x .execution/docs/bin/python ]; then python3 -m venv .execution/docs; fi
.execution/docs/bin/pip install -r analyse/requirements-docs.txt
.execution/docs/bin/python analyse/generer_pdf.py
pdfinfo analyse/cas_d_usage.pdf
```

## Étape 2 — Prototype Figma

Aucune base ni API à lancer. Une connexion Internet et un accès lecture au
prototype sont nécessaires. Depuis Intern :

```bash
test -f LIVRABLES.md
cat maquette/figma_link.txt
xdg-open maquette/ecran_zero.jpg
python3 - <<'PY'
from pathlib import Path
import re, subprocess
text = Path("maquette/figma_link.txt").read_text()
url = re.search(r"https://www\.figma\.com/proto/[^\s]+", text)
if not url: raise SystemExit("Lien prototype absent")
subprocess.run(["xdg-open", url.group()], check=True)
PY
```

Parcourir les trois acteurs dans Figma. La présence du lien ne prouve pas
que les droits lecture ni l’approbation pédagogique sont acquis.

## Étape 3 — Couche données

Prérequis : installer Python, uv, PostgreSQL client et Docker Engine selon le
bloc initial. Aucun métier ni client React nécessaire. Depuis Intern :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -f .execution/moteur.env ]; then
  set -a
  source .execution/moteur.env
  set +a
fi
export DOCKER_BIN="${DOCKER_BIN:-docker}"
if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  if [ -n "${DOCKER_ENGINE_RUNTIME:-}" ]; then
    test -d "$DOCKER_ENGINE_RUNTIME"
    test -d "$DOCKER_ENGINE_DATA"
    test -x "$DOCKER_ENGINE_BIN/dockerd-rootless.sh"
    mkdir -p .execution
    PATH="$DOCKER_ENGINE_BIN:$PATH" XDG_RUNTIME_DIR="$DOCKER_ENGINE_RUNTIME" \
      nohup "$DOCKER_ENGINE_BIN/dockerd-rootless.sh" \
      --host="$DOCKER_HOST" --data-root="$DOCKER_ENGINE_DATA" \
      --exec-root="$DOCKER_ENGINE_RUNTIME/exec" --storage-driver=fuse-overlayfs \
      --pidfile="$DOCKER_ENGINE_RUNTIME/docker.pid" \
      > .execution/moteur.log 2>&1 < /dev/null &
  elif systemctl --user cat docker.service >/dev/null 2>&1; then
    systemctl --user start docker.service
  else
    sudo systemctl start docker.service
  fi
fi
for tentative in $(seq 1 60); do
  if "$DOCKER_BIN" info >/dev/null 2>&1; then break; fi
  sleep 1
done
"$DOCKER_BIN" info --format '{{.ServerVersion}}'
"$DOCKER_BIN" compose version
python3 outils/demarrer_local.py donnees --database intern_donnees_execution
```

La base `intern_donnees_execution` est réservée à cette étape : les inscriptions
et essais des étapes 5–6 ne modifient pas ses effectifs attendus. Le lanceur
affiche les contrôles SQL et les 13 consultations. Pour ouvrir
la base par défaut dans ce même terminal :

```bash
PGHOST=127.0.0.1 PGPORT=5433 PGUSER=intern_user \
PGPASSWORD=1234 PGDATABASE=intern_donnees_execution psql -X
```

Dans `psql` : `\dt`, puis `SELECT title FROM jobboard_offer;`, puis `\q`.
Si `.execution/local.env` contient une configuration différente, utiliser ses valeurs.

## Étape 4 — Couche métier

Prérequis : installer Python, uv, PostgreSQL client et Docker Engine selon le
bloc initial. Même sans service lancé auparavant, depuis Intern :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -f .execution/moteur.env ]; then
  set -a
  source .execution/moteur.env
  set +a
fi
export DOCKER_BIN="${DOCKER_BIN:-docker}"
if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  if [ -n "${DOCKER_ENGINE_RUNTIME:-}" ]; then
    test -d "$DOCKER_ENGINE_RUNTIME"
    test -d "$DOCKER_ENGINE_DATA"
    test -x "$DOCKER_ENGINE_BIN/dockerd-rootless.sh"
    mkdir -p .execution
    PATH="$DOCKER_ENGINE_BIN:$PATH" XDG_RUNTIME_DIR="$DOCKER_ENGINE_RUNTIME" \
      nohup "$DOCKER_ENGINE_BIN/dockerd-rootless.sh" \
      --host="$DOCKER_HOST" --data-root="$DOCKER_ENGINE_DATA" \
      --exec-root="$DOCKER_ENGINE_RUNTIME/exec" --storage-driver=fuse-overlayfs \
      --pidfile="$DOCKER_ENGINE_RUNTIME/docker.pid" \
      > .execution/moteur.log 2>&1 < /dev/null &
  elif systemctl --user cat docker.service >/dev/null 2>&1; then
    systemctl --user start docker.service
  else
    sudo systemctl start docker.service
  fi
fi
for tentative in $(seq 1 60); do
  if "$DOCKER_BIN" info >/dev/null 2>&1; then break; fi
  sleep 1
done
"$DOCKER_BIN" info --format '{{.ServerVersion}}'
"$DOCKER_BIN" compose version
python3 outils/demarrer_local.py metier
```

```bash
curl --fail http://127.0.0.1:8000/health/ready/
curl --fail http://127.0.0.1:8000/api/v1/auth/csrf/
xdg-open http://127.0.0.1:8000/admin/
```

Le fichier `metier/api.http` contient les requêtes HTTP commentées.
API : `http://127.0.0.1:8000/api/v1/`. Administration : login `admin`,
mot de passe du jeu d’essai. React n’est pas nécessaire à cette étape.

## Étape 5 — Couche présentation

Prérequis : installer Python, uv, PostgreSQL client, Docker Engine, Node et npm
selon le bloc initial. Depuis Intern, le bloc complet démarre **base, métier
et présentation**, sans dépendre d’un terminal de l’étape 4 :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -f .execution/moteur.env ]; then
  set -a
  source .execution/moteur.env
  set +a
fi
export DOCKER_BIN="${DOCKER_BIN:-docker}"
if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  if [ -n "${DOCKER_ENGINE_RUNTIME:-}" ]; then
    test -d "$DOCKER_ENGINE_RUNTIME"
    test -d "$DOCKER_ENGINE_DATA"
    test -x "$DOCKER_ENGINE_BIN/dockerd-rootless.sh"
    mkdir -p .execution
    PATH="$DOCKER_ENGINE_BIN:$PATH" XDG_RUNTIME_DIR="$DOCKER_ENGINE_RUNTIME" \
      nohup "$DOCKER_ENGINE_BIN/dockerd-rootless.sh" \
      --host="$DOCKER_HOST" --data-root="$DOCKER_ENGINE_DATA" \
      --exec-root="$DOCKER_ENGINE_RUNTIME/exec" --storage-driver=fuse-overlayfs \
      --pidfile="$DOCKER_ENGINE_RUNTIME/docker.pid" \
      > .execution/moteur.log 2>&1 < /dev/null &
  elif systemctl --user cat docker.service >/dev/null 2>&1; then
    systemctl --user start docker.service
  else
    sudo systemctl start docker.service
  fi
fi
for tentative in $(seq 1 60); do
  if "$DOCKER_BIN" info >/dev/null 2>&1; then break; fi
  sleep 1
done
"$DOCKER_BIN" info --format '{{.ServerVersion}}'
"$DOCKER_BIN" compose version
python3 outils/demarrer_local.py presentation
```

```bash
curl --fail http://127.0.0.1:8000/health/ready/
curl --fail http://127.0.0.1:5173/api/v1/auth/csrf/
xdg-open http://127.0.0.1:5173/login
```

Connexion candidat : `alice@example.test` ; recruteur :
`recruteur_a@example.test` ; mot de passe `Intern-Demo-2026!`.
L’administration reste sur `http://127.0.0.1:8000/admin/`.

Pour prendre les captures de tous les écrans principaux sur ces services réels
(installation des bibliothèques système du navigateur si elles manquent) :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
cd frontend
npx playwright install --with-deps chromium
cd ..
node frontend/scripts/capturer_ecrans.mjs
```

Si Chrome est déjà installé, utiliser à la place
`CAPTURES_BROWSER=chrome node frontend/scripts/capturer_ecrans.mjs`, sans
installer Chromium une seconde fois.

Index des écrans : [frontend/captures/README.md](frontend/captures/README.md).
Après une première série complète, `--refresh` reprend seulement les écrans
connectés et conserve les captures d’inscription, sans créer de nouveaux comptes.
Le script inscrit des comptes fictifs de capture en attente ; il ne publie
aucune offre et n’envoie aucune candidature externe. Les captures précédentes
avec API contrôlée restent identifiées séparément.

## Étape 6 — Intégration et tests

Prérequis : installer Python, uv, PostgreSQL client, Docker Engine, Node et npm
selon le bloc initial. Une recette écrit dans sa base : utiliser une **base
dédiée à la recette**. Le bloc prépare les trois couches, même si rien ne tourne :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -f .execution/moteur.env ]; then
  set -a
  source .execution/moteur.env
  set +a
fi
export DOCKER_BIN="${DOCKER_BIN:-docker}"
if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  if [ -n "${DOCKER_ENGINE_RUNTIME:-}" ]; then
    test -d "$DOCKER_ENGINE_RUNTIME"
    test -d "$DOCKER_ENGINE_DATA"
    test -x "$DOCKER_ENGINE_BIN/dockerd-rootless.sh"
    mkdir -p .execution
    PATH="$DOCKER_ENGINE_BIN:$PATH" XDG_RUNTIME_DIR="$DOCKER_ENGINE_RUNTIME" \
      nohup "$DOCKER_ENGINE_BIN/dockerd-rootless.sh" \
      --host="$DOCKER_HOST" --data-root="$DOCKER_ENGINE_DATA" \
      --exec-root="$DOCKER_ENGINE_RUNTIME/exec" --storage-driver=fuse-overlayfs \
      --pidfile="$DOCKER_ENGINE_RUNTIME/docker.pid" \
      > .execution/moteur.log 2>&1 < /dev/null &
  elif systemctl --user cat docker.service >/dev/null 2>&1; then
    systemctl --user start docker.service
  else
    sudo systemctl start docker.service
  fi
fi
for tentative in $(seq 1 60); do
  if "$DOCKER_BIN" info >/dev/null 2>&1; then break; fi
  sleep 1
done
"$DOCKER_BIN" info --format '{{.ServerVersion}}'
"$DOCKER_BIN" compose version
python3 outils/demarrer_local.py presentation --database intern_recette_execution \
  --api-port 8001 --frontend-port 5175
```

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
cd frontend
npx playwright install chrome
cd ..
RECETTE_URL=http://127.0.0.1:5175 RECETTE_ADMIN_URL=http://127.0.0.1:8001 \
  RECETTE_PASSWORD='Intern-Demo-2026!' node tests/recette_navigateur.mjs
node tests/generer_cahier.mjs
xdg-open tests/cahier_de_tests.pdf
```

La recette crée un compte, l’active et ajoute une candidature : la base
`intern_recette_execution` est réservée à ces tests.
Les services de recette utilisent 8001 et 5175 : une démonstration déjà active
sur 8000/5173 est conservée. Elle n’est pas effacée.
Pour reproduire exactement les effectifs initiaux, utiliser une base dédiée neuve
avec `--database` et des ports libres avec `--api-port` / `--frontend-port`,
avant de lancer les couches.
Ne pas présenter une base déjà modifiée comme une base réinitialisée.
Les tests frontend contrôlés sont distincts de cette recette réelle :

```bash
npm --prefix frontend run build
npm --prefix frontend run lint
npm --prefix frontend run test:e2e
```

## Étape 7 — Préparer les machines

Prérequis : installer VirtualBox et ses modules, Python, curl, OpenSSH et `rg`
(`ripgrep` sur Ubuntu/Fedora). Prévoir au moins 5 Gio de RAM pour les trois VM,
les disques et les snapshots. Aucun serveur applicatif requis. Depuis Intern :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
mkdir -p "$VM_WORK/downloads" "$VM_WORK/access" "$VM_WORK/machines"
chmod 700 "$VM_WORK/access"
VBoxManage --version
if VBoxManage showvminfo vm-proxy >/dev/null 2>&1 && \
   VBoxManage showvminfo vm-metier >/dev/null 2>&1 && \
   VBoxManage showvminfo vm-donnees >/dev/null 2>&1; then
  echo 'Les trois VM existent : aucun nouveau modèle nécessaire.'
elif ! VBoxManage showvminfo vm-modele >/dev/null 2>&1; then

IMAGE_URL=https://cloud-images.ubuntu.com/releases/noble/release-20260926
curl -fL --retry 3 "$IMAGE_URL/SHA256SUMS" -o "$VM_WORK/downloads/SHA256SUMS"
curl -fL --retry 3 "$IMAGE_URL/ubuntu-24.04-server-cloudimg-amd64.ova" \
  -o "$VM_WORK/downloads/ubuntu-24.04-server-cloudimg-amd64.ova"
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

  until ssh -i "$VM_WORK/access/id_ed25519" -p 2220 -o BatchMode=yes \
    -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new \
    -o "UserKnownHostsFile=$VM_WORK/access/known_hosts" adminvm@127.0.0.1 true; do sleep 3; done
  ssh -i "$VM_WORK/access/id_ed25519" -p 2220 \
    -o "UserKnownHostsFile=$VM_WORK/access/known_hosts" \
    adminvm@127.0.0.1 'sudo bash -s' < deploiement/scripts/finaliser_modele.sh
  until VBoxManage showvminfo vm-modele --machinereadable | rg -q '^VMState="poweroff"$'; do sleep 2; done
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
VBoxManage list vms
```

Le modèle existant n’est pas recréé. En cas d’installation interrompue,
inspecter son état : sa simple présence ne prouve pas sa préparation.
La procédure détaillée est dans [deploiement/scripts/PROCEDURE.md](deploiement/scripts/PROCEDURE.md).
Pour une capture de la liste : ouvrir VirtualBox et afficher les trois VM.

## Étape 8 — Réseau et adressage

Prérequis : VirtualBox, Python, OpenSSH, `rg`. Si les VM manquent, exécuter
le bloc complet de l’étape 7. Cette étape n’installe pas encore l’application.
Sur les clones neufs et éteints, depuis Intern :

Préparation complète des VM requises, conservées si elles existent déjà :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
mkdir -p "$VM_WORK/downloads" "$VM_WORK/access" "$VM_WORK/machines"
chmod 700 "$VM_WORK/access"
VBoxManage --version
if VBoxManage showvminfo vm-proxy >/dev/null 2>&1 && \
   VBoxManage showvminfo vm-metier >/dev/null 2>&1 && \
   VBoxManage showvminfo vm-donnees >/dev/null 2>&1; then
  echo 'Les trois VM existent : aucun nouveau modèle nécessaire.'
elif ! VBoxManage showvminfo vm-modele >/dev/null 2>&1; then

IMAGE_URL=https://cloud-images.ubuntu.com/releases/noble/release-20260926
curl -fL --retry 3 "$IMAGE_URL/SHA256SUMS" -o "$VM_WORK/downloads/SHA256SUMS"
curl -fL --retry 3 "$IMAGE_URL/ubuntu-24.04-server-cloudimg-amd64.ova" \
  -o "$VM_WORK/downloads/ubuntu-24.04-server-cloudimg-amd64.ova"
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

  until ssh -i "$VM_WORK/access/id_ed25519" -p 2220 -o BatchMode=yes \
    -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new \
    -o "UserKnownHostsFile=$VM_WORK/access/known_hosts" adminvm@127.0.0.1 true; do sleep 3; done
  ssh -i "$VM_WORK/access/id_ed25519" -p 2220 \
    -o "UserKnownHostsFile=$VM_WORK/access/known_hosts" \
    adminvm@127.0.0.1 'sudo bash -s' < deploiement/scripts/finaliser_modele.sh
  until VBoxManage showvminfo vm-modele --machinereadable | rg -q '^VMState="poweroff"$'; do sleep 2; done
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
VBoxManage list vms
```

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
if VBoxManage showvminfo vm-proxy --machinereadable | rg -q '^intnet1="intnet-app"$'; then
  echo "Réseau déjà configuré : conservé"
else
  python3 deploiement/scripts/reseau_etape8.py "$VM_WORK"
fi
for vm in vm-proxy vm-metier vm-donnees; do VBoxManage showvminfo "$vm" --machinereadable; done
```

Pour vérifier un réseau déjà configuré, démarrer seulement les VM arrêtées
et ouvrir l’accès SSH temporaire :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
VBoxManage --version
for vm in vm-donnees vm-metier vm-proxy; do
  state=$(VBoxManage showvminfo "$vm" --machinereadable | sed -n 's/^VMState="\(.*\)"$/\1/p')
  case "$state" in
    running) echo "$vm déjà démarrée : conservée" ;;
    poweroff) VBoxManage startvm "$vm" --type headless ;;
    *) echo "$vm : état $state, inspecter avant de continuer" >&2; exit 1 ;;
  esac
done
if ! VBoxManage showvminfo vm-proxy --machinereadable | rg -q 'ssh-verification,tcp,127.0.0.1,2221'; then
  VBoxManage controlvm vm-proxy natpf2 'ssh-verification,tcp,127.0.0.1,2221,,22'
fi
test -f "$VM_WORK/access/ssh-etape8-interne.conf"
vmssh() {
  (cd "$VM_WORK/access" && ssh -F ssh-etape8-interne.conf "$@")
}
for vm in vm-donnees vm-metier vm-proxy; do
  until vmssh "$vm" true; do sleep 3; done
done
python3 deploiement/scripts/reseau_etape8.py "$VM_WORK" --verifier
```

Ce vérificateur arrête les VM et retire l’accès temporaire à la fin. Les
fichiers et le plan sont dans [deploiement/reseau/README.md](deploiement/reseau/README.md).

## Étape 9 — Déployer les couches

Prérequis : VirtualBox, Python, OpenSSH, uv, Node/npm et `rg`. Si les VM ou
le réseau manquent, exécuter les blocs 7 puis 8. Depuis Intern :

Préparation complète des VM requises, conservées si elles existent déjà :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
mkdir -p "$VM_WORK/downloads" "$VM_WORK/access" "$VM_WORK/machines"
chmod 700 "$VM_WORK/access"
VBoxManage --version
if VBoxManage showvminfo vm-proxy >/dev/null 2>&1 && \
   VBoxManage showvminfo vm-metier >/dev/null 2>&1 && \
   VBoxManage showvminfo vm-donnees >/dev/null 2>&1; then
  echo 'Les trois VM existent : aucun nouveau modèle nécessaire.'
elif ! VBoxManage showvminfo vm-modele >/dev/null 2>&1; then

IMAGE_URL=https://cloud-images.ubuntu.com/releases/noble/release-20260926
curl -fL --retry 3 "$IMAGE_URL/SHA256SUMS" -o "$VM_WORK/downloads/SHA256SUMS"
curl -fL --retry 3 "$IMAGE_URL/ubuntu-24.04-server-cloudimg-amd64.ova" \
  -o "$VM_WORK/downloads/ubuntu-24.04-server-cloudimg-amd64.ova"
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

  until ssh -i "$VM_WORK/access/id_ed25519" -p 2220 -o BatchMode=yes \
    -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new \
    -o "UserKnownHostsFile=$VM_WORK/access/known_hosts" adminvm@127.0.0.1 true; do sleep 3; done
  ssh -i "$VM_WORK/access/id_ed25519" -p 2220 \
    -o "UserKnownHostsFile=$VM_WORK/access/known_hosts" \
    adminvm@127.0.0.1 'sudo bash -s' < deploiement/scripts/finaliser_modele.sh
  until VBoxManage showvminfo vm-modele --machinereadable | rg -q '^VMState="poweroff"$'; do sleep 2; done
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
VBoxManage list vms
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
if VBoxManage showvminfo vm-proxy --machinereadable | rg -q '^intnet1="intnet-app"$'; then
  echo "Réseau déjà configuré : conservé"
else
  python3 deploiement/scripts/reseau_etape8.py "$VM_WORK"
fi
for vm in vm-proxy vm-metier vm-donnees; do VBoxManage showvminfo "$vm" --machinereadable; done
```

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
VBoxManage --version
for vm in vm-donnees vm-metier vm-proxy; do
  state=$(VBoxManage showvminfo "$vm" --machinereadable | sed -n 's/^VMState="\(.*\)"$/\1/p')
  case "$state" in
    running) echo "$vm déjà démarrée : conservée" ;;
    poweroff) VBoxManage startvm "$vm" --type headless ;;
    *) echo "$vm : état $state, inspecter avant de continuer" >&2; exit 1 ;;
  esac
done
if ! VBoxManage showvminfo vm-proxy --machinereadable | rg -q 'ssh-verification,tcp,127.0.0.1,2221'; then
  VBoxManage controlvm vm-proxy natpf2 'ssh-verification,tcp,127.0.0.1,2221,,22'
fi
test -f "$VM_WORK/access/ssh-etape8-interne.conf"
vmssh() {
  (cd "$VM_WORK/access" && ssh -F ssh-etape8-interne.conf "$@")
}
for vm in vm-donnees vm-metier vm-proxy; do
  until vmssh "$vm" true; do sleep 3; done
done
if vmssh vm-donnees 'test -f /etc/postgresql/16/main/conf.d/intern.conf'; then
  vmssh vm-donnees 'systemctl is-active --quiet postgresql || sudo systemctl start postgresql'
else
  python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" donnees
fi
if vmssh vm-metier 'systemctl cat intern.service >/dev/null 2>&1'; then
  vmssh vm-metier 'systemctl is-active --quiet intern || sudo systemctl start intern'
else
  python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" metier
fi
if vmssh vm-proxy 'test -f /etc/nginx/sites-available/intern'; then
  vmssh vm-proxy 'systemctl is-active --quiet nginx || sudo systemctl start nginx'
else
  npm --prefix frontend ci
  python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" proxy
fi
curl --fail http://127.0.0.1:8080/health/ready/
xdg-open http://127.0.0.1:8080/login
```

Une couche installée mais arrêtée doit d’abord être diagnostiquée, puis
démarrée avec `sudo systemctl start` dans sa VM ; ne pas restaurer sa base.
Les installateurs refusent notamment une base déjà présente. La première
installation peut redémarrer la VM concernée pour appliquer sa configuration.
API, présentation et administration passent ensuite par le proxy sur 8080.

## Étape 10 — Vérifier, mesurer et exporter

Prérequis : VirtualBox, Python, OpenSSH, `rg`. Si rien n’est préparé, exécuter
7 (machines), 8 (réseau), 9 (base, métier, proxy), dans cet ordre. Pour accéder
à l’application existante sans redémarrage, depuis Intern :

Préparation complète des VM requises, conservées si elles existent déjà :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
mkdir -p "$VM_WORK/downloads" "$VM_WORK/access" "$VM_WORK/machines"
chmod 700 "$VM_WORK/access"
VBoxManage --version
if VBoxManage showvminfo vm-proxy >/dev/null 2>&1 && \
   VBoxManage showvminfo vm-metier >/dev/null 2>&1 && \
   VBoxManage showvminfo vm-donnees >/dev/null 2>&1; then
  echo 'Les trois VM existent : aucun nouveau modèle nécessaire.'
elif ! VBoxManage showvminfo vm-modele >/dev/null 2>&1; then

IMAGE_URL=https://cloud-images.ubuntu.com/releases/noble/release-20260926
curl -fL --retry 3 "$IMAGE_URL/SHA256SUMS" -o "$VM_WORK/downloads/SHA256SUMS"
curl -fL --retry 3 "$IMAGE_URL/ubuntu-24.04-server-cloudimg-amd64.ova" \
  -o "$VM_WORK/downloads/ubuntu-24.04-server-cloudimg-amd64.ova"
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

  until ssh -i "$VM_WORK/access/id_ed25519" -p 2220 -o BatchMode=yes \
    -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new \
    -o "UserKnownHostsFile=$VM_WORK/access/known_hosts" adminvm@127.0.0.1 true; do sleep 3; done
  ssh -i "$VM_WORK/access/id_ed25519" -p 2220 \
    -o "UserKnownHostsFile=$VM_WORK/access/known_hosts" \
    adminvm@127.0.0.1 'sudo bash -s' < deploiement/scripts/finaliser_modele.sh
  until VBoxManage showvminfo vm-modele --machinereadable | rg -q '^VMState="poweroff"$'; do sleep 2; done
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
VBoxManage list vms
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
if VBoxManage showvminfo vm-proxy --machinereadable | rg -q '^intnet1="intnet-app"$'; then
  echo "Réseau déjà configuré : conservé"
else
  python3 deploiement/scripts/reseau_etape8.py "$VM_WORK"
fi
for vm in vm-proxy vm-metier vm-donnees; do VBoxManage showvminfo "$vm" --machinereadable; done
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
VBoxManage --version
for vm in vm-donnees vm-metier vm-proxy; do
  state=$(VBoxManage showvminfo "$vm" --machinereadable | sed -n 's/^VMState="\(.*\)"$/\1/p')
  case "$state" in
    running) echo "$vm déjà démarrée : conservée" ;;
    poweroff) VBoxManage startvm "$vm" --type headless ;;
    *) echo "$vm : état $state, inspecter avant de continuer" >&2; exit 1 ;;
  esac
done
if ! VBoxManage showvminfo vm-proxy --machinereadable | rg -q 'ssh-verification,tcp,127.0.0.1,2221'; then
  VBoxManage controlvm vm-proxy natpf2 'ssh-verification,tcp,127.0.0.1,2221,,22'
fi
test -f "$VM_WORK/access/ssh-etape8-interne.conf"
vmssh() {
  (cd "$VM_WORK/access" && ssh -F ssh-etape8-interne.conf "$@")
}
for vm in vm-donnees vm-metier vm-proxy; do
  until vmssh "$vm" true; do sleep 3; done
done
if vmssh vm-donnees 'test -f /etc/postgresql/16/main/conf.d/intern.conf'; then
  vmssh vm-donnees 'systemctl is-active --quiet postgresql || sudo systemctl start postgresql'
else
  python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" donnees
fi
if vmssh vm-metier 'systemctl cat intern.service >/dev/null 2>&1'; then
  vmssh vm-metier 'systemctl is-active --quiet intern || sudo systemctl start intern'
else
  python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" metier
fi
if vmssh vm-proxy 'test -f /etc/nginx/sites-available/intern'; then
  vmssh vm-proxy 'systemctl is-active --quiet nginx || sudo systemctl start nginx'
else
  npm --prefix frontend ci
  python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" proxy
fi
curl --fail http://127.0.0.1:8080/health/ready/
xdg-open http://127.0.0.1:8080/login
```

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
VBoxManage --version
for vm in vm-donnees vm-metier vm-proxy; do
  state=$(VBoxManage showvminfo "$vm" --machinereadable | sed -n 's/^VMState="\(.*\)"$/\1/p')
  case "$state" in
    running) echo "$vm déjà démarrée : conservée" ;;
    poweroff) VBoxManage startvm "$vm" --type headless ;;
    *) echo "$vm : état $state, inspecter avant de continuer" >&2; exit 1 ;;
  esac
done
curl --fail --retry 20 --retry-connrefused --retry-delay 2 http://127.0.0.1:8080/health/ready/
xdg-open http://127.0.0.1:8080/login
```

Pour lire les preuves existantes, aucune nouvelle mesure nécessaire :

```bash
cat deploiement/docs/etape10.md
cat deploiement/docs/mesures.md
cat deploiement/docs/exports-etape10.json
```

**Opération de mesure distincte** : elle arrête et relance les VM pour mesurer
leur démarrage. À exécuter seulement pour refaire les mesures ; elle remplace
les rapports de l’étape. Retirer d’abord l’accès SSH temporaire s’il est présent :

```bash
if VBoxManage showvminfo vm-proxy --machinereadable | rg -q ssh-verification; then
  VBoxManage controlvm vm-proxy natpf2 delete ssh-verification
fi
python3 deploiement/scripts/verifier_etape10.py "$VM_WORK"
python3 deploiement/scripts/exporter_etape10.py "$VM_WORK"
(cd "$VM_WORK/exports-etape10" && sha256sum -c SHA256SUMS)
```

L’export exige les VM éteintes ; le vérificateur les éteint en fin de mesure.
Les archives restent dans `$VM_WORK/exports-etape10`. Ne pas confondre cette
opération avec le démarrage conditionnel du premier bloc.

## Étape 11 — Couche données Docker

Prérequis : Python et Docker Engine/Compose du bloc initial. Les étapes DEV
ne doivent pas être en cours de modification de ces mêmes données. Depuis Intern :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -f .execution/moteur.env ]; then
  set -a
  source .execution/moteur.env
  set +a
fi
export DOCKER_BIN="${DOCKER_BIN:-docker}"
if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  if [ -n "${DOCKER_ENGINE_RUNTIME:-}" ]; then
    test -d "$DOCKER_ENGINE_RUNTIME"
    test -d "$DOCKER_ENGINE_DATA"
    test -x "$DOCKER_ENGINE_BIN/dockerd-rootless.sh"
    mkdir -p .execution
    PATH="$DOCKER_ENGINE_BIN:$PATH" XDG_RUNTIME_DIR="$DOCKER_ENGINE_RUNTIME" \
      nohup "$DOCKER_ENGINE_BIN/dockerd-rootless.sh" \
      --host="$DOCKER_HOST" --data-root="$DOCKER_ENGINE_DATA" \
      --exec-root="$DOCKER_ENGINE_RUNTIME/exec" --storage-driver=fuse-overlayfs \
      --pidfile="$DOCKER_ENGINE_RUNTIME/docker.pid" \
      > .execution/moteur.log 2>&1 < /dev/null &
  elif systemctl --user cat docker.service >/dev/null 2>&1; then
    systemctl --user start docker.service
  else
    sudo systemctl start docker.service
  fi
fi
for tentative in $(seq 1 60); do
  if "$DOCKER_BIN" info >/dev/null 2>&1; then break; fi
  sleep 1
done
"$DOCKER_BIN" info --format '{{.ServerVersion}}'
"$DOCKER_BIN" compose version
export DOCKER_ENV_FILE="${DOCKER_ENV_FILE:-docker/.env}"
export EXECUTION_PROJECT=intern-docker
bash outils/demarrer_docker.sh donnees
"$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml -p "$EXECUTION_PROJECT" \
  exec -T donnees sh -c 'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM jobboard_offer;"'
```

Le lanceur crée le fichier local de secrets seulement s’il manque. Une
configuration existante est conservée. PostgreSQL initialise le volume neuf
avec les SQL de l’étape 3 ; un volume existant n’est pas réimporté.
[Source du lanceur conditionnel](outils/demarrer_docker.sh). Aucun port SQL
n’est publié. Pour un test de persistance avec recréation volontaire, suivre
[la procédure de l’étape 11](docker/PROCEDURE.md#vérifier-la-persistance) ;
ce test est distinct d’un lancement normal et ne supprime pas le volume.

## Étape 12 — Image métier Docker

Prérequis : Python et Docker Engine/Compose du bloc initial. Même si rien
ne tourne, le bloc suivant prépare les images manquantes et démarre la base
puis le métier. Depuis Intern :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -f .execution/moteur.env ]; then
  set -a
  source .execution/moteur.env
  set +a
fi
export DOCKER_BIN="${DOCKER_BIN:-docker}"
if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  if [ -n "${DOCKER_ENGINE_RUNTIME:-}" ]; then
    test -d "$DOCKER_ENGINE_RUNTIME"
    test -d "$DOCKER_ENGINE_DATA"
    test -x "$DOCKER_ENGINE_BIN/dockerd-rootless.sh"
    mkdir -p .execution
    PATH="$DOCKER_ENGINE_BIN:$PATH" XDG_RUNTIME_DIR="$DOCKER_ENGINE_RUNTIME" \
      nohup "$DOCKER_ENGINE_BIN/dockerd-rootless.sh" \
      --host="$DOCKER_HOST" --data-root="$DOCKER_ENGINE_DATA" \
      --exec-root="$DOCKER_ENGINE_RUNTIME/exec" --storage-driver=fuse-overlayfs \
      --pidfile="$DOCKER_ENGINE_RUNTIME/docker.pid" \
      > .execution/moteur.log 2>&1 < /dev/null &
  elif systemctl --user cat docker.service >/dev/null 2>&1; then
    systemctl --user start docker.service
  else
    sudo systemctl start docker.service
  fi
fi
for tentative in $(seq 1 60); do
  if "$DOCKER_BIN" info >/dev/null 2>&1; then break; fi
  sleep 1
done
"$DOCKER_BIN" info --format '{{.ServerVersion}}'
"$DOCKER_BIN" compose version
export DOCKER_ENV_FILE="${DOCKER_ENV_FILE:-docker/.env}"
export EXECUTION_PROJECT=intern-docker
bash outils/demarrer_docker.sh metier
"$DOCKER_BIN" image inspect intern-metier:etape12 --format '{{.Size}}'
"$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml -p "$EXECUTION_PROJECT" \
  exec -T metier .venv/bin/python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/health/ready/").read().decode())'
```

Le métier n’est pas publié sur l’hôte : l’étape 13 ajoute le proxy.
Le lanceur ne reconstruit une image que si son tag est absent ; après un
changement du code, une reconstruction/remplacement volontaire relève d’une
mise à jour, pas de ce démarrage conditionnel.

## Étape 13 — Proxy et composition Docker

Prérequis : Python et Docker Engine/Compose du bloc initial. Depuis Intern,
construire seulement les images absentes et lancer les trois services manquants :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -f .execution/moteur.env ]; then
  set -a
  source .execution/moteur.env
  set +a
fi
export DOCKER_BIN="${DOCKER_BIN:-docker}"
if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  if [ -n "${DOCKER_ENGINE_RUNTIME:-}" ]; then
    test -d "$DOCKER_ENGINE_RUNTIME"
    test -d "$DOCKER_ENGINE_DATA"
    test -x "$DOCKER_ENGINE_BIN/dockerd-rootless.sh"
    mkdir -p .execution
    PATH="$DOCKER_ENGINE_BIN:$PATH" XDG_RUNTIME_DIR="$DOCKER_ENGINE_RUNTIME" \
      nohup "$DOCKER_ENGINE_BIN/dockerd-rootless.sh" \
      --host="$DOCKER_HOST" --data-root="$DOCKER_ENGINE_DATA" \
      --exec-root="$DOCKER_ENGINE_RUNTIME/exec" --storage-driver=fuse-overlayfs \
      --pidfile="$DOCKER_ENGINE_RUNTIME/docker.pid" \
      > .execution/moteur.log 2>&1 < /dev/null &
  elif systemctl --user cat docker.service >/dev/null 2>&1; then
    systemctl --user start docker.service
  else
    sudo systemctl start docker.service
  fi
fi
for tentative in $(seq 1 60); do
  if "$DOCKER_BIN" info >/dev/null 2>&1; then break; fi
  sleep 1
done
"$DOCKER_BIN" info --format '{{.ServerVersion}}'
"$DOCKER_BIN" compose version
export DOCKER_ENV_FILE="${DOCKER_ENV_FILE:-docker/.env}"
export EXECUTION_PROJECT=intern-docker
bash outils/demarrer_docker.sh proxy
curl --fail http://127.0.0.1:8080/health/ready/
xdg-open http://127.0.0.1:8080/login
```

Si 8080 est occupé par les VM, ne pas arrêter ce service implicitement :
choisir quel déploiement présenter, puis arrêter explicitement l’autre.
Connexion candidat/recruteur : mêmes comptes fictifs que l’étape 5.
L’administration est sur `http://127.0.0.1:8080/admin/`. Le fichier Compose
monte les fichiers SQL existants et conserve le volume nommé `pgdata`.

## Étape 14 — Vérifier et comparer Docker / VM

Prérequis : Python et Docker Engine/Compose du bloc initial. Si les mesures
VM manquent, réaliser 7 à 10 avant la comparaison. Depuis Intern :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -f .execution/moteur.env ]; then
  set -a
  source .execution/moteur.env
  set +a
fi
export DOCKER_BIN="${DOCKER_BIN:-docker}"
if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  if [ -n "${DOCKER_ENGINE_RUNTIME:-}" ]; then
    test -d "$DOCKER_ENGINE_RUNTIME"
    test -d "$DOCKER_ENGINE_DATA"
    test -x "$DOCKER_ENGINE_BIN/dockerd-rootless.sh"
    mkdir -p .execution
    PATH="$DOCKER_ENGINE_BIN:$PATH" XDG_RUNTIME_DIR="$DOCKER_ENGINE_RUNTIME" \
      nohup "$DOCKER_ENGINE_BIN/dockerd-rootless.sh" \
      --host="$DOCKER_HOST" --data-root="$DOCKER_ENGINE_DATA" \
      --exec-root="$DOCKER_ENGINE_RUNTIME/exec" --storage-driver=fuse-overlayfs \
      --pidfile="$DOCKER_ENGINE_RUNTIME/docker.pid" \
      > .execution/moteur.log 2>&1 < /dev/null &
  elif systemctl --user cat docker.service >/dev/null 2>&1; then
    systemctl --user start docker.service
  else
    sudo systemctl start docker.service
  fi
fi
for tentative in $(seq 1 60); do
  if "$DOCKER_BIN" info >/dev/null 2>&1; then break; fi
  sleep 1
done
"$DOCKER_BIN" info --format '{{.ServerVersion}}'
"$DOCKER_BIN" compose version
export DOCKER_ENV_FILE="${DOCKER_ENV_FILE:-docker/.env}"
export EXECUTION_PROJECT=intern-docker
bash outils/demarrer_docker.sh proxy
curl --fail http://127.0.0.1:8080/health/ready/
xdg-open docs/compte_rendu_comparaison.pdf
```

La consultation du rapport ne relance pas la campagne. Pour une nouvelle
mesure, utiliser un **projet dédié**, vérifier que 8080 est libre et fournir
`DOCKER_PIDFILE`, fichier contenant le PID réel du daemon mesuré. Pour un
moteur systemd classique, récupérer son PID sans le redémarrer :

```bash
mkdir -p .execution
systemctl show docker.service -p MainPID --value > .execution/docker-engine.pid
export DOCKER_PIDFILE="$PWD/.execution/docker-engine.pid"
test "$(cat "$DOCKER_PIDFILE")" -gt 0
export EXECUTION_PROJECT=intern-verification
bash outils/demarrer_docker.sh proxy
python3 docker/verifier-etape14.py --docker "$DOCKER_BIN" \
  --env-file "$DOCKER_ENV_FILE" --project "$EXECUTION_PROJECT" \
  --engine-pidfile "$DOCKER_PIDFILE"
python3 docker/rediger-comparaison.py
python3 docker/generer-comparaison.py
```

Cette mesure arrête/recrée les conteneurs du projet choisi pour les essais
de démarrage et de persistance, en gardant le volume. Elle remplace ses rapports.
Pour Docker rootless, utiliser le PID de ce daemon et les espaces de noms
expliqués dans [docker/PROCEDURE.md](docker/PROCEDURE.md). Ne pas utiliser
le PID d’un client Docker à la place de celui du moteur.

## Étape 15 — Plan JMeter

Prérequis : Python, Docker Engine/Compose, Java, curl, un affichage graphique
pour la GUI. Depuis Intern, préparer base, métier et proxy de mesure sur 8081
et installer JMeter s’il manque, même si aucun service n’est lancé :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
mkdir -p .execution
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -f .execution/moteur.env ]; then
  set -a
  source .execution/moteur.env
  set +a
fi
export DOCKER_BIN="${DOCKER_BIN:-docker}"
if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  if [ -n "${DOCKER_ENGINE_RUNTIME:-}" ]; then
    test -d "$DOCKER_ENGINE_RUNTIME"
    test -d "$DOCKER_ENGINE_DATA"
    test -x "$DOCKER_ENGINE_BIN/dockerd-rootless.sh"
    mkdir -p .execution
    PATH="$DOCKER_ENGINE_BIN:$PATH" XDG_RUNTIME_DIR="$DOCKER_ENGINE_RUNTIME" \
      nohup "$DOCKER_ENGINE_BIN/dockerd-rootless.sh" \
      --host="$DOCKER_HOST" --data-root="$DOCKER_ENGINE_DATA" \
      --exec-root="$DOCKER_ENGINE_RUNTIME/exec" --storage-driver=fuse-overlayfs \
      --pidfile="$DOCKER_ENGINE_RUNTIME/docker.pid" \
      > .execution/moteur.log 2>&1 < /dev/null &
  elif systemctl --user cat docker.service >/dev/null 2>&1; then
    systemctl --user start docker.service
  else
    sudo systemctl start docker.service
  fi
fi
for tentative in $(seq 1 60); do
  if "$DOCKER_BIN" info >/dev/null 2>&1; then break; fi
  sleep 1
done
"$DOCKER_BIN" info --format '{{.ServerVersion}}'
"$DOCKER_BIN" compose version
export JMETER_BIN="${JMETER_BIN:-$HOME/.local/share/intern-jmeter/apache-jmeter-5.6.3/bin/jmeter}"
if [ ! -x "$JMETER_BIN" ]; then
  mkdir -p "$HOME/.local/share/intern-jmeter"
  (
    cd "$HOME/.local/share/intern-jmeter"
    curl -fLO https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-5.6.3.tgz
    curl -fLO https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-5.6.3.tgz.sha512
    printf '%s  apache-jmeter-5.6.3.tgz\n' "$(cat apache-jmeter-5.6.3.tgz.sha512)" | sha512sum -c -
    tar -xf apache-jmeter-5.6.3.tgz
  )
fi
java -version
"$JMETER_BIN" --version
export DOCKER_ENV_FILE="${DOCKER_ENV_FILE:-docker/.env}"
export EXECUTION_PROJECT=intern-mesure
export EXECUTION_MESURE=1
bash outils/demarrer_docker.sh proxy
curl --fail http://127.0.0.1:8081/health/ready/
"$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml \
  -f mesure/compose.test.yaml -p "$EXECUTION_PROJECT" exec -T metier \
  .venv/bin/python app/manage.py shell --verbosity 0 \
  --command 'exec(__import__("sys").stdin.read())' \
  < mesure/scripts/preparer_comptes.py > .execution/comptes-mesure.csv
# Ne pas remplacer le CSV livré avant d’avoir confirmé la préparation.
test -s .execution/comptes-mesure.csv
cp .execution/comptes-mesure.csv mesure/comptes.csv
```

Depuis le dossier mesure, ouvrir le plan en GUI et exécuter une itération :

```bash
(cd mesure && "$JMETER_BIN" -t plan.jmx -Jport=8081)
```

Fermer cette GUI, puis ouvrir le cas d’échec :

```bash
(cd mesure && "$JMETER_BIN" -t plan.jmx -Jport=8081 -Jmot_de_passe=incorrect)
```

Pour la CLI, chaque résultat doit être neuf :

```bash
mkdir -p mesure/resultats/essai-execution15
(cd mesure && "$JMETER_BIN" -n -t plan.jmx -Jport=8081 \
  -l resultats/essai-execution15/reussite.jtl -j resultats/essai-execution15/reussite.log)
(cd mesure && "$JMETER_BIN" -n -t plan.jmx -Jport=8081 -Jmot_de_passe=incorrect \
  -l resultats/essai-execution15/echec.jtl -j resultats/essai-execution15/echec.log)
```

Le projet `intern-mesure` utilise un volume distinct. Les comptes de mesure
sont fictifs ; leur préparation refuse une identité existante incompatible.
La GUI nécessite une session de bureau ; un lancement CLI ne produit pas
une capture GUI. Conserver les résultats précédents.

## Étape 16 — Étalonnage

Prérequis : Python, Docker Engine/Compose, Java et curl. Depuis Intern,
répéter la préparation complète, même si rien n’est actif :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
mkdir -p .execution
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -f .execution/moteur.env ]; then
  set -a
  source .execution/moteur.env
  set +a
fi
export DOCKER_BIN="${DOCKER_BIN:-docker}"
if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  if [ -n "${DOCKER_ENGINE_RUNTIME:-}" ]; then
    test -d "$DOCKER_ENGINE_RUNTIME"
    test -d "$DOCKER_ENGINE_DATA"
    test -x "$DOCKER_ENGINE_BIN/dockerd-rootless.sh"
    mkdir -p .execution
    PATH="$DOCKER_ENGINE_BIN:$PATH" XDG_RUNTIME_DIR="$DOCKER_ENGINE_RUNTIME" \
      nohup "$DOCKER_ENGINE_BIN/dockerd-rootless.sh" \
      --host="$DOCKER_HOST" --data-root="$DOCKER_ENGINE_DATA" \
      --exec-root="$DOCKER_ENGINE_RUNTIME/exec" --storage-driver=fuse-overlayfs \
      --pidfile="$DOCKER_ENGINE_RUNTIME/docker.pid" \
      > .execution/moteur.log 2>&1 < /dev/null &
  elif systemctl --user cat docker.service >/dev/null 2>&1; then
    systemctl --user start docker.service
  else
    sudo systemctl start docker.service
  fi
fi
for tentative in $(seq 1 60); do
  if "$DOCKER_BIN" info >/dev/null 2>&1; then break; fi
  sleep 1
done
"$DOCKER_BIN" info --format '{{.ServerVersion}}'
"$DOCKER_BIN" compose version
export JMETER_BIN="${JMETER_BIN:-$HOME/.local/share/intern-jmeter/apache-jmeter-5.6.3/bin/jmeter}"
if [ ! -x "$JMETER_BIN" ]; then
  mkdir -p "$HOME/.local/share/intern-jmeter"
  (
    cd "$HOME/.local/share/intern-jmeter"
    curl -fLO https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-5.6.3.tgz
    curl -fLO https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-5.6.3.tgz.sha512
    printf '%s  apache-jmeter-5.6.3.tgz\n' "$(cat apache-jmeter-5.6.3.tgz.sha512)" | sha512sum -c -
    tar -xf apache-jmeter-5.6.3.tgz
  )
fi
java -version
"$JMETER_BIN" --version
export DOCKER_ENV_FILE="${DOCKER_ENV_FILE:-docker/.env}"
export EXECUTION_PROJECT=intern-mesure
export EXECUTION_MESURE=1
bash outils/demarrer_docker.sh proxy
curl --fail http://127.0.0.1:8081/health/ready/
"$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml \
  -f mesure/compose.test.yaml -p "$EXECUTION_PROJECT" exec -T metier \
  .venv/bin/python app/manage.py shell --verbosity 0 \
  --command 'exec(__import__("sys").stdin.read())' \
  < mesure/scripts/preparer_comptes.py > .execution/comptes-mesure.csv
# Ne pas remplacer le CSV livré avant d’avoir confirmé la préparation.
test -s .execution/comptes-mesure.csv
cp .execution/comptes-mesure.csv mesure/comptes.csv
```

Les autres déploiements doivent rester arrêtés pendant une mesure : vérifier
`VBoxManage list runningvms` et `"$DOCKER_BIN" ps`, puis arrêter explicitement
ceux qui ne font pas partie de cet essai. Ne pas lancer un arrêt global.

```bash
python3 mesure/scripts/etalonnage.py static --jmeter "$JMETER_BIN" \
  --users 1 --output mesure/resultats/etape16/statique-1
python3 mesure/scripts/etalonnage.py static --jmeter "$JMETER_BIN" \
  --users 20 --output mesure/resultats/etape16/statique-20
python3 mesure/scripts/etalonnage.py application --jmeter "$JMETER_BIN" \
  --users 10 --output mesure/resultats/etape16/controle-1
sleep 30
python3 mesure/scripts/etalonnage.py application --jmeter "$JMETER_BIN" \
  --users 10 --output mesure/resultats/etape16/controle-2
python3 mesure/scripts/rediger_etalonnage.py
```

Les dossiers livrés existent déjà : les lire pour la démonstration. Pour
refaire les mesures, conserver ces preuves et employer des sorties neuves.
Le générateur de rapport lit les quatre chemins canoniques ci-dessus ; ne
pas mélanger anciennes mesures et nouvelles configurations.
Les résultats archivés sont dans [mesure/ETAPE16.md](mesure/ETAPE16.md).

## Étape 17 — Campagnes

Prérequis : Python, VirtualBox, OpenSSH, `rg`, Docker Engine/Compose, Java, curl.
Si rien n’est préparé : réaliser 7–9 pour les VM et 15–16 pour le déploiement
de mesure et le protocole. Ces préparations sont nécessaires avant une campagne
qui alterne réellement les deux déploiements. Depuis Intern :

Préparation complète des VM requises, conservées si elles existent déjà :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
mkdir -p "$VM_WORK/downloads" "$VM_WORK/access" "$VM_WORK/machines"
chmod 700 "$VM_WORK/access"
VBoxManage --version
if VBoxManage showvminfo vm-proxy >/dev/null 2>&1 && \
   VBoxManage showvminfo vm-metier >/dev/null 2>&1 && \
   VBoxManage showvminfo vm-donnees >/dev/null 2>&1; then
  echo 'Les trois VM existent : aucun nouveau modèle nécessaire.'
elif ! VBoxManage showvminfo vm-modele >/dev/null 2>&1; then

IMAGE_URL=https://cloud-images.ubuntu.com/releases/noble/release-20260926
curl -fL --retry 3 "$IMAGE_URL/SHA256SUMS" -o "$VM_WORK/downloads/SHA256SUMS"
curl -fL --retry 3 "$IMAGE_URL/ubuntu-24.04-server-cloudimg-amd64.ova" \
  -o "$VM_WORK/downloads/ubuntu-24.04-server-cloudimg-amd64.ova"
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

  until ssh -i "$VM_WORK/access/id_ed25519" -p 2220 -o BatchMode=yes \
    -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new \
    -o "UserKnownHostsFile=$VM_WORK/access/known_hosts" adminvm@127.0.0.1 true; do sleep 3; done
  ssh -i "$VM_WORK/access/id_ed25519" -p 2220 \
    -o "UserKnownHostsFile=$VM_WORK/access/known_hosts" \
    adminvm@127.0.0.1 'sudo bash -s' < deploiement/scripts/finaliser_modele.sh
  until VBoxManage showvminfo vm-modele --machinereadable | rg -q '^VMState="poweroff"$'; do sleep 2; done
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
VBoxManage list vms
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
if VBoxManage showvminfo vm-proxy --machinereadable | rg -q '^intnet1="intnet-app"$'; then
  echo "Réseau déjà configuré : conservé"
else
  python3 deploiement/scripts/reseau_etape8.py "$VM_WORK"
fi
for vm in vm-proxy vm-metier vm-donnees; do VBoxManage showvminfo "$vm" --machinereadable; done
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
VBoxManage --version
for vm in vm-donnees vm-metier vm-proxy; do
  state=$(VBoxManage showvminfo "$vm" --machinereadable | sed -n 's/^VMState="\(.*\)"$/\1/p')
  case "$state" in
    running) echo "$vm déjà démarrée : conservée" ;;
    poweroff) VBoxManage startvm "$vm" --type headless ;;
    *) echo "$vm : état $state, inspecter avant de continuer" >&2; exit 1 ;;
  esac
done
if ! VBoxManage showvminfo vm-proxy --machinereadable | rg -q 'ssh-verification,tcp,127.0.0.1,2221'; then
  VBoxManage controlvm vm-proxy natpf2 'ssh-verification,tcp,127.0.0.1,2221,,22'
fi
test -f "$VM_WORK/access/ssh-etape8-interne.conf"
vmssh() {
  (cd "$VM_WORK/access" && ssh -F ssh-etape8-interne.conf "$@")
}
for vm in vm-donnees vm-metier vm-proxy; do
  until vmssh "$vm" true; do sleep 3; done
done
if vmssh vm-donnees 'test -f /etc/postgresql/16/main/conf.d/intern.conf'; then
  vmssh vm-donnees 'systemctl is-active --quiet postgresql || sudo systemctl start postgresql'
else
  python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" donnees
fi
if vmssh vm-metier 'systemctl cat intern.service >/dev/null 2>&1'; then
  vmssh vm-metier 'systemctl is-active --quiet intern || sudo systemctl start intern'
else
  python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" metier
fi
if vmssh vm-proxy 'test -f /etc/nginx/sites-available/intern'; then
  vmssh vm-proxy 'systemctl is-active --quiet nginx || sudo systemctl start nginx'
else
  npm --prefix frontend ci
  python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" proxy
fi
curl --fail http://127.0.0.1:8080/health/ready/
xdg-open http://127.0.0.1:8080/login
```

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ -f .execution/moteur.env ]; then
  set -a
  source .execution/moteur.env
  set +a
fi
export DOCKER_BIN="${DOCKER_BIN:-docker}"
if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  if [ -n "${DOCKER_ENGINE_RUNTIME:-}" ]; then
    test -d "$DOCKER_ENGINE_RUNTIME"
    test -d "$DOCKER_ENGINE_DATA"
    test -x "$DOCKER_ENGINE_BIN/dockerd-rootless.sh"
    mkdir -p .execution
    PATH="$DOCKER_ENGINE_BIN:$PATH" XDG_RUNTIME_DIR="$DOCKER_ENGINE_RUNTIME" \
      nohup "$DOCKER_ENGINE_BIN/dockerd-rootless.sh" \
      --host="$DOCKER_HOST" --data-root="$DOCKER_ENGINE_DATA" \
      --exec-root="$DOCKER_ENGINE_RUNTIME/exec" --storage-driver=fuse-overlayfs \
      --pidfile="$DOCKER_ENGINE_RUNTIME/docker.pid" \
      > .execution/moteur.log 2>&1 < /dev/null &
  elif systemctl --user cat docker.service >/dev/null 2>&1; then
    systemctl --user start docker.service
  else
    sudo systemctl start docker.service
  fi
fi
for tentative in $(seq 1 60); do
  if "$DOCKER_BIN" info >/dev/null 2>&1; then break; fi
  sleep 1
done
"$DOCKER_BIN" info --format '{{.ServerVersion}}'
"$DOCKER_BIN" compose version
export JMETER_BIN="${JMETER_BIN:-$HOME/.local/share/intern-jmeter/apache-jmeter-5.6.3/bin/jmeter}"
if [ ! -x "$JMETER_BIN" ]; then
  mkdir -p "$HOME/.local/share/intern-jmeter"
  (
    cd "$HOME/.local/share/intern-jmeter"
    curl -fLO https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-5.6.3.tgz
    curl -fLO https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-5.6.3.tgz.sha512
    printf '%s  apache-jmeter-5.6.3.tgz\n' "$(cat apache-jmeter-5.6.3.tgz.sha512)" | sha512sum -c -
    tar -xf apache-jmeter-5.6.3.tgz
  )
fi
java -version
"$JMETER_BIN" --version
if [ -z "${VM_WORK:-}" ] && [ -d ../.local-vms/access ]; then
  export VM_WORK="$(cd ../.local-vms && pwd)"
else
  export VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
fi
export DOCKER_ENV_FILE="${DOCKER_ENV_FILE:-$PWD/docker/.env}"
export MESURE_SSH_CONFIG="$VM_WORK/access/ssh-etape8-interne.conf"
export MESURE_RUNTIME="${MESURE_RUNTIME:-$PWD/../.execution-campagnes}"
export MESURE_OUTPUT="${MESURE_OUTPUT:-$PWD/mesure/resultats/nouvelle-campagne}"
export MESURE_REFERENCE_PROJECT="${MESURE_REFERENCE_PROJECT:-intern-docker}"
export DOCKER_CONFIG="${DOCKER_CONFIG:-$HOME/.docker}"
export DOCKER_HOST="${DOCKER_HOST:-unix:///var/run/docker.sock}"
export DOCKER_BIN="$(command -v "$DOCKER_BIN")"
test -f "$DOCKER_ENV_FILE"
test -f "$MESURE_SSH_CONFIG"
mkdir -p "$DOCKER_CONFIG"
VBoxManage list vms
python3 - <<'PY'
import json, os
from pathlib import Path
paths = {"docker": "DOCKER_BIN", "docker_config": "DOCKER_CONFIG",
         "env_file": "DOCKER_ENV_FILE", "ssh_config": "MESURE_SSH_CONFIG",
         "jmeter": "JMETER_BIN", "runtime": "MESURE_RUNTIME", "output": "MESURE_OUTPUT"}
config = {key: str(Path(os.environ[var]).resolve()) for key, var in paths.items()}
config.update(docker_host=os.environ["DOCKER_HOST"], reference_project=os.environ["MESURE_REFERENCE_PROJECT"])
runtime = Path(config["runtime"])
if runtime.is_relative_to(Path.cwd().resolve()): raise SystemExit("Dossier privé requis hors Intern")
runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
path = runtime / "configuration.json"
if not path.exists():
    path.write_text(json.dumps(config, indent=2) + "\n")
    path.chmod(0o600)
else:
    print("Configuration existante conservée : vérifier ses chemins avant le lancement")
PY
python3 mesure/scripts/lancer17.py status --runtime "$MESURE_RUNTIME"
```

Vérifier les chemins et le nom exact du projet de référence avant le lancement.
Le lanceur refuse une seconde campagne si son processus est encore actif.
Ne pas lancer de nouvelle campagne si le manifeste existant est complet :
choisir une nouvelle configuration et un nouveau dossier de résultats.

```bash
python3 mesure/scripts/lancer17.py start --runtime "$MESURE_RUNTIME"
python3 mesure/scripts/lancer17.py status --runtime "$MESURE_RUNTIME"
```

Laisser l’hôte allumé : environ 3 h 45 min, plus préparation et transitions.
Le pilote gère volontairement les arrêts et démarrages des déploiements :
un simple démarrage conditionnel ne permettrait pas de comparer leurs charges.
Les VM doivent avoir leur accès SSH de maintenance prêt selon l’étape 9.
Le contrôleur conserve les bases initiales, restaure uniquement les bases de
mesure et rétablit le projet de référence.

Pour vérifier les **preuves livrées**, sans lancer de charge ni démarrer de
serveur :

```bash
python3 mesure/scripts/verifier17.py
cat mesure/resultats/etape17/verification.json
```

Le vérificateur ci-dessus lit `resultats/etape17`, pas une nouvelle campagne.
Une nouvelle sortie doit être vérifiée et rattachée explicitement au rapport
avant d’être utilisée comme preuve. Détails : [mesure/ETAPE17.md](mesure/ETAPE17.md).

## Étape 18 — Analyse des mesures

Prérequis : Python et pip/venv du bloc initial. **Aucune base, API, présentation,
VM ou conteneur à lancer** pour analyser les fichiers archivés. Si les résultats
17 manquent, réaliser la campagne avant l’analyse. Depuis Intern :

```bash
set -e
export PATH="$HOME/.local/bin:$HOME/.local/share/intern-node/node-v22.17.0-linux-x64/bin:$PATH"
if [ ! -x .execution/analyse/bin/python ]; then python3 -m venv .execution/analyse; fi
.execution/analyse/bin/pip install -r mesure/requirements-analyse.txt
.execution/analyse/bin/python mesure/scripts/verifier17.py
.execution/analyse/bin/python mesure/scripts/analyser18.py
.execution/analyse/bin/python mesure/scripts/generer_rapport18.py
xdg-open mesure/docs/rapport-charge.pdf
```

Ces scripts utilisent les preuves canoniques `mesure/resultats/etape17`.
Ils recalculent les statistiques et génèrent les courbes et le PDF sans
simuler des mesures. Le lancement de nouveaux services ne rendrait pas
ces résultats archivés plus actuels.

## Diagnostic et arrêt volontaire des services locaux

Depuis Intern, lire les journaux sans relancer les services :

```bash
tail -n 50 .execution/metier.log
tail -n 50 .execution/presentation.log
```

Les PID enregistrés permettent d’identifier les processus, mais leur présence
ne prouve pas que le service est prêt : les lanceurs vérifient le SQL et le HTTP.
Avant un arrêt volontaire, vérifier le processus indiqué avec `ps -p PID -o args=`.
Ne pas supprimer un volume pour corriger un service indisponible.

## Vérification de ce guide

Les blocs DEV et les captures sont vérifiés sur la machine de travail avec une
base dédiée. Les 34 contrôles SQL passent dans la base réservée à l’étape 3 ;
les 15 parcours de recette passent sur la base et les ports de l’étape 6.
Les trois services Docker de cours sont également lancés sur un
projet dédié ; un second lancement conserve leurs IDs et dates de démarrage. Cette vérification n’est pas une installation de tous les outils
sur une machine vierge. Les commandes VM et JMeter reprennent
les outils et procédures du dépôt ; les nouvelles campagnes, installations
système, exports et mesures ne sont pas relancés pour vérifier ce document.
