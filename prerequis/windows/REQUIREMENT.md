# Windows — prérequis avec WSL 2

Les scripts sont écrits pour Bash et les environnements Python Unix.
Pour Windows, utiliser Ubuntu 24.04 sous WSL 2 ; PowerShell sert seulement
à l’installation initiale. Dans un PowerShell administrateur :

```powershell
wsl --install -d Ubuntu-24.04
wsl --list --verbose
```

Redémarrer si Windows le demande, créer l’utilisateur Ubuntu et vérifier que
la distribution utilise la version 2. Voir l’[installation officielle WSL](https://learn.microsoft.com/windows/wsl/install).

Installer [Docker Desktop pour Windows](https://docs.docker.com/desktop/setup/install/windows-install/),
activer le moteur WSL 2 et l’intégration de la distribution Ubuntu dans
**Settings > Resources > WSL Integration**. Démarrer Desktop et attendre
sa disponibilité. La [documentation Docker WSL](https://docs.docker.com/desktop/features/wsl/)
décrit cette configuration. Ne pas installer un second daemon Docker dans
Ubuntu lorsque l’intégration Desktop fournit déjà le moteur.

Toutes les commandes suivantes se lancent dans **Ubuntu WSL**, depuis une
copie du dépôt dans le système de fichiers Linux, par exemple `~/projets/Intern`.
Ne pas réutiliser `.venv` ou `node_modules` créés sous Windows.

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip curl git openssh-client \
  postgresql-client-16 xz-utils unzip poppler-utils default-jre ripgrep xdg-utils
```

Installer ensuite uv et Node avec le bloc **uv et Node** des
[prérequis Linux](../linux/REQUIREMENT.md), sans ses installations Docker et
VirtualBox. Vérifier `docker info` et `docker compose version` dans Ubuntu.
Si ces commandes échouent, vérifier Desktop et l’intégration WSL avant de lancer
le guide. Les branches `systemctl` sont ignorées quand Docker est joignable.

Les étapes DEV 1–6, Docker et l’analyse des fichiers peuvent être préparées
dans WSL. `python3 outils/ouvrir.py` ouvre les fichiers ou URL avec Windows ;
sans outil graphique disponible, il indique la cible à ouvrir manuellement.

Les étapes VirtualBox 7–10 et la campagne comparative 17 ne sont pas prévues
pour une exécution dans WSL : elles utilisent `VBoxManage`, des chemins SSH,
des réseaux et des scripts d’hôte Linux. Installer VirtualBox côté Windows
ne suffit pas à rendre ces blocs compatibles. Pour les reproduire, utiliser
un hôte Linux x86_64. Aucun parcours Windows natif n’est validé ici.

Reprendre les [vérifications communes](../../REQUIREMENT.md), puis
[EXECUTION.md](../../EXECUTION.md) dans Bash Ubuntu.
