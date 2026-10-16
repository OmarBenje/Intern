# macOS — prérequis

Utiliser un terminal Bash (`bash`), puis se placer dans `Intern`.
Installer [Homebrew](https://brew.sh/) s’il manque, puis les outils absents :

```bash
brew install python@3.12 uv node@22 libpq poppler ripgrep coreutils gnu-sed openjdk@21
export PATH="$(brew --prefix python@3.12)/libexec/bin:$(brew --prefix node@22)/bin:$(brew --prefix libpq)/bin:$(brew --prefix coreutils)/libexec/gnubin:$(brew --prefix gnu-sed)/libexec/gnubin:$(brew --prefix openjdk@21)/bin:$HOME/.local/bin:$PATH"
```

Conserver cette configuration PATH dans `~/.bash_profile` pour les nouveaux
terminaux Bash. Homebrew choisit son préfixe selon Intel ou Apple Silicon ;
ne pas copier un chemin `/usr/local` ou `/opt/homebrew` d’un autre poste.
`libpq` fournit les clients SQL ; vérifier un client au moins 16 à jour.
Les outils GNU rendent disponibles `sha256sum`, `sha512sum`, `seq` et les
options utilisées pour les archives et rapports du guide.

Installer [Docker Desktop pour Mac](https://docs.docker.com/desktop/setup/install/mac-install/)
pour l’architecture du poste, l’ouvrir et attendre que `docker info` réponde.
Les blocs `systemctl` du guide concernent Linux : avec Docker Desktop déjà
joignable, ils sont ignorés. Si Desktop est arrêté, l’ouvrir avant chaque étape
Docker. Ne pas exporter un socket Linux par défaut sur macOS.

Les étapes DEV 1–6 et Docker peuvent être préparées ainsi. Pour Playwright,
utiliser l’installation du navigateur décrite dans le guide ; les bibliothèques
système Linux ne s’installent pas avec `apt` sur macOS.

Les étapes 7–10 et 17 réutilisent une image Ubuntu **amd64**, des scripts et un
réseau VirtualBox préparés sur Linux. Elles ne sont pas validées sur macOS ;
Apple Silicon ne peut pas exécuter cette image avec la même procédure native.
Pour reproduire ces étapes et la comparaison des mesures, utiliser un hôte
Linux x86_64 et y suivre le guide complet. Ne pas mélanger des mesures de
machines différentes dans une campagne comparable.

Reprendre les [vérifications communes](../../REQUIREMENT.md), puis
[EXECUTION.md](../../EXECUTION.md). L’ouverture des documents passe par
`python3 outils/ouvrir.py`, qui utilise `open` sur macOS.
