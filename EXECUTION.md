# Exécution — les 18 étapes

Ce guide se lance depuis la racine du dépôt **Intern**, dans un terminal Bash.
Chaque étape répète ses préparations : ne pas supposer qu'un terminal précédent,
une base, une API ou un client est encore disponible. Les étapes se réalisent
dans l'ordre ; si un livrable prérequis manque, sa commande de préparation
est indiquée. Les fichiers livrés se consultent aussi sans relancer les mesures.

## Installation des outils sur une machine neuve

Commencer par [REQUIREMENT.md](REQUIREMENT.md), qui renvoie vers les
prérequis Linux, macOS et Windows. Ce guide reste commun : les différences
d’installation sont isolées, sans dupliquer les 18 étapes.
Les blocs utilisent **Bash** (Windows : Ubuntu sous WSL 2). Les étapes VM
et certaines commandes système restent propres à un hôte Linux x86_64 ;
les limites sont précisées dans les prérequis de chaque système.

Depuis le dossier `Intern`, vérifier l’emplacement puis installer les dépendances :

```bash
pwd
test -f LIVRABLES.md && test -f metier/uv.lock && test -f frontend/package-lock.json
uv sync --project metier --frozen
```

`uv sync --frozen` seul cherche un projet dans le dossier courant : depuis
`Intern`, préciser `--project metier`. L’environnement est `metier/.venv`.
Si un autre environnement Python est actif, lancer `deactivate` (s’il a été
activé dans ce terminal) avant la commande manuelle. Les lanceurs ci-dessous
ignorent cet environnement actif et utilisent celui du métier.

## Règle de démarrage conditionnel

Les scripts ci-dessous ne font pas de `restart`. Un service disponible est
conservé ; un service en cours de démarrage est attendu ; un service arrêté
est démarré. Si un autre programme occupe le port ou si les identifiants sont
incorrects, le lanceur s'arrête avec un diagnostic et garde les données.

Les étapes 3–6 utilisent [outils/demarrer_local.py](outils/demarrer_local.py).
Depuis `Intern`, choisir la couche à démarrer (les couches précédentes sont incluses) :

```bash
python3 outils/demarrer_local.py donnees --database intern_donnees_execution
python3 outils/demarrer_local.py metier
python3 outils/demarrer_local.py presentation
```

Chaque commande se suffit à elle-même pour la couche choisie.
Le lanceur charge `.execution/moteur.env` s’il existe, puis `.execution/local.env`.
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

Pour générer automatiquement la configuration Docker, depuis `Intern` :

```bash
python3 outils/configurer_moteur.py
```

Si les anciens binaires `/tmp` ont disparu, utiliser
`python3 outils/configurer_moteur.py --restaurer --demarrer`.
Le script conserve le stockage et sauvegarde l’ancien fichier.
Voir [REQUIREMENT.md](REQUIREMENT.md)
pour les prérequis rootless et les options.

Pour Docker natif installé ailleurs, définir `DOCKER_BIN` vers son exécutable,
et si nécessaire `DOCKER_HOST` / `DOCKER_CONFIG`, dans chaque terminal.
Ne pas changer le répertoire des volumes d'un moteur déjà installé.
Une configuration explicite du moteur peut être conservée dans
`.execution/moteur.env` (ignoré par Git), sous forme de lignes `export CLE=valeur`.
Les lanceurs des étapes Docker la chargent si elle existe. Pour un moteur rootless
manuel, y définir `DOCKER_BIN`, `DOCKER_HOST`, `DOCKER_CONFIG`,
`DOCKER_ENGINE_BIN`, `DOCKER_ENGINE_RUNTIME` et `DOCKER_ENGINE_DATA` selon
son installation existante. Le répertoire des données doit déjà exister :
un lancement ne crée pas un autre stockage à la place du premier.

Sur ce poste Fedora, la commande système `docker` peut être une émulation
Podman. Les lanceurs `bash outils/executer_etape.sh ...` utilisent Docker Engine
grâce à `.execution/moteur.env` : continuer à utiliser ces lanceurs pour suivre
les étapes. Pour une commande Docker manuelle dans un nouveau terminal,
charger cette même configuration et appeler l'exécutable configuré :

```bash
source .execution/moteur.env
"$DOCKER_BIN" ps
```

