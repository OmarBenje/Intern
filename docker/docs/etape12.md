# Étape 12 — Image de la couche métier

## Objectif et livrables

Construire l'application existante et accéder à PostgreSQL par le nom
`donnees`, sans port publié sur le métier.

**Résultat actuel : image reconstruite avec Podman, 388 668 114 octets ;
Git, uv et cache uv absents ; démarrage Gunicorn vérifié.** La connexion SQL
et la validation avec Docker Engine restent à exécuter.

- [Construction de l'image](../metier.Dockerfile).
- [Exclusion du contexte](../.dockerignore), source unique à la racine.
- [Composition des deux services](../compose.yaml).
- [Démarrage](../demarrer-metier.sh) et [vérificateur](../verifier-metier.sh).
- [Procédure et commande de mesure de taille](../PROCEDURE.md).

L'image comporte deux étapes : installation des dépendances verrouillées,
puis copie de l'environnement et du code dans une base Python réduite.
Le processus final utilise un compte sans privilèges et écoute sur toutes
les interfaces du conteneur. L'isolation vient des réseaux et de l'absence
de publication du port.

## Vérifications du 12 octobre 2026

| Contrôle | Résultat |
| --- | --- |
| YAML et chemins du contexte, Dockerfile et fichiers copiés | Réussis |
| Dépendances avant code, deux bases Python versionnées | Vérifiés statiquement |
| Cache d'installation absent de l'image finale | Décrit par la construction ; contenu final à vérifier |
| Une seule source Dockerfile et exclusion, avec liens valides | Vérifié |
| `POSTGRES_HOST=donnees`, port 5432 | Vérifié sur la déclaration |
| Métier sur frontal et interne, aucun port publié | Vérifié sur la déclaration |
| Dépendance conditionnée à la santé de la base | Vérifiée |
| Syntaxe des scripts shell | Réussie |
| Chargement local des paramètres Django | Réussi, sans connexion SQL |
| `manage.py check` local avec hôte `donnees` | Échec : nom accessible seulement dans le réseau des conteneurs |
| Construction et démarrage sur Docker Engine | Non exécutés : moteur requis indisponible |
| Connexion SQL depuis le métier, sonde HTTP et CV privés | À vérifier sur l'image construite |
| Taille de l'image | Non mesurée : image non construite |

Les commandes Docker disponibles délèguent toujours à Podman et échouent
avant l'exécution du projet, comme décrit au [rapport données](etape11.md).
La validation locale des paramètres ne prouve ni la compatibilité de toutes
les dépendances avec l'image cible ni la résolution DNS des services.

Les preuves de connexion, d'isolation et de taille seront générées par les
commandes de la procédure lors de leur exécution réelle. Aucun résultat Docker
n'est déduit des contrôles statiques.

État au 12 octobre : **livrables préparés ; construction, connexion et taille
sur Docker Engine à vérifier**. Les vérifications ultérieures sont ci-dessous.

## Taille de l'image locale antérieure

Une inspection Podman hors du sandbox, le **14 octobre 2026**, a permis
de mesurer l'image métier effectivement présente dans le stockage local :

| Mesure | Résultat |
| --- | --- |
| Image inspectée | `localhost/intern-tp-metier:local` |
| Taille exacte non compressée | **1 042 844 117 octets** |
| Conversion décimale arrondie | **1,043 Go** |
| Création de l'image | 12 octobre 2026, 13:08:12 UTC |

L'identifiant complet et la commande sont conservés dans la
[preuve de mesure](taille-image-locale-etape12.txt).
Lors de cette première inspection, l'étiquette `intern-metier:etape12`
n'existait pas dans ce stockage.
La correspondance de l'image locale avec le Dockerfile actuel n'a pas été
vérifiée : cette valeur mesure l'image nommée ci-dessus, sans valider la
construction prévue ni le déploiement sur Docker Engine.
Les limites d'exécution constatées dans le sandbox restent applicables.

## Répartition mesurée de l'image locale

L'historique de `localhost/intern-tp-metier:local` a été inspecté le
14 octobre 2026. Les valeurs ci-dessous proviennent des tailles entières
de `podman history --no-trunc --format json`.

| Groupe de couches | Octets |
| --- | ---: |
| Base Python 3.12.3 slim et système | 135 367 680 |
| Installation Git et dépendances système | 93 644 288 |
| Installation uv | 55 111 680 |
| `uv sync`, environnement Python et cache | 503 910 400 |
| `useradd`, répertoires et `chown -R /app` | 252 517 888 |
| Code, fichiers partagés et manifests de dépendances | 2 277 376 |
| Somme des tailles de couches retournées | 1 042 829 312 |
| Taille totale retournée par l'inspection de l'image | 1 042 844 117 |

Les deux méthodes diffèrent de 14 805 octets ; cet écart n'est pas attribué
à une catégorie sans mesure supplémentaire. La taille totale de l'inspection
reste la référence pour cette image.

Un conteneur temporaire, sans réseau et avec système de fichiers en lecture
seule, a permis de compter la taille logique des fichiers. Les liens symboliques
sont exclus et les liens physiques sont comptés une fois par répertoire mesuré.
Ces tailles de fichiers ne sont pas directement additionnables aux tailles
des couches, qui incluent leur propre représentation et les versions anciennes.

| Répertoire dans l'image | Octets de fichiers |
| --- | ---: |
| `/app/metier/.venv` | 240 043 798 |
| `/root/.cache/uv` | 243 160 158 |
| `/app/metier/app` | 1 848 695 |
| `/var/lib/apt/lists` | 0 |

Principaux répertoires de dépendances, inclus dans l'environnement Python :

| Dépendance | Octets de fichiers |
| --- | ---: |
| NumPy et `numpy.libs` | 56 178 923 |
| `curl_cffi` | 38 917 861 |
| pandas | 38 663 298 |
| Django | 23 315 423 |
| botocore | 20 232 487 |
| Pillow et `pillow.libs` | 19 552 825 |
| psycopg binaire et bibliothèques associées | 19 896 230 |

## Réductions identifiées

1. Ne pas inclure le cache uv dans l'image finale. L'image locale conserve
   effectivement plus de 243 millions d'octets sous `/root/.cache/uv`.
2. Garder Git et uv dans le constructeur uniquement. Leurs installations
   ajoutent respectivement 93 644 288 et 55 111 680 octets de couches.
3. Éviter `chown -R /app` après copie de toutes les dépendances : dans l'image
   inspectée, cette opération produit une couche de 252 517 888 octets.
   Restreindre les changements de propriétaire aux dossiers modifiables,
   ou définir les droits dès la copie si nécessaire.
4. Étudier ensuite les dépendances facultatives. NumPy, pandas et curl_cffi
   sont utilisés par la collecte JobSpy ; leur retrait exige un profil
   d'installation distinct et une vérification des fonctions concernées.
   Ils ne sont pas supprimés arbitrairement du projet.

Le Dockerfile actuel applique déjà les trois premières mesures : constructeur
séparé, copie du seul environnement Python et droits modifiés uniquement sur
le stockage privé et les statiques. L'historique mesuré contient au contraire
une base 3.12.3, uv 0.9.29 et le changement de propriétaire récursif de `/app` :
**l'image locale de 1 Go ne provient pas de cette recette actuelle**.
La nouvelle construction et son poids mesuré sont documentés ci-dessous.

Le cache de construction réutilise les couches pour accélérer les builds et
consomme du stockage sur le poste ; il ne s'ajoute pas comme une copie entière
à chaque image finale. Un cache de paquets laissé dans une couche, comme ici
le cache uv, fait en revanche partie de cette image. Effacer ce cache dans une
couche ultérieure ne retire pas les octets des couches précédentes.

Références : [cache de construction Docker](https://docs.docker.com/build/cache/),
[construction en plusieurs phases](https://docs.docker.com/build/building/multi-stage/).

## Construction et contrôle de conformité du 14 octobre 2026

La recette actuelle a été construite réellement avec Podman, hors du sandbox :

```sh
podman build -f docker/metier.Dockerfile -t localhost/intern-metier:etape12 .
podman image inspect localhost/intern-metier:etape12 --format '{{.Id}} {{.Size}}'
```

| Résultat | Valeur |
| --- | ---: |
| Taille exacte de la nouvelle image | **388 668 114 octets** |
| Conversion décimale | **388,668114 Mo** |
| Différence par rapport à l'image précédente | **654 176 003 octets** |
| Réduction arrondie | **62,73 %** |

La comparaison porte sur deux images réellement mesurées. La version
corrective de Python change aussi entre elles ; la différence totale ne doit
pas être attribuée exclusivement aux trois corrections.

| Exigence | Vérification réalisée |
| --- | --- |
| Base légère et versionnée | Deux phases `python:3.12.15-slim-bookworm`, construction réussie |
| Installation des dépendances | 43 paquets depuis le verrou ; imports principaux réussis |
| Dépendances avant code pour réutiliser les couches | Manifest et verrou copiés avant `uv sync` ; code copié ensuite dans la phase finale |
| Copie du code | Sources applicatives et fichiers partagés présents |
| Commande de démarrage | Gunicorn lancé sous `intern`, deux workers ; `/health/live/` répond HTTP 200 |
| Fichier d'exclusion | Exclusions à la racine du contexte ; aucun fichier local exclu retrouvé dans les sources copiées |
| Environnement virtuel local exclu | `.venv` de l'hôte exclu ; seul l'environnement créé dans le constructeur est copié |
| Cache uv hors de l'image finale | `/root/.cache/uv` absent dans le conteneur final |
| Git et uv réservés au constructeur | Deux exécutables absents ; paquet global uv absent dans l'image finale |
| Pas de changement de propriétaire global de `/app` | Code et environnement Python détenus par root ; seuls stockage privé et statiques détenus par `intern` |

Les identifiants, empreintes des sources et résultats sont conservés dans la
[preuve de vérification](verification-image-etape12.txt).
Les contrôles de contenu ont utilisé un conteneur temporaire en lecture seule,
sans réseau externe. Le contrôle HTTP a ajouté uniquement un espace temporaire
en mémoire pour Gunicorn. Aucune base existante n'a été utilisée ou modifiée.

Les exigences de construction et les trois mesures de réduction sont
vérifiées sur cette image Podman. La connexion à `donnees`, le contrôle des
migrations contre PostgreSQL et l'exécution avec Docker Engine restent à
vérifier. Le cache de couches reste utilisable : désactiver le cache de
paquets uv ne désactive pas la réutilisation des couches de construction.
