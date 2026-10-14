# Plan JMeter : connexion et candidatures

## Méthode de travail et points de contrôle

Cette procédure permet de reproduire les étapes 15 à 17 et d'expliquer les
choix effectués. Les rapports [15](ETAPE15.md), [16](ETAPE16.md) et
[17](ETAPE17.md) indiquent les preuves disponibles et leurs limites.
Les commandes de préparation et de charge servent à une nouvelle exécution :
ne pas les lancer en parallèle d'une campagne déjà active.

Pour chaque étape : lire l'objectif, vérifier les prérequis, préparer un
environnement isolé, exécuter, examiner les résultats bruts, puis consigner les
preuves et les limites dans le rapport et l'index des livrables. Un fichier
présent ne suffit pas à établir que son contenu est correct. Un test local ne
prouve pas à lui seul que Docker ou les VM fonctionnent.

| Étape | Question à résoudre | Preuve nécessaire avant de poursuivre |
| --- | --- | --- |
| 15 | Le parcours réussit-il et détecte-t-il un mauvais mot de passe ? | Une réussite et un refus HTTP 401 observés, assertions et captures GUI |
| 16 | L'injecteur a-t-il assez de marge et les mesures sont-elles répétables ? | Mesures statiques, ressources de l'injecteur, deux contrôles comparables et écarts |
| 17 | Les campagnes utilisent-elles les mêmes entrées et produisent-elles toutes les mesures ? | Seize dossiers complets, résultats bruts, métriques serveur, journal et restauration vérifiée |

### Préparer les commandes sur son poste

Les commandes de préparation ci-dessous partent de la racine d'Intern.
La section graphique indique explicitement quand se placer dans `mesure/`.
Configurer dans le terminal les chemins propres au poste : `DOCKER_BIN`,
`DOCKER_ENV_FILE`, `JMETER_BIN` et `MESURE_PROJECT`. En Docker rootless,
configurer aussi `DOCKER_HOST` et `DOCKER_CONFIG`. Garder les secrets dans le
fichier d'environnement local hors du dépôt.

Avant un lancement neuf, vérifier les programmes et le moteur :

```sh
java -version
"$JMETER_BIN" --version
"$DOCKER_BIN" version
"$DOCKER_BIN" compose version
"$DOCKER_BIN" info --format '{{.ServerVersion}}'
VBoxManage list runningvms
```

`docker --version` vérifie seulement le client. `docker info` doit réussir
pour établir que le moteur répond. La liste des VM et l'état des projets
Compose servent à vérifier qu'un seul déploiement sera actif pendant la mesure.
Le pilote de l'étape 17 gère les transitions ; ne pas démarrer un autre
déploiement pendant son exécution.

### Rôle des fichiers et automatisations

| Fichier | Travail réalisé | Point à savoir expliquer |
| --- | --- | --- |
| `plan.jmx` | Décrit les requêtes, sessions, comptes et assertions | Un HTTP 200 ne suffit pas : l'identité et la candidature attendue sont contrôlées |
| `scripts/preparer_comptes.py` | Ajoute vingt candidats fictifs avec leurs candidatures | Une transaction protège le peuplement ; un compte incompatible provoque un refus |
| `protocole.json` | Fixe les paliers et les durées | Changer ces paramètres entre déploiements invaliderait la comparaison |
| `scripts/etalonnage.py` | Génère un plan CLI, lance JMeter et analyse la fenêtre stable | La montée et la stabilisation sont exclues des statistiques |
| `scripts/rediger_etalonnage.py` | Compare les contrôles et produit le rapport | Les chiffres viennent des fichiers mesurés, avec vérification des empreintes |
| `scripts/campagnes17.py` | Prépare les bases dédiées, alterne les déploiements et collecte les preuves | Les bases initiales sont conservées ; chaque campagne restaure le même export |
| `scripts/metrics_serveur.py` | Mesure CPU, mémoire, I/O et statistiques PostgreSQL | Les compteurs utilisés et leurs limites sont identifiés dans les résultats |
| `scripts/collecteur_serveur.py` | Horodate sur l'hôte les relevés reçus | Les horloges VM ne sont pas utilisées seules pour aligner les fenêtres |
| `scripts/lancer17.py` | Lance le pilote en arrière-plan, affiche son état ou demande un arrêt | Le lanceur ne démarre pas le moteur Docker ; celui-ci doit rester disponible |

## Objectif et scénario

Le plan reproduit la connexion d'un candidat puis la consultation de ses
candidatures, données privées filtrées par session. Une requête préparatoire
obtient le CSRF requis par Django. Le catalogue public ne prouve pas la
réussite de ce parcours.