Ne pas mélanger ces conteneurs avec ceux affichés par la commande système
`docker` si elle indique « Emulate Docker CLI using podman ».

Les comptes du jeu d'essai utilisent le mot de passe **`Intern-Demo-2026!`** :
`alice@example.test` (candidat), `recruteur_a@example.test` (recruteur),
`recruteur_non_verifie@example.test` (vérification entreprise),
`vide@example.test` (liste vide). L'administration utilise le login `admin`.

## Étape 1 — Analyse

Aucun serveur nécessaire pour lire le livrable. Depuis Intern :
`outils/ouvrir.py` choisit l’outil d’ouverture du système (Linux, macOS ou WSL)
et affiche la cible si aucune ouverture graphique n’est disponible.

```bash
test -f LIVRABLES.md
python3 outils/ouvrir.py analyse/cas_d_usage.pdf
```

Pour générer le PDF si nécessaire, installer les outils Python de [REQUIREMENT.md](REQUIREMENT.md) :

```bash
set -e
export PATH="$HOME/.local/bin:$PATH"
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
python3 outils/ouvrir.py maquette/ecran_zero.jpg
python3 - <<'PY'
from pathlib import Path
import re, subprocess, sys
text = Path("maquette/figma_link.txt").read_text()
url = re.search(r"https://www\.figma\.com/proto/[^\s]+", text)
if not url: raise SystemExit("Lien prototype absent")
subprocess.run([sys.executable, "outils/ouvrir.py", url.group()], check=True)
PY
```

Parcourir les trois acteurs dans Figma. La présence du lien ne prouve pas
que les droits lecture ni l’approbation pédagogique sont acquis.

## Étape 3 — Couche données

Prérequis : installer Python, uv, PostgreSQL client et Docker Engine selon [REQUIREMENT.md](REQUIREMENT.md). Aucun métier ni client React nécessaire. Depuis Intern :

```bash
python3 outils/demarrer_local.py donnees --database intern_donnees_execution
```

La base `intern_donnees_execution` est réservée à cette étape : les inscriptions
et essais des étapes 5–6 ne modifient pas ses effectifs attendus. Le lanceur
affiche les contrôles SQL et les 13 consultations. Pour ouvrir
la base de cette étape dans ce même terminal :

```bash
python3 outils/demarrer_local.py sql --database intern_donnees_execution
```

Dans `psql` : `\dt`, puis `SELECT title FROM jobboard_offer;`, puis `\q`.
La commande reprend `.execution/local.env` et le nom indiqué par `--database`.
Elle ouvre seulement le client SQL ; elle ne démarre ni ne modifie la base.
En cas d’échec, relancer la préparation `donnees` ci-dessus et lire le diagnostic :
un refus de connexion, un mot de passe rejeté et une base absente sont des problèmes distincts.

## Étape 4 — Couche métier

Prérequis : installer Python, uv, PostgreSQL client et Docker Engine selon [REQUIREMENT.md](REQUIREMENT.md). Même sans service lancé auparavant, depuis Intern :


```bash
python3 outils/demarrer_local.py metier
```

```bash
curl --fail http://127.0.0.1:8000/health/ready/
curl --fail http://127.0.0.1:8000/api/v1/auth/csrf/
python3 outils/ouvrir.py http://127.0.0.1:8000/admin/
```

Le fichier `metier/api.http` contient les requêtes HTTP commentées.
API : `http://127.0.0.1:8000/api/v1/`. Administration : login `admin`,
mot de passe du jeu d’essai. React n’est pas nécessaire à cette étape.

## Étape 5 — Couche présentation

Prérequis : installer Python, uv, PostgreSQL client, Docker Engine, Node et npm
selon [REQUIREMENT.md](REQUIREMENT.md). Depuis Intern, le bloc complet démarre **base, métier
et présentation**, sans dépendre d’un terminal de l’étape 4 :

```bash
python3 outils/demarrer_local.py presentation
```

```bash
curl --fail http://127.0.0.1:8000/health/ready/
curl --fail http://127.0.0.1:5173/api/v1/auth/csrf/
python3 outils/ouvrir.py http://127.0.0.1:5173/login
```

Connexion candidat : `alice@example.test` ; recruteur :
`recruteur_a@example.test` ; mot de passe `Intern-Demo-2026!`.
L’administration reste sur `http://127.0.0.1:8000/admin/`.

