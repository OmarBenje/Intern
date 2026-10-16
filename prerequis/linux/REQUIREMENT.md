# Linux — prérequis

Le guide complet cible un hôte Linux x86_64. Les couches DEV/Docker peuvent
être préparées sur ARM64, mais l’image VM livrée est `amd64`.

## Ubuntu 24.04

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip curl git openssh-client \
  postgresql-client-16 docker.io docker-compose-v2 xz-utils unzip \
  poppler-utils virtualbox default-jre ripgrep xdg-utils
```

## Fedora

```bash
sudo dnf install -y python3 python3-pip curl git openssh-clients \
  postgresql docker-cli moby-engine docker-compose xz unzip poppler-utils \
  java-21-openjdk ripgrep xdg-utils
```

Selon la version de Fedora et ses dépôts, les noms de paquets Docker peuvent
varier. S’ils sont absents, suivre l’[installation officielle Docker Engine
pour Fedora](https://docs.docker.com/engine/install/fedora/).
Installer [VirtualBox](https://www.virtualbox.org/wiki/Linux_Downloads) avec
les modules adaptés au noyau pour les étapes VM. Vérifier `VBoxManage --version`.

## uv et Node

Installer uv dans un environnement d’outillage distinct, seulement s’il manque :

```bash
if ! command -v uv >/dev/null; then
  python3 -m venv "$HOME/.local/share/intern-uv"
  "$HOME/.local/share/intern-uv/bin/pip" install uv==0.11.29
  mkdir -p "$HOME/.local/bin"
  ln -s "$HOME/.local/share/intern-uv/bin/uv" "$HOME/.local/bin/uv"
fi
export PATH="$HOME/.local/bin:$PATH"
```

Pour Node, utiliser une version compatible déjà installée, ou installer cette
archive Linux selon l’architecture. Le bloc ne remplace pas un Node compatible :

```bash
if ! node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit((a===20&&b>=19)||(a===22&&b>=12)||a>22?0:1)' 2>/dev/null; then
  case "$(uname -m)" in
    x86_64) INTERN_NODE_ARCH=x64 ;;
    aarch64|arm64) INTERN_NODE_ARCH=arm64 ;;
    *) echo 'Architecture Node à installer manuellement'; exit 1 ;;
  esac
  mkdir -p "$HOME/.local/share/intern-node"
  (
    set -e
    cd "$HOME/.local/share/intern-node"
    INTERN_NODE_FILE="node-v22.17.0-linux-$INTERN_NODE_ARCH.tar.xz"
    curl -fLO "https://nodejs.org/dist/v22.17.0/$INTERN_NODE_FILE"
    curl -fLO https://nodejs.org/dist/v22.17.0/SHASUMS256.txt
    sha256sum --ignore-missing -c SHASUMS256.txt
    tar -xf "$INTERN_NODE_FILE"
    mkdir -p "$HOME/.local/bin"
    for tool in node npm npx; do
      ln -sf "$HOME/.local/share/intern-node/node-v22.17.0-linux-$INTERN_NODE_ARCH/bin/$tool" "$HOME/.local/bin/$tool"
    done
  )
fi
```

Ajouter `export PATH="$HOME/.local/bin:$PATH"` à la configuration Bash pour
les prochains terminaux. Les archives Node sont propres au système et à
l’architecture : ne pas utiliser l’archive Linux sur macOS ou Windows natif.

## Accès Docker

Si `docker info` fonctionne, conserver le moteur. Sinon, pour une installation
avec service système (les droits sur le socket doivent déjà être configurés) :

```bash
sudo systemctl start docker.service
```

Pour un moteur rootless installé comme service utilisateur :

```bash
systemctl --user start docker.service
```

Choisir le service réellement installé. Un problème de permission sur le socket
se règle selon l’[installation Docker](https://docs.docker.com/engine/install/linux-postinstall/),
pas en supprimant des volumes. Une installation rootless manuelle existante peut
être décrite dans `.execution/moteur.env` selon le guide commun.

Reprendre les [vérifications communes](../../REQUIREMENT.md).
