# Plan JMeter : connexion et candidatures

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