| Ordre | Appel | Assertion |
| --- | --- | --- |
| 0 | `GET /api/v1/auth/csrf/` | HTTP 200 et jeton CSRF non vide |
| 1 | `POST /api/v1/auth/login/` | HTTP 200, identité et rôle attendus, cookie `sessionid` reçu |
| 2 | `GET /api/v1/applications/?page_size=20` | HTTP 200, liste non vide et identifiant de la candidature attendue |

Chaque utilisateur conserve ses cookies et son compte. La connexion et la
lecture du CSV sont dans un contrôleur « une seule fois » ; les itérations
suivantes consultent les candidatures. Une erreur arrête le fil concerné.
Un temps de réflexion de 1 000 ms précède chaque consultation.

## Prérequis et comptes

Installer Java et [Apache JMeter](https://jmeter.apache.org/download_jmeter.cgi),
en vérifiant l'intégrité de l'archive. JMeter s'exécute sur l'hôte.
Les essais consignés utilisent JMeter 5.6.3 et Java 21.

Utiliser une base de démonstration dédiée, initialisée avec
`donnees/schema.sql` et `donnees/data.sql`. Ne pas réinitialiser une base
existante contenant des données à conserver. Le script suivant ajoute vingt
candidats fictifs actifs et une candidature par candidat, sans appel externe.
Il est transactionnel et refuse un compte existant incompatible.

Depuis la racine du projet, avec les variables locales du client Docker,
du fichier d'environnement et du projet isolé. Utiliser un nom de projet neuf
pour obtenir un volume distinct (par exemple `MESURE_PROJECT=intern-mesure`).
L'overlay suivant requiert Compose 2.24.4 ou ultérieur, remplace la publication
du proxy par 8081 et conserve les images déjà construites :

```sh
"$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml \
  -f mesure/compose.test.yaml -p "$MESURE_PROJECT" \
  up -d --no-build --wait --wait-timeout 180
"$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml \
  -f mesure/compose.test.yaml -p "$MESURE_PROJECT" \
  exec -T metier .venv/bin/python app/manage.py shell \
  --verbosity 0 --command 'exec(__import__("sys").stdin.read())' \
  < mesure/scripts/preparer_comptes.py > mesure/comptes.csv
```

Le fichier CSV contient `username,password,application_id`. Ses mots de passe
sont explicitement fictifs, réservés à cette base isolée. Ne pas utiliser de
comptes réels. Les identifiants des candidatures viennent de la base réellement
peuplée ; régénérer le CSV si celle-ci change.

Pour préparer la comparaison, utiliser le même peuplement sur les deux
déploiements et confirmer les mêmes identifiants avant de conserver un CSV
commun. Les références de démarrage et de mémoire figurent dans
`deploiement/docs/mesures-etape10.json` et `docker/docs/mesures-etape14.json`.
Le démarrage et l'arrêt des deux déploiements, ainsi que l'égalité des jeux de
données, doivent être revérifiés avant l'étalonnage et les campagnes.

## Vérification graphique à un utilisateur

Depuis `mesure/`, pointer `port` vers le proxy de la base dédiée :

```sh
jmeter -t plan.jmx -Jport=8081
```

Les valeurs par défaut sont un utilisateur, une seconde de montée et une
itération. Sélectionner « Voir les résultats », puis lancer avec Ctrl+R.
Les trois appels doivent être verts. Conserver une capture de cette fenêtre.
Fermer JMeter, puis tester avec un mot de passe volontairement incorrect :

```sh
jmeter -t plan.jmx -Jport=8081 -Jmot_de_passe=incorrect
```

La préparation CSRF doit réussir, la connexion doit apparaître en échec
HTTP 401, et la consultation doit être absente. Cliquer la connexion pour
lire l'assertion, puis conserver la capture. Un HTTP 403 CSRF ou 429 de
limitation ne remplace pas ce contrôle des identifiants.

## Vérification reproductible en ligne de commande

```sh
mkdir -p resultats/etape15
jmeter -n -t plan.jmx -Jport=8081 \
  -l resultats/etape15/reussite.csv -j /tmp/jmeter-reussite.log
jmeter -n -t plan.jmx -Jport=8081 -Jmot_de_passe=incorrect \
  -l resultats/etape15/echec.csv -j /tmp/jmeter-echec.log
python3 tests/verifier_etape15.py
```

Pour une nouvelle exécution, choisir de nouveaux fichiers de résultats.
La sortie du programme JMeter ne suffit pas à détecter une assertion échouée :
le vérificateur lit les résultats bruts. Ces essais sont des contrôles du
scénario, pas des mesures de performance ni un étalonnage.

### Décider si l'étape 15 est vérifiée

Vérifier trois conditions : le cas correct comporte les trois appels réussis ;
le mot de passe incorrect produit bien HTTP 401 et une assertion échouée ;
aucune consultation privée ne suit ce refus. Les deux captures doivent montrer
ces exécutions réelles dans JMeter. Le vérificateur contrôle les CSV archivés
dans `resultats/etape15`, il ne relance pas le serveur ni l'interface graphique.
Pour de nouveaux CSV, adapter ses chemins avant de vérifier les nouvelles preuves.

À expliquer : le jeton CSRF protège la requête de connexion, tandis que le
cookie `sessionid` prouve ensuite la session. Chaque candidat doit consulter
sa propre candidature. Le mauvais mot de passe teste la capacité du plan à
détecter un échec, avant de lui confier une campagne de charge.

Paramètres disponibles : `hote`, `port`, `protocole`, `comptes`, `utilisateurs`,
`montee`, `iterations`, `reflexion` et `mot_de_passe` (contrôle négatif).
Le CSV ne recycle pas les comptes ; préparer davantage de comptes pour dépasser
vingt utilisateurs. Les limites de connexion restent actives : trente essais
par IP et dix par identité sur quinze minutes. Les paliers, la montée et la
durée stable seront fixés lors de l'étalonnage. Désactiver l'écouteur graphique
pendant les campagnes, qui s'exécutent exclusivement en CLI.

Après les essais, arrêter uniquement ce projet en conservant son volume :

```sh
"$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml \
  -f mesure/compose.test.yaml -p "$MESURE_PROJECT" down
```

Référence technique : [composants JMeter](https://jmeter.apache.org/usermanual/component_reference.html).

## Étalonnage en ligne de commande

Les paramètres applicatifs sont centralisés dans [protocole.json](protocole.json).
Le script conserve `plan.jmx` comme source du parcours : il génère un plan à
durée limitée avec des itérations continues et retire l'écouteur graphique.
Pour le statique, il conserve les paramètres HTTP du même plan et utilise
uniquement la feuille CSS Nginx, sans cookies, connexion ni temporisation.
Les plans générés sont conservés dans les dossiers des résultats.

Sur l'hôte, une fois les images construites, démarrer seulement le projet
isolé décrit plus haut. Les autres déploiements doivent être arrêtés pendant
les contrôles. Vérifier les vingt comptes avant l'exécution. `JMETER_BIN`
désigne le programme JMeter installé sur l'hôte. Depuis la racine d'Intern :

```sh
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

Les dossiers de sortie doivent être neufs. Pour refaire l'étalonnage, conserver
les preuves existantes dans une archive puis choisir de nouveaux dossiers ;
adapter les chemins du générateur de rapport à cette nouvelle série.
Les mesures statiques archivées ont été réalisées sur le proxy de référence
au port 8080, avant l'activation de la base isolée ; ajouter `--port 8080`
pour reproduire ce point d'entrée. La procédure ci-dessus cible le proxy isolé
au port 8081, avec les mêmes images.

Le script vérifie une fenêtre complète, hors montée et stabilisation : les
requêtes doivent commencer et finir dans cette fenêtre, chaque utilisateur
doit y être présent et le nombre de fils actifs doit rester égal au palier.
Les résultats comportent le débit total et réussi, les centiles et les erreurs,
ainsi que les ressources CPU/RSS de l'injecteur et la charge globale de l'hôte.
Le générateur refuse des contrôles dont le plan, les comptes, les scripts SQL,
les paramètres appliqués ou l'hôte diffèrent. Il indique un échec de
répétabilité si le débit ou le p95 diffère de plus de 10 %, ou si des erreurs
ont été détectées. Le code de sortie JMeter seul ne suffit pas.

Entre les paliers des futures campagnes, attendre quinze minutes pour que les
connexions cumulées respectent la protection de trente essais/IP par fenêtre.
Les deux contrôles à dix utilisateurs ne consomment que vingt connexions ;
aucune autre connexion ne doit avoir épuisé ce budget. Attendre l'expiration
de la fenêtre si HTTP 429 apparaît, sans supprimer les compteurs ni désactiver
les protections.

Après les essais, arrêter le projet isolé en conservant son volume, puis
remettre le déploiement initial dans son état de fonctionnement.

### Décider si l'étape 16 est vérifiée

Lire les `synthese.json` des mesures statiques et des deux contrôles,
les paramètres de `configuration.json`, puis
`resultats/etape16/etalonnage.json`. Le rapport [ETAPE16.md](ETAPE16.md)
présente les valeurs réellement obtenues.

| Vérification | Critère appliqué | Pourquoi |
| --- | --- | --- |
| Ressource statique | HTTP 200 et contenu CSS attendu, sans erreur | Éviter de mesurer une réponse d'erreur très rapide |
| Marge de l'injecteur | Débit statique nettement supérieur au débit applicatif attendu | Éviter que l'instrument limite les consultations |
| Fenêtre stable | Nombre d'utilisateurs constant, chaque utilisateur couvre la fenêtre | Éviter d'inclure un démarrage ou une disparition de fils |
| Contrôles comparables | Mêmes empreintes, paramètres et hôte | Attribuer l'écart à la répétabilité plutôt qu'à un changement de scénario |
| Répétabilité | Zéro erreur et écarts de débit et p95 au plus 10 % | Critère opérationnel utilisé par le générateur du rapport |

Le débit réussi est le nombre de consultations réussies dans les 120 secondes
stables, divisé par 120. Le p95 est une durée sous laquelle se trouvent 95 % des
temps de réponse mesurés. Pour comparer deux valeurs A et B, calculer
`abs(B - A) / ((A + B) / 2) × 100`. Le p99 reste documenté séparément.

À expliquer : avec vingt candidats et une seconde de réflexion, le débit de
consultation est au plus vingt requêtes par seconde, avant même les délais de
réponse. Le plafond statique observé est une capacité du chemin complet
injecteur/réseau/proxy sur ce poste. Ce n'est pas une limite universelle de JMeter.
Les paliers sont arrêtés à vingt candidats dans le protocole étalonné.

## Campagnes et contrôle final de l'étape 17

Suivre [ETAPE17.md](ETAPE17.md) pour la configuration locale, le lancement,
les transitions, le diagnostic et la reprise après incident. Le pilote appelle
le même script de mesure CLI pour chaque palier. Il ajoute les relevés des
trois services et filtre leurs intervalles dans la même fenêtre stable.

Avant de déclarer la collecte terminée, vérifier l'état `complete`, les seize
paliers attendus et l'événement `reference_restored`. Vérifier aussi que le
déploiement de référence répond réellement et que les VM sont arrêtées.
Une campagne peut mesurer des erreurs sous charge : conserver ces erreurs et
leur nombre ; ne pas supprimer les lignes en échec pour améliorer le résultat.
Un dossier incomplet ou des métriques absentes empêchent une livraison complète.

Le vérificateur centralise le contrôle des preuves, sans relancer de charge :

```sh
python3 mesure/scripts/verifier17.py
# Inclure les sources et l'export privés, s'ils sont conservés :
python3 mesure/scripts/verifier17.py --runtime ../.runtime-etape17
```

Il recalcule les statistiques des CSV bruts et des relevés serveur dans la
fenêtre stable, vérifie les configurations et l'ordre, puis produit
`verification.json`, `releve-paliers.csv`, `releve-serveurs.csv` et `SHA256SUMS`.
Les détails et limites sont dans [ETAPE17.md](ETAPE17.md#relevés-livrés-et-vérification).
La santé des services doit être vérifiée séparément en direct. Conserver et
signaler les incidents qui peuvent affecter la comparaison. L'analyse
comparative relève de l'étape 18.

## Analyse et comparaison de l'étape 18

Suivre [ETAPE18.md](ETAPE18.md) pour les commandes d'analyse et l'export du
rapport. Recalculer les statistiques sur les preuves de l'étape 17, contrôler
leurs empreintes, puis tracer chaque répétition séparément. Comparer les deux
déploiements au même nombre d'utilisateurs. Le débit moyen est une moyenne
des deux débits mesurés ; conserver chaque p95 séparé, sans prétendre qu'une
moyenne de p95 représente le p95 de l'ensemble des requêtes.

Rechercher un débit qui cesse de progresser, une hausse durable de latence ou
des erreurs, puis rapprocher ces signes des ressources serveur. Si la plage
testée ne montre pas de saturation, écrire « non observée » sur les courbes
et dans le tableau. Le composant ayant le CPU le plus élevé n'est pas, à lui
seul, un goulot démontré. Signaler la temporisation, les variations entre
séries et les incidents avant toute conclusion sur la capacité du système.

Le [rapport](docs/rapport-charge.md) reprend le tableau demandé et répond dans
l'ordre : écart chiffré, explication technique et hypothèses, premier composant
limitant, limites de la mesure. Le PDF doit comporter trois à quatre pages ;
l'export livré comporte quatre pages A4. Les graphes, valeurs et sources doivent
être lisibles et cohérents avec les données conservées.