Pour prendre les captures de tous les écrans principaux sur ces services réels
(installation des bibliothèques système du navigateur si elles manquent) :

```bash
set -e
export PATH="$HOME/.local/bin:$PATH"
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
selon [REQUIREMENT.md](REQUIREMENT.md). Une recette écrit dans sa base : utiliser une **base
dédiée à la recette**. Le bloc prépare les trois couches, même si rien ne tourne :

```bash
python3 outils/demarrer_local.py presentation --database intern_recette_execution \
  --api-port 8001 --frontend-port 5175
```

```bash
set -e
export PATH="$HOME/.local/bin:$PATH"
cd frontend
npx playwright install chrome
cd ..
RECETTE_URL=http://127.0.0.1:5175 RECETTE_ADMIN_URL=http://127.0.0.1:8001 \
  RECETTE_PASSWORD='Intern-Demo-2026!' node tests/recette_navigateur.mjs
node tests/generer_cahier.mjs
python3 outils/ouvrir.py tests/cahier_de_tests.pdf
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
bash outils/preparer_vm.sh
VBoxManage list vms
```

Si une VM apparaît `<inaccessible>`, vérifier d'abord sa configuration et ses
disques. Pour récupérer un fichier `.vbox` absent depuis sa copie `.vbox-prev`,
sans supprimer les disques :

```bash
python3 outils/reinitialiser_vm.py
```

Pour reprendre volontairement à l'étape 7 sur les trois snapshots `base propre`,
avec les VM arrêtées :

```bash
python3 outils/reinitialiser_vm.py --base-propre
bash outils/preparer_vm.sh
VBoxManage list vms
```

Cette commande conserve les états actuels et les anciens snapshots sous des noms
`archive-*`, puis restaure les disques et les paramètres des snapshots initiaux.
Les changements applicatifs postérieurs quittent donc l'état actif, mais restent
dans les archives. Elle vérifie les fichiers de disque et les snapshots avant
de commencer et applique `paravirtprovider minimal`, nécessaire sur l'hôte testé.
`VM_WORK` ou `--vm-work CHEMIN` permet de choisir un autre stockage.
Elle n'efface ni les exports OVA ni les résultats de mesure.

Le script [outils/preparer_vm.sh](outils/preparer_vm.sh) regroupe le téléchargement
vérifié, la préparation du modèle, les clones, leurs identités et leurs snapshots
`base propre`. Si les trois VM existent, il les conserve sans les modifier ni
les redémarrer. VirtualBox et les outils indiqués restent à installer au préalable.
Le répertoire est choisi via `VM_WORK`, puis `../.local-vms` s’il contient les accès,
sinon `$HOME/VMs-intern`. Pour un autre emplacement, exporter `VM_WORK` dans
le terminal avant la commande ; les étapes suivantes reprendront cette valeur.

Le modèle existant n’est pas recréé. En cas d’installation interrompue,
inspecter son état : sa simple présence ne prouve pas sa préparation.
La procédure détaillée est dans [deploiement/scripts/PROCEDURE.md](deploiement/scripts/PROCEDURE.md).
Pour une capture de la liste : ouvrir VirtualBox et afficher les trois VM.

## Commandes des étapes 8 à 18

Chaque étape utilise le même lanceur depuis `Intern` :
`bash outils/executer_etape.sh NUMERO [ACTION]`.
Il regroupe les préparations et les contrôles de l’étape. Les différences
entre démarrage, consultation et nouvelle mesure sont précisées ci-dessous.
Pour retrouver toutes les actions :

```bash
bash outils/executer_etape.sh --help
```

Les implémentations sont dans [outils/etapes](outils/etapes).

## Étape 8 — Réseau et adressage

Prérequis : VirtualBox, Python, OpenSSH et `rg`, selon [REQUIREMENT.md](REQUIREMENT.md).
Depuis Intern, préparer les VM manquantes et leur réseau :

```bash
bash outils/executer_etape.sh 8
```

Le script réutilise les machines et le réseau existants. Pour rejouer la
vérification réseau (elle démarre les VM, puis les éteint et retire l’accès
SSH temporaire à la fin) :

```bash
bash outils/executer_etape.sh 8 verifier
```

Pendant les arrêts, les erreurs temporaires de session VirtualBox sont
réessayées dans un délai borné. L’attente SSH commence par le proxy ; chaque
tentative est limitée et son dernier diagnostic est conservé dans
`.execution/ssh-NOM_VM.log`. Un délai SSH expiré fait échouer la commande :
les nouvelles preuves réseau ne sont écrites qu’après la vérification complète.
Si une VM reste indisponible, consulter sa console VirtualBox et le journal
SSH indiqué avant de relancer le test.
Une expiration SSH pendant l'échange de bannière, avant authentification, est
réessayée au plus trois fois. Une erreur d'authentification ou une commande
distante déjà commencée n'est pas rejouée automatiquement.

Preuves et plan : [deploiement/reseau/README.md](deploiement/reseau/README.md).
Résultat du contrôle des commandes :
[validation-commandes-etape8.md](deploiement/docs/validation-commandes-etape8.md).

## Étape 9 — Déployer les couches

Prérequis : outils VM, uv et Node/npm. Depuis Intern :

```bash
bash outils/executer_etape.sh 9
```

La commande prépare les VM et le réseau s’ils manquent, démarre les VM arrêtées,
attend SSH, puis installe les couches absentes. Elle conserve les bases et les
services disponibles. La première installation peut redémarrer la VM concernée
pour appliquer sa configuration. Le proxy est vérifié avant l’ouverture du navigateur.
Les applications Netplan disposent de 120 secondes ; les vérifications SSH
simples gardent leur délai de 30 secondes.
Application : `http://127.0.0.1:8080/login` ; administration :
`http://127.0.0.1:8080/admin/`. Comptes fictifs : voir étape 5.

