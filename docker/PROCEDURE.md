# Conteneurisation — couche données

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
Les noms `POSTGRES_DB`, `POSTGRES_USER` et `POSTGRES_PASSWORD` sont ceux de
l'application. Le service métier utilisera ensuite `POSTGRES_HOST=donnees`
et `POSTGRES_PORT=5432`.

## Déclaration et initialisation

[compose.yaml](compose.yaml) déclare uniquement le service de données à cette
étape. Les couches métier et proxy seront ajoutées aux étapes suivantes.
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
