# Conteneurisation — trois couches

## Prérequis

La procédure de [déploiement des trois VM](../deploiement/DEPLOIEMENT.md),
la [configuration externalisée](../metier/.env.example) et les
[mesures de référence](../deploiement/docs/mesures.md) sont disponibles.
Les rapports des étapes 1 à 10 sont indexés dans [les livrables](../LIVRABLES.md).
Les mesures VM comprennent trois séries réelles ; le temps humain de mise en
place n'a pas été chronométré.

Installer Docker Engine et le plugin Docker Compose. Vérifier que le serveur
est bien Docker Engine, puis exécuter toutes les commandes depuis la racine
d'Intern :

```sh
docker version
docker info
docker compose version
cp docker/.env.example docker/.env
chmod 600 docker/.env
```

Renseigner un mot de passe local dans `docker/.env`, sans versionner ce fichier.
Renseigner aussi `DJANGO_SECRET_KEY` avec une valeur générée localement :
`python3 -c 'import secrets; print(secrets.token_urlsafe(64))'`.
Si le fichier `.env` existe déjà, y ajouter cette clé sans remplacer ses valeurs.
Les noms `POSTGRES_DB`, `POSTGRES_USER` et `POSTGRES_PASSWORD` sont ceux de
l'application. Le service métier utilisera ensuite `POSTGRES_HOST=donnees`
et `POSTGRES_PORT=5432`.

## Déclaration et initialisation

[compose.yaml](compose.yaml) déclare les services données, métier et proxy.
L'image officielle `postgres:16.15-bookworm` utilise la même version PostgreSQL
que les mesures VM. Elle reconnaît les commandes `\restrict` des exports SQL.
La version est explicite ; le digest réellement téléchargé sera relevé lors
de l'exécution pour identifier également la révision de l'image.

Les scripts [schema.sql](../donnees/schema.sql) et [data.sql](../donnees/data.sql)
sont montés en lecture seule, sans copie, et exécutés dans cet ordre sur un
volume vide. Le volume nommé `pgdata` est monté à `/var/lib/postgresql/data`.
Le service n'a aucun port publié et appartient uniquement au réseau `interne`.
La sonde TCP évite de confondre le serveur temporaire d'initialisation avec
le serveur final prêt à accepter les connexions des autres conteneurs.

L'image crée le rôle donné par `POSTGRES_USER` avec des droits de
superutilisateur. Ce choix reprend l'initialisation standard pour la
démonstration isolée ; les droits diffèrent du rôle restreint installé en VM.

```sh
docker compose --env-file docker/.env -f docker/compose.yaml config --quiet
docker compose --env-file docker/.env -f docker/compose.yaml up -d --wait --wait-timeout 180 donnees
docker compose --env-file docker/.env -f docker/compose.yaml ps
docker compose --env-file docker/.env -f docker/compose.yaml logs donnees
```

Si le démarrage échoue, lire les journaux avant toute reprise. Un import SQL
échoué peut laisser un volume partiellement initialisé : une relance ne rejoue
pas les scripts. Ne pas réinitialiser un volume contenant des données à conserver.

## Vérifier le peuplement et conserver les preuves

```sh
mkdir -p docker/docs
sh docker/verifier-donnees.sh > docker/docs/peuplement-etape11.txt
docker compose --env-file docker/.env -f docker/compose.yaml ps > docker/docs/services-etape11.txt
docker image inspect postgres:16.15-bookworm --format '{{json .RepoDigests}}' > docker/docs/image-etape11.txt
docker inspect "$(docker compose --env-file docker/.env -f docker/compose.yaml ps -q donnees)" --format 'ports={{json .HostConfig.PortBindings}} reseaux={{json .NetworkSettings.Networks}} volumes={{json .Mounts}}' > docker/docs/isolation-etape11.txt
```

Le vérificateur doit confirmer huit comptes, trois entreprises, quatre stages,
deux candidatures et le compte `attente` inactif. Il exécute aussi les
[consultations SQL existantes](../donnees/requetes.sql).
L'inspection doit montrer aucun port publié, un seul réseau
`intern-docker_interne` et le volume `intern-docker_pgdata`.
La joignabilité depuis le métier et l'interdiction depuis le proxy seront
testées une fois ces services ajoutés ; la déclaration seule ne les prouve pas.

## Vérifier la persistance

Sur le volume de démonstration, après la première vérification :

