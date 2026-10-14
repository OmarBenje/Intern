# Conteneurisation — données et métier

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

[compose.yaml](compose.yaml) déclare les services données et métier.
Le proxy sera ajouté à l'étape suivante.
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

Le fichier [d'exclusion](.dockerignore) pointe vers `../.dockerignore`, utilisé
par le contexte de construction situé à la racine d'Intern. Il exclut les
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
