# Prérequis d’exécution

Choisir le système du poste avant de suivre [EXECUTION.md](EXECUTION.md) :

| Système | Installation | Périmètre |
| --- | --- | --- |
| Ubuntu / Fedora | [Linux](prerequis/linux/REQUIREMENT.md) | Guide complet sur hôte x86_64 avec VirtualBox fonctionnel |
| macOS Intel / Apple Silicon | [macOS](prerequis/macos/REQUIREMENT.md) | DEV et Docker ; restrictions VM dans le document |
| Windows | [Windows et WSL 2](prerequis/windows/REQUIREMENT.md) | DEV et Docker dans Ubuntu WSL ; restrictions VM dans le document |

Les commandes du guide commun utilisent Bash. Ne pas les coller dans PowerShell
ou `cmd.exe`. Les installations système nécessitent parfois un administrateur.
Les prérequis par système sont documentés ; ils ne constituent pas une preuve
d’exécution sur chacun de ces systèmes.

## Outils selon les étapes

| Étapes | Outils |
| --- | --- |
| 1–2 | Python 3.12+, pip/venv, navigateur et lecteur PDF |
| 3–4 | Python 3.12+, uv, client PostgreSQL 16 à jour, Docker Engine et Compose v2 |
| 5–6 | Outils précédents, Node 22.12+ et npm, navigateur Playwright |
| 7–10 | Hôte Linux x86_64, VirtualBox et modules noyau, OpenSSH, curl, ripgrep |
| 11–14 | Docker Engine et Compose v2 ; outils PDF pour les rapports |
| 15–17 | Java 21, JMeter 5.6.3 (installé par le guide), outils Docker et VM selon l’essai |
| 18 | Python, pip/venv ; dépendances du rapport installées par le guide |

Node 20.19+ est également accepté par le frontend. Préférer la même version
Node pour comparer deux exécutions. Le SQL livré contient `\restrict` : un
ancien client PostgreSQL 16 peut nécessiter une mise à jour.

Depuis `Intern`, dans le terminal utilisé pour le guide :

```bash
python3 --version
uv --version
node --version
npm --version
psql --version
docker info
docker compose version
uv sync --project metier --frozen
```

Pas besoin d’activer un environnement Python. Si un autre est actif,
`deactivate` avant une commande manuelle `uv`. Le lanceur utilise `metier/.venv`.
La [documentation uv](https://docs.astral.sh/uv/concepts/projects/config/)
explique le choix de l’environnement du projet.

## Docker fonctionne dans mon terminal, mais pas dans le lanceur

`docker --version` vérifie le client ; `docker info` vérifie l’accès au serveur.
Exécuter ces diagnostics dans le même terminal que le lanceur :

```bash
command -v docker
docker context show
docker info
docker compose version
```

## Générer automatiquement moteur.env

Depuis `Intern`, détecter le véritable Docker Engine et remplir la configuration :

```bash
python3 outils/configurer_moteur.py
```

Le script exclut Podman, teste le client et Compose, reprend le stockage existant,
protège les chemins contenant des espaces et sauvegarde l’ancien fichier avant
remplacement. Une seconde exécution identique ne réécrit pas la configuration.

Si les anciens binaires se trouvaient dans `/tmp` et ont disparu, restaurer les
binaires Linux et démarrer le même moteur rootless :

```bash
python3 outils/configurer_moteur.py --restaurer --demarrer
python3 outils/demarrer_local.py metier
```

Les binaires Docker 28.3.3 et Compose 2.39.4 sont conservés dans
`.execution/docker-engine/`, hors `/tmp`. Le stockage `DOCKER_ENGINE_DATA`
est repris depuis l’ancien fichier et doit déjà exister. S’il n’existe pas de
configuration précédente, indiquer le stockage réel avec `--data-root /chemin/existant`.
Le script ne crée pas un stockage de remplacement et ne touche pas aux données
Podman. La restauration utilise les [archives officielles Docker](https://docs.docker.com/engine/install/binaries/)
et le plugin Compose officiel avec contrôle SHA-256 ; elle nécessite Internet.
Les prérequis [Docker rootless](https://docs.docker.com/engine/security/rootless/)
`newuidmap`, `newgidmap` et `fuse-overlayfs` doivent déjà être installés.
Sur Fedora : `sudo dnf install shadow-utils fuse-overlayfs` ;
sur Ubuntu : `sudo apt-get install uidmap fuse-overlayfs`.

Sans `--demarrer`, le script configure un moteur rootless existant sans lancer
le daemon. En cas d’échec, lire le message et `.execution/moteur.log` ; l’ancien
`moteur.env` est conservé. Le script n’active pas de service au démarrage du poste.
Pour un client installé à un emplacement particulier, utiliser
`--docker-bin /chemin/vers/docker`.

Une commande interactive `docker` peut être un alias ou une fonction du shell :
Python attend un exécutable. Le fichier produit contient les chemins réels.
Après une régénération, ouvrir un nouveau terminal ou charger sa configuration :

```bash
source .execution/moteur.env
"$DOCKER_BIN" info
"$DOCKER_BIN" compose version
```

Ne définir `DOCKER_HOST` que si ce moteur en a besoin ; une ancienne valeur
peut masquer un contexte Docker Desktop valide. Le lanceur charge ce fichier
Bash local, puis `.execution/local.env`. Ne pas copier les chemins d’un autre
poste. Un moteur joignable est conservé ; le lanceur Python ne démarre pas le
daemon Docker. Démarrer Docker Desktop ou le service installé selon le système.
Un client Podman qui émule `docker` ne valide pas les étapes Docker Engine.
Conserver les volumes et les répertoires de données existants.