```sh
docker compose --env-file docker/.env -f docker/compose.yaml down
docker volume inspect intern-docker_pgdata
docker compose --env-file docker/.env -f docker/compose.yaml up -d --wait --wait-timeout 180 donnees
sh docker/verifier-donnees.sh > docker/docs/persistance-etape11.txt
docker compose --env-file docker/.env -f docker/compose.yaml logs donnees > docker/docs/redemarrage-etape11.txt
```

`down` supprime les conteneurs et le réseau, mais conserve le volume.
Le nouveau conteneur doit retrouver le même jeu sans rejouer les imports ;
le journal doit indiquer que l'initialisation a été ignorée.

Pour rejouer les scripts sur une démonstration jetable uniquement, la commande
suivante **efface les données** du volume du projet :

```sh
docker compose --env-file docker/.env -f docker/compose.yaml down --volumes
```

Cette commande n'est pas nécessaire pour vérifier la persistance.
Changer les variables de base ou de mot de passe après initialisation ne
modifie pas les comptes déjà enregistrés dans le volume.

Référence : [documentation de l'image officielle PostgreSQL](https://hub.docker.com/_/postgres).

## Étape 12 — Construire l'image métier

[metier.Dockerfile](metier.Dockerfile) utilise `python:3.12.15-slim-bookworm`.
Python reste dans la même version mineure que les VM, avec une version corrective
différente. Le constructeur installe Git et `uv==0.11.29`, puis les dépendances
de `metier/uv.lock`, avant de copier le code. L'image finale ne reçoit que
l'environnement Python, le code et les fichiers nécessaires à la démonstration ;
Git, uv et leurs caches restent hors de cette image.

Le fichier [d'exclusion](.dockerignore) est la source unique ; le lien
`../.dockerignore` le rend actif à la racine du contexte de construction. Il exclut les
environnements virtuels, secrets, historique Git et artefacts temporaires.
Le lien `docker/Dockerfile` pointe vers `metier.Dockerfile` pour conserver une
seule définition utilisable par les configurations existantes.

Les fichiers partagés `jeu_fictif.py`, `verifier.py` et `cv_fictif.pdf` sont copiés
depuis leurs sources existantes. Les trois CV de démonstration sont placés dans
les chemins privés enregistrés en base, avec accès réservé au compte `intern`.
Le code et les dépendances restent détenus par root ; seuls le stockage privé
et les statiques sont accessibles en écriture au processus applicatif.

Le [script de démarrage](demarrer-metier.sh) vérifie Django et l'historique des
migrations, collecte les statiques puis lance Gunicorn. Il ne recrée ni le
schéma ni le jeu fictif. Une migration absente fait échouer le démarrage,
pour éviter de modifier silencieusement la base restaurée.
Gunicorn écoute sur `0.0.0.0:8000`, avec deux workers et le même timeout de
30 secondes que le déploiement VM. Aucun port n'est publié.
`metier` rejoint `frontal` et `interne` et attend la santé de `donnees`.
Sa sonde `/health/ready/` exécute une véritable requête SQL.

La configuration HTTP utilise explicitement `DJANGO_DEBUG=true`, comme la
démonstration VM. Aucun worker d'import ou d'envoi externe n'est lancé.
Les fichiers privés ajoutés pendant une session ne persistent pas à la
recréation du métier ; les CV fictifs inclus dans l'image sont restaurés.

### Construire, démarrer et vérifier

Après renseignement de `docker/.env`, depuis la racine d'Intern :

```sh
docker compose --env-file docker/.env -f docker/compose.yaml config --quiet
docker compose --env-file docker/.env -f docker/compose.yaml build metier
docker compose --env-file docker/.env -f docker/compose.yaml up -d --wait --wait-timeout 180 metier
docker compose --env-file docker/.env -f docker/compose.yaml logs metier
sh docker/verifier-metier.sh > docker/docs/connexion-etape12.txt
docker compose --env-file docker/.env -f docker/compose.yaml ps > docker/docs/services-etape12.txt
docker inspect "$(docker compose --env-file docker/.env -f docker/compose.yaml ps -q metier)" --format 'ports={{json .HostConfig.PortBindings}} reseaux={{json .NetworkSettings.Networks}}' > docker/docs/isolation-etape12.txt
docker image inspect intern-metier:etape12 --format 'id={{.Id}} taille_exacte_octets={{.Size}}' > docker/docs/taille-image-etape12.txt
cat docker/docs/taille-image-etape12.txt
```

Résultats attendus : résolution de `donnees`, HTTP 200 avec `status: ok`,
**34 vérifications SQL réussies depuis le métier**, deux réseaux pour le métier
et aucun port publié. Le champ `taille_exacte_octets` affiche la valeur entière
mesurée par Docker pour l'image non compressée, sans arrondi. Reporter cette
valeur et l'identifiant de l'image dans le rapport de l'étape 12, avec la date
de mesure. Une conversion en Mio (octets / 1 048 576) peut compléter cette
valeur, mais ne remplace pas le nombre exact d'octets.
Cette mesure ne représente pas la place totale de toutes les couches partagées
sur disque.
L'accès navigateur attend le proxy de l'étape 13.

### Taille et contenu effectivement vérifiés

Le 14 octobre 2026, la recette actuelle a été construite avec Podman :
**388 668 114 octets**, soit **388,668114 Mo** non compressés.
La réduction par rapport à l'image locale antérieure est de **62,73 %**.
Git, uv et le cache uv sont absents de l'image finale ; Gunicorn démarre
et répond sur `/health/live/`. Les sources copiées ne contiennent pas les
fichiers locaux exclus. Le [rapport](docs/etape12.md) et la
[preuve](docs/verification-image-etape12.txt) détaillent ces contrôles.
La construction et la connexion PostgreSQL avec Docker Engine restent
à valider séparément.

Références : [image officielle Python](https://hub.docker.com/_/python),
[installation uv et cache Docker](https://docs.astral.sh/uv/guides/integration/docker/).

## Étape 13 — Proxy et composition

Le [proxy](proxy.Dockerfile) est construit en trois phases : collecte des
statiques depuis l'image métier, build React avec Node 22.23.3, puis copie
des seuls fichiers nécessaires dans Nginx 1.28.0 Alpine. Les outils Python
et Node ne sont pas copiés dans l'image finale du proxy.

La [configuration Nginx](proxy.conf) sert le client et les statiques de
l'administration. Elle transmet `/api/`, `/admin/` et `/health/` à
`http://metier:8000`, en conservant le Host et le protocole pour les sessions
et le CSRF. Le client utilise le préfixe relatif `/api/v1`.

| Service | Réseaux | Port publié sur l'hôte |
| --- | --- | --- |
| proxy | frontal | `127.0.0.1:8080` vers `80` |
| metier | frontal, interne | Aucun |
| donnees | interne | Aucun |

`pgdata` reste le seul volume nommé. Les statiques sont incorporés dans
l'image du proxy ; les sources SQL sont les seuls montages de fichiers.
Le métier attend la santé de PostgreSQL et le proxy attend celle du métier.
La sonde du proxy consulte `/health/ready/` à travers Nginx et Django jusqu'à
la base, ce qui vérifie la disponibilité des trois couches.

### Une commande pour chaque opération

Renseigner d'abord `docker/.env` comme indiqué dans les prérequis. Depuis
la racine d'Intern :

```sh
# Construction dans l'ordre métier puis proxy, et démarrage des trois services.
sh docker/demarrer.sh up

# Arrêt et suppression des conteneurs ; le volume de données est conservé.
sh docker/demarrer.sh down

# Recréation des conteneurs depuis les images déjà construites, volume conservé.
sh docker/demarrer.sh restart

# État des trois services.
sh docker/demarrer.sh ps
```

Le script utilise Docker Compose. Les deux constructions sont séquentielles
car la collecte des statiques du proxy utilise l'image métier construite.
Une fois les images disponibles, le démarrage direct est également possible :

```sh
docker compose --env-file docker/.env -f docker/compose.yaml up -d --no-build --wait --wait-timeout 180
```

Le script de démarrage métier est l'`ENTRYPOINT` de son image et Gunicorn
est son `CMD`. La composition conserve ces deux éléments : elle ne remplace
pas l'`ENTRYPOINT` en perdant la commande de lancement.

Ouvrir **http://127.0.0.1:8080/login** et contrôler :

```sh
curl --fail http://127.0.0.1:8080/health/ready/
docker compose --env-file docker/.env -f docker/compose.yaml exec -T proxy nginx -t
sh docker/verifier-metier.sh
```

### Recette navigateur et capture

La recette existante est réutilisée avec un dossier de sortie distinct des
preuves VM. Les fichiers sont générés par le navigateur réel.
Définir `RECETTE_PASSWORD` avec le mot de passe fictif documenté dans
`donnees/README.md`, puis :

```sh
mkdir -p docker/docs
RECETTE_URL=http://127.0.0.1:8080 RECETTE_OUTPUT_DIR=docker/docs RECETTE_PREFIX=etape13 node deploiement/scripts/recette_etape9.mjs
```

Pour la capture des services, afficher `sh docker/demarrer.sh ps` dans un
terminal et capturer cette fenêtre après que les trois services sont sains.
Le [rapport initial](docs/etape13.md) décrit les essais Podman.
L'[étape 14](docs/etape14.md) complète ces preuves sur Docker Engine natif.

La composition rend explicites les noms des services, les dépendances,
les réseaux et les montages. La procédure VM comporte les installations,
les configurations système, les copies et les redémarrages de chaque machine.
Les deux procédures restent disponibles pour la comparaison ultérieure.

## Étape 14 — Vérification et comparaison sur Docker Engine

La campagne du 14 octobre a été exécutée avec **Docker Engine 28.3.3 rootless
et Docker Compose 2.39.4**, sur Linux, avec VPNKit et fuse-overlayfs. Un moteur
temporaire isolé a permis ces essais sans remplacer le programme Docker qui
délègue à Podman sur le poste. Les images construites précédemment sont importées
avec leurs identifiants vérifiés. Le client doit pointer vers ce véritable
Docker Engine : vérifier les sections client et serveur de `docker version`.
Les résultats précédents Podman restent des preuves distinctes.

### Reproduire les mesures

Choisir un projet de démonstration isolé, libérer son port 8080 et préparer
un fichier d'environnement local. Démarrer ses trois services et attendre
leur santé. Les variables suivantes doivent désigner le client Docker natif,
le fichier d'environnement et le PID du daemon de la session mesurée :

```sh
"$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml -p intern-verification up -d --no-build --wait --wait-timeout 180
python3 docker/verifier-etape14.py \
  --docker "$DOCKER_BIN" --env-file "$DOCKER_ENV_FILE" \
  --project intern-verification --engine-pidfile "$DOCKER_PIDFILE"
```

Le script arrête et relance seulement les conteneurs du projet choisi.
Il conserve le volume, refuse une matrice inattendue, confirme les quatre
offres fictives, puis effectue trois séries avec trente secondes au repos
et dix consultations par série. Le seuil de démarrage est le premier catalogue
HTTP 200, pas la fin d'une attente de santé du proxy. Le cache disque hôte
n'est pas purgé, comme pour les VM.

La mémoire est la somme des RSS des processus applicatifs et du moteur,
avec rootlesskit, VPNKit, containerd, shims, FUSE et publication de port.
Des pages partagées peuvent être comptées plusieurs fois, comme avec les VM.
La mesure disque exige les métadonnées overlay/fuse-overlayfs : couches uniques
des images, couches modifiables des conteneurs et volume. Les vues fusionnées,
archives d'export et caches de construction ne sont pas ajoutés.

Sur un moteur rootless, l'inspection du stockage peut nécessiter de lancer
le vérificateur dans l'espace utilisateur et de montage de ce daemon :

```sh
nsenter -t "$(cat "$DOCKER_PIDFILE")" -U -m --wd="$PWD" -- \
  python3 docker/verifier-etape14.py \
  --docker "$DOCKER_BIN" --env-file "$DOCKER_ENV_FILE" \
  --project intern-verification --engine-pidfile "$DOCKER_PIDFILE"
```

Ce choix donne accès au stockage du moteur rootless concerné ; il ne nécessite
pas de service Docker système. Les essais depuis l'hôte restent sur son réseau,
car la commande ne rejoint pas l'espace réseau du daemon.

### Générer le compte rendu

Depuis la racine d'Intern, avec les dépendances documentaires installées dans
un environnement dédié selon `analyse/requirements-docs.txt` :

```sh
python3 docker/rediger-comparaison.py
python3 docker/generer-comparaison.py
pdfinfo docs/compte_rendu_comparaison.pdf
```

La source [comparaison.md](../docs/comparaison.md) est générée depuis les mesures
brutes VM et Docker. Le [PDF](../docs/compte_rendu_comparaison.pdf) contient
deux pages. Le [rapport technique](docs/etape14.md) rassemble les contrôles
des erreurs fréquentes et les limites de comparaison. Le temps humain de mise
en place initial n'a pas été chronométré pour les VM ni pour les conteneurs.