## Étape 10 — Vérifier, mesurer et exporter

Pour lire les preuves livrées, sans démarrer de VM :

```bash
bash outils/executer_etape.sh 10
```

Pour préparer/démarrer l’application VM et ouvrir son interface :

```bash
bash outils/executer_etape.sh 10 demarrer
```

Pour effectuer de nouvelles mesures et exporter les trois OVA :

```bash
bash outils/executer_etape.sh 10 mesurer
```

Le mode `mesurer` prépare les couches si nécessaire, sauvegarde les rapports
précédents dans `.execution/sauvegardes/`, arrête et redémarre les VM pendant
les essais, puis les laisse éteintes pour les exports. Il contrôle les empreintes
`SHA256SUMS`. Les archives sont dans `$VM_WORK/exports-etape10` : si ce dossier
existe déjà, le script refuse une nouvelle mesure avant toute modification.
Conserver ou déplacer volontairement ces exports avant de recommencer.
Les rapports canoniques sont remplacés après sauvegarde.

### Arrêter les VM avant de passer à Docker

Depuis Intern :

```bash
bash outils/executer_etape.sh 10 arreter
VBoxManage list runningvms
```

La commande demande l'arrêt propre des trois VM par ACPI, puis attend leur
extinction (jusqu'à 120 secondes par VM). Une VM déjà arrêtée est conservée.
Si l'arrêt n'aboutit pas, la commande échoue sans forcer la coupure.
Les disques et les snapshots sont conservés. Cela libère notamment le port
8080 du proxy VM pour le proxy Docker de l'étape 13.

Pour revenir ensuite au déploiement VM :

```bash
bash outils/executer_etape.sh 10 demarrer
```

## Étape 11 — Couche données Docker

Prérequis : Python et Docker Engine/Compose selon [REQUIREMENT.md](REQUIREMENT.md).
Depuis Intern :

```bash
bash outils/executer_etape.sh 11
```

La commande charge la configuration du moteur, démarre les services manquants,
puis contrôle le nombre d’offres en SQL. Les secrets sont créés seulement
s’ils manquent ; un volume existant est conservé, sans réimport SQL.
Aucun port PostgreSQL n’est publié. Le test de persistance avec recréation
volontaire reste décrit dans [docker/PROCEDURE.md](docker/PROCEDURE.md).

## Étape 12 — Image métier Docker

Depuis Intern, avec les mêmes prérequis Docker :

```bash
bash outils/executer_etape.sh 12
```

La commande prépare la base et l’image métier si elles manquent, attend leur
santé, affiche la taille de l’image et contrôle le HTTP depuis le conteneur.
Le métier reste accessible uniquement sur son réseau Docker.
Après une modification du code, reconstruire volontairement l’image : le
lancement conditionnel conserve un tag déjà présent.

## Étape 13 — Proxy et composition Docker

Depuis Intern :

```bash
bash outils/executer_etape.sh 13
```

La commande prépare les images absentes, démarre les trois services manquants,
vérifie le proxy et ouvre `http://127.0.0.1:8080/login`.
Si le port 8080 est utilisé par les VM, choisir le déploiement à présenter
et arrêter explicitement l’autre ; le script n’arrête aucun service concurrent.
Les volumes, secrets et services déjà actifs sont conservés.

## Étape 14 — Vérifier et comparer Docker / VM

Pour ouvrir le compte rendu livré, sans démarrer de service :

```bash
bash outils/executer_etape.sh 14
```

Pour démarrer le déploiement Docker et ouvrir l’application :

```bash
bash outils/executer_etape.sh 14 demarrer
```

Pour refaire les mesures Docker et régénérer le compte rendu :

```bash
bash outils/executer_etape.sh 14 mesurer
```

Le mode `mesurer` utilise par défaut le projet dédié `intern-verification`.
Il charge le même moteur que l'étape 13 et arrête automatiquement le projet
`intern-docker` si celui-ci occupe le port 8080, sans supprimer ses données.
Le projet de vérification devient alors le déploiement actif. Un autre projet
occupant ce port est signalé avant le démarrage et doit être arrêté explicitement.
Si les VM tournent encore, les arrêter avec `bash outils/executer_etape.sh 10 arreter`.
Il faut disposer des mesures VM de l’étape 10.
Le script détecte le PID du daemon rootless configuré ou du service
Docker système ; `DOCKER_PIDFILE` permet de fournir un autre fichier PID.
Pour rootless, le vérificateur utilise les espaces utilisateur et de montage
du daemon via `nsenter`, comme dans [docker/PROCEDURE.md](docker/PROCEDURE.md).

Les essais arrêtent/recréent les conteneurs du projet choisi et conservent
leur volume. Les rapports précédents sont sauvegardés dans
`.execution/sauvegardes/`, puis remplacés. Les dépendances PDF sont installées
dans un environnement documentaire dédié. Le rapport s’ouvre à la fin.

## Étape 15 — Plan JMeter

Prérequis : Python, Docker Engine/Compose, Java, curl et un bureau graphique
pour la GUI. Préparer les services de mesure sur 8081, JMeter et les comptes :

```bash
bash outils/executer_etape.sh 15
```

Pour enchaîner les deux essais GUI puis leurs exécutions CLI :

```bash
bash outils/executer_etape.sh 15 tout
```

Dans chaque fenêtre JMeter, lancer une itération puis fermer la fenêtre pour
continuer. La première utilise le mot de passe correct ; la seconde utilise
`incorrect`. Conserver une capture de chaque résultat GUI.
Une exécution CLI ne remplace pas ces captures.

Pour lancer uniquement les deux essais CLI, sans bureau graphique :

```bash
bash outils/executer_etape.sh 15 cli
```

Chaque action prépare ses dépendances applicatives. Les actions `gui` et
`gui-echec` permettent aussi d’ouvrir un seul cas. Les nouveaux résultats CLI
sont dans un dossier daté `mesure/resultats/essai-execution15-*`, affiché à la fin.
`MESURE15_OUTPUT` permet de choisir un dossier neuf. Le projet `intern-mesure`
a un volume distinct ; la préparation des comptes conserve l’ancien CSV en
sauvegarde s’il change et refuse une identité incompatible.

## Étape 16 — Étalonnage

Les nouveaux essais utilisent la [configuration de performance](mesure/PERFORMANCE.md) :
limitation des connexions désactivée uniquement sur les services de mesure.
L'image dédiée est reconstruite lors de la préparation. Le déploiement normal
conserve sa protection.

Pour lire le rapport livré, sans lancer de charge :

```bash
bash outils/executer_etape.sh 16
```

Pour préparer le déploiement de mesure, effectuer les quatre essais et produire
un nouveau rapport :

```bash
bash outils/executer_etape.sh 16 mesurer
```

Avant la charge, le script vérifie qu’aucune VM ni aucun conteneur d’un autre
projet ne tourne. Arrêter explicitement les déploiements signalés, puis relancer.
Il exécute les essais statiques à 1 et 20 utilisateurs, puis deux contrôles
applicatifs à 10 utilisateurs séparés par 30 secondes de repos.

Les résultats, configurations, empreintes et `rapport.md` restent ensemble dans
un nouveau dossier `mesure/resultats/etape16-*`. Le chemin est affiché à la fin ;
`MESURE16_OUTPUT` permet de choisir un autre dossier neuf sous `mesure/`.
Le script refuse de réutiliser une sortie existante. Le rapport historique
[mesure/ETAPE16.md](mesure/ETAPE16.md) et ses preuves restent conservés.
Si la répétabilité échoue, stabiliser l’hôte avant une nouvelle campagne.

## Étape 17 — Campagnes

Pour contrôler les preuves livrées, sans démarrer de service ni lancer de charge :

```bash
bash outils/executer_etape.sh 17
```

Pour préparer les VM, le moteur, les images, JMeter et la configuration privée :

```bash
bash outils/executer_etape.sh 17 preparer
```

Vérifier le chemin de configuration affiché et le projet de référence avant le
lancement. Par défaut : runtime `../.execution-campagnes/active`, sortie
`mesure/resultats/campagne`, projet de référence `intern-docker`.
Les variables `MESURE_RUNTIME`, `MESURE_OUTPUT`, `MESURE_REFERENCE_PROJECT` et
`VM_WORK` permettent de choisir leurs valeurs. Une configuration existante
est conservée ; des paramètres différents sont refusés sans modifier le fichier.
Une préparation ou un lancement réussi mémorise la campagne dans
`.execution/campagne-active.json`. Les commandes `17 statut`, `17 arreter` et
`17 lancer` la retrouvent dans un nouveau terminal. Les variables explicitement
fournies restent prioritaires. Sans sélection mémorisée, les valeurs par défaut
ci-dessus sont utilisées.

Pour lancer la campagne en arrière-plan (la préparation est également incluse) :

```bash
bash outils/executer_etape.sh 17 lancer
```

La préparation attend SSH pendant 240 s par VM, en commençant par le proxy.
Si le démarrage à froid est plus lent sur l’hôte, la limite est configurable :

```bash
VM_SSH_WAIT_SECONDS=600 bash outils/executer_etape.sh 17 lancer
```

Chaque tentative expirée termine ses processus de connexion et conserve son
diagnostic dans `.execution/ssh-vm-proxy.log` (ou le fichier de la VM concernée).
Un échec à ce stade précède le lancement du contrôleur de campagne.
Éviter les recherches de fichiers sur les données brutes Docker et les disques
VM pendant les essais. À la racine `virtualisation`, `.ignore` et les réglages
VS Code `.vscode/settings.json` excluent `.runtime-*` et `.local-vms` des recherches.

Pour consulter sa progression ou demander un arrêt propre :

```bash
bash outils/executer_etape.sh 17 statut
```

```bash
bash outils/executer_etape.sh 17 arreter
```

Laisser l’hôte allumé : 45 min 20 s de paliers, plus des repos dynamiques
d'au moins 30 s, la préparation et les transitions. Le détail des seuils et des
limites est dans [la configuration de performance](mesure/PERFORMANCE.md).
Réétalonner à l'étape 16 avant de lancer ce nouveau protocole.
Le pilote alterne volontairement les déploiements, conserve leurs bases initiales
et rétablit le projet de référence. L’arrêt demandé attend cette restauration.
Le script refuse une campagne déjà active ou complète ; pour une nouvelle
campagne, utiliser `17 nouvelle`. Le projet de référence doit
correspondre au déploiement réel à restaurer.

Chaque nouveau runtime reçoit un projet Docker de mesure distinct ; les anciens
conteneurs et volumes ne sont pas supprimés. Un runtime ancien avec son snapshot
conserve son projet pour la reprise. Le lancement contrôle les conflits et
l’accès aux VM avant de passer en arrière-plan. Les conteneurs `intern-mesure`
encore actifs après l’étalonnage sont arrêtés pendant la campagne puis redémarrés
s’ils étaient actifs auparavant. Un autre projet occupant 8081 provoque un refus
explicite. Ne pas lancer deux campagnes simultanément : elles partagent les VM
et le port 8081.

`statut` consulte uniquement les fichiers et le processus. Il affiche le chemin
du journal et, en cas d’échec, ses dernières lignes ainsi que les erreurs de
restauration. Pour suivre le journal depuis Intern :

```bash
tail -f ../.execution-campagnes/active/controller.log
```

Avec un runtime personnalisé, remplacer ce chemin par `$MESURE_RUNTIME/controller.log`.
Après un échec avant le premier palier, relancer `17 lancer` avec la même
configuration. Après un repos refusé, consulter `repos/.../diagnostic.json` et
corriger la cause. Pour préparer une nouvelle campagne après une campagne
terminée ou interrompue :

```bash
bash outils/executer_etape.sh 17 nouvelle
bash outils/executer_etape.sh 17 lancer
```

`nouvelle` refuse un contrôleur actif, déplace les anciens fichiers privés et
résultats dans leurs sous-dossiers `archives/` avec la même date UTC, puis prépare
les dossiers standards. Cette action ne lance pas JMeter. Aucun nom de dossier
lié à une correction n’est nécessaire. La sélection reste mémorisée pour
`17 statut` dans tous les terminaux.
Une erreur VirtualBox persistante doit être résolue avant le
lancement ; les refus temporaires de verrouillage sont retentés pendant 10 s.
Le contrôleur restaure seulement les ressources qu’il a utilisées et tente de
rétablir Docker même si la restauration des VM échoue. Un palier partiellement
écrit reste conservé pour examen et bloque sa reprise automatique.
Les redirections NAT équivalentes sont réutilisées quel que soit leur nom
(notamment `ssh-verification` sur 2221). Le nettoyage retire uniquement les
règles ajoutées par la campagne. Les VM sont arrêtées proprement par ACPI,
indépendamment de SSH et du proxy ; aucun arrêt forcé n’est effectué.
Si un invité démarre encore, la demande ACPI est répétée toutes les 10 s pendant
au plus 120 s. Une tentative SSH expirée est retentée dans la limite globale de
240 s par VM.

La commande sans action vérifie toujours `mesure/resultats/etape17` ; elle ne
valide pas automatiquement une nouvelle sortie. Rattacher et vérifier les
nouvelles preuves avant de les présenter. Détails : [mesure/ETAPE17.md](mesure/ETAPE17.md).

## Étape 18 — Analyse des mesures

Prérequis : Python et pip/venv. Depuis Intern :

```bash
bash outils/executer_etape.sh 18
```

La commande prépare l’environnement d’analyse, vérifie les preuves canoniques
de l’étape 17, recalcule les statistiques, génère les courbes et le PDF, puis ouvre
[mesure/docs/rapport-charge.pdf](mesure/docs/rapport-charge.pdf).
Aucune VM, API, base ou conteneur n’est démarré pour cette analyse.
Elle utilise les fichiers livrés dans `mesure/resultats/etape17` ; elle ne
sélectionne pas automatiquement une nouvelle campagne.

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

Les lanceurs sont vérifiés par des tests ciblés et des contrôles de syntaxe
Bash. Les parcours du lanceur sont testés avec VirtualBox, Docker et JMeter
simulés dans un projet temporaire. Ces contrôles ne relancent ni VM, ni exports,
ni campagne de charge réelle. Pour relancer les tests du lanceur depuis Intern :

```bash
python3 -m unittest discover -s outils -p 'test_*.py' -v
```
Les installations
macOS/Windows et une installation vierge ne sont pas validées par ces contrôles.
Les résultats ci-dessous proviennent de la vérification initiale du guide.


Les blocs DEV et les captures sont vérifiés sur la machine de travail avec une
base dédiée. Les 34 contrôles SQL passent dans la base réservée à l’étape 3 ;
les 15 parcours de recette passent sur la base et les ports de l’étape 6.
Les trois services Docker de cours sont également lancés sur un
projet dédié ; un second lancement conserve leurs IDs et dates de démarrage. Cette vérification n’est pas une installation de tous les outils
sur une machine vierge. Les commandes VM et JMeter reprennent
les outils et procédures du dépôt ; les nouvelles campagnes, installations
système, exports et mesures ne sont pas relancés pour vérifier ce document.
