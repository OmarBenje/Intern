# Étape 17 — Campagnes VM et Docker

## Objectif et livrables

Conserver les résultats JMeter bruts des deux déploiements et relever les
métriques serveur pour chaque palier. Deux séries sont prévues, avec inversion
de l'ordre : VM puis Docker, ensuite Docker puis VM.

**État : seize paliers terminés et vérifiés techniquement.** Les deux séries
contiennent les CSV bruts et les relevés des trois services pour chaque palier.
Les 22 199 échantillons JMeter ne comportent aucune erreur ; 16 902 consultations
appartiennent aux fenêtres stables. Les protections de connexion sont restées
actives et aucun HTTP 429 n'a été observé.

Une panne du moteur Docker a interrompu la transition après les quatre premiers
paliers VM. La reprise a conservé ces paliers ; l'incident reste dans le journal.
La collecte est complète, mais cette interruption limite l'interprétation de
l'effet de l'ordre de passage. La cause de l'arrêt du moteur reste indéterminée.
La restauration finale est vérifiée : trois conteneurs de référence sains,
HTTP 200 sur le contrôle de disponibilité et aucune VM active.

## Relevés livrés et vérification

| Livrable | Contenu |
| --- | --- |
| [Série 1 VM](resultats/etape17/serie-1/vm), [série 1 Docker](resultats/etape17/serie-1/docker) | Quatre paliers par déploiement, dans l'ordre VM puis Docker |
| [Série 2 Docker](resultats/etape17/serie-2/docker), [série 2 VM](resultats/etape17/serie-2/vm) | Quatre paliers par déploiement, dans l'ordre inverse |
| [Relevé des paliers](resultats/etape17/releve-paliers.csv) | Seize lignes : échantillons, erreurs, débit et centiles |
| [Relevé serveur](resultats/etape17/releve-serveurs.csv) | Quarante-huit lignes : CPU, RSS, I/O et connexions par service et palier |
| [Vérification](resultats/etape17/verification.json) | Comptage, empreintes et incident enregistré |
| [Empreintes](resultats/etape17/SHA256SUMS) | Intégrité des fichiers bruts, configurations et relevés |
| [Restauration](resultats/etape17/restauration.json) | État des services et réponse HTTP effectivement vérifiés |
| [Manifeste](resultats/etape17/manifest.json), [journal](resultats/etape17/journal.jsonl) | Ordre, versions, ressources, restaurations SQL, repos et reprise |

Le [vérificateur](scripts/verifier17.py) recalcule les statistiques depuis les
CSV bruts avec la fonction d'analyse utilisée pendant les exécutions, compare
les résultats archivés, puis vérifie les relevés serveur dans les mêmes fenêtres.
Il contrôle les paramètres communs, les plans identiques pour un même palier,
l'ordre des seize exécutions et le respect des repos. Chaque service possède
au moins 22 relevés stables, au-dessus du minimum requis de quinze.
Les tableaux regroupés sont dérivés des preuves conservées ; aucune charge
n'est relancée pour les produire.

Depuis la racine d'Intern :

```sh
python3 mesure/scripts/verifier17.py
# Vérification supplémentaire de l'export et des sources privés, si conservés :
python3 mesure/scripts/verifier17.py --runtime ../.runtime-etape17
# Contrôle des empreintes depuis le dossier de résultats :
(cd mesure/resultats/etape17 && sha256sum -c SHA256SUMS)
```

La vérification des fichiers ne sonde pas les services en direct : la preuve de
restauration est datée séparément. Les versions Python diffèrent entre VM et
Docker ; les VM ont des ressources fixes, les conteneurs n'ont pas de quotas
CPU/mémoire explicites. Les méthodes CPU/I/O indiquées dans les relevés doivent
être prises en compte lors de leur comparaison. L'analyse comparative est
documentée à l'[étape 18](ETAPE18.md).

## Protocole

**Nouvelles campagnes :** le pilote utilise désormais la
[configuration de performance](PERFORMANCE.md) : limitation des connexions
désactivée uniquement pour les mesures, et repos dynamique de 30 à 180 s.
Réétalonner à l'étape 16 et utiliser de nouveaux dossiers de travail et de
résultats. Les preuves archivées décrites ci-dessous gardent leur protocole
historique avec pauses de quinze minutes.

Méthode commune et critères de vérification :
[procédure des étapes 15 à 17](PROCEDURE.md#méthode-de-travail-et-points-de-contrôle).

La [configuration d'étalonnage](protocole.json) reste inchangée : paliers de
1, 5, 10 et 20 candidats distincts ; montée de 30 s, stabilisation de 15 s,
fenêtre stable de 120 s et réflexion de 1 000 ms. Les repos de quinze minutes
entre les paliers préservent les protections de connexion.

Le [pilote](scripts/campagnes17.py) prépare un export SQL commun depuis les
scripts de peuplement et les vingt comptes fictifs. Il restaure cet export
avant chacune des quatre campagnes, uniquement dans les bases dédiées nommées
`intern_mesure17`. Les bases et volumes des déploiements de référence sont
conservés. Le code Python et le client de la VM de mesure proviennent des mêmes
images que la composition Docker. Les versions et ressources de chaque
environnement sont enregistrées dans le manifeste.

Un seul déploiement fonctionne pendant chaque campagne. L'injecteur s'exécute
sur l'hôte, en CLI. La VM de mesure utilise une unité métier et une entrée
Nginx séparées ; les paramètres du service publié ne sont pas remplacés.
Une règle PostgreSQL temporaire autorise seulement la base dédiée, le compte
applicatif et l'adresse interne de la VM métier. En fin d'exécution, les
configurations temporaires sont retirées et le déploiement initial est rétabli.

### Déroulement du pilote à savoir reproduire

| Ordre | Action | Vérification et preuve |
| --- | --- | --- |
| 1 | Arrêter le projet Docker de référence | Les mesures ne partagent pas les ressources avec ce déploiement |
| 2 | Préparer le projet dédié `intern-etape17` | Volume distinct, comptes fictifs et CSV identique à celui du plan |
| 3 | Exporter la base préparée et les sources des images | Empreintes SQL, comptes et sources enregistrées dans `manifest.json` |
| 4 | Arrêter Docker de mesure et démarrer les trois VM | Accès SSH disponible et versions applicatives vérifiées |
| 5 | Installer les services VM dédiés | Nouvelle unité `intern-mesure17`, nouvelle entrée Nginx et règle PostgreSQL limitée |
| 6 | Restaurer la base dédiée avant chaque campagne | Événement `database_restored` avec l'empreinte du même export |
| 7 | Exécuter les paliers 1, 5, 10 et 20 | Plan CLI sauvegardé, CSV brut et métriques de trois services |
| 8 | Attendre le retour au repos entre deux paliers | Événements `cooldown_start` et `cooldown_complete`, relevés dans `repos/` |
| 9 | Changer de déploiement et inverser l'ordre pour la seconde série | Ordre VM/Docker puis Docker/VM visible dans le journal |
| 10 | Arrêter la mesure et rétablir la référence | Événement `reference_restored`, conteneurs sains et VM arrêtées |

Le code et les fichiers statiques des VM dédiées proviennent des images Docker
de mesure. Les paquets Django, DRF et Gunicorn sont comparés avant les campagnes.
Les versions Python et les ressources VM/Docker sont aussi conservées : leur
présence dans le manifeste permet de signaler les différences restantes, pas
de prétendre que les environnements sont identiques sur tous les points.

Sur les VM, le proxy reçoit le port interne 8082 et relaie vers Gunicorn sur
8001. Une redirection NAT temporaire expose ce proxy sur `127.0.0.1:8081` côté
hôte, point d'entrée également utilisé par Docker. Les fichiers du service
initial restent distincts des fichiers de mesure. La restauration SQL supprime
et recrée uniquement `intern_mesure17`, jamais la base initiale `intern`.

Le pilote démarre le même `etalonnage.py application` que celui des contrôles
de l'étape 16. Celui-ci génère un plan à durée limitée depuis `plan.jmx`,
retire l'écouteur graphique et lance JMeter en CLI. Pour refaire un palier
isolé sur un environnement déjà préparé, hors campagne active :

```sh
python3 mesure/scripts/etalonnage.py application --jmeter "$JMETER_BIN" \
  --users 5 --output mesure/resultats/essai-manuel-5
```

Cette commande seule ne restaure pas la base, ne change pas de déploiement et
ne relève pas les métriques serveur : ces tâches appartiennent au pilote.
Elle aide à comprendre la mesure, mais ne remplace pas la campagne complète.

## Fichiers attendus

Chaque dossier `resultats/etape17/serie-N/{vm,docker}/PALIER/` doit contenir :

| Fichier | Contenu |
| --- | --- |
| `brut.csv` | Tous les échantillons JMeter, montée et erreurs comprises |
| `serveur-proxy.jsonl` | CPU, RSS et entrées-sorties du proxy |
| `serveur-metier.jsonl` | CPU, RSS et entrées-sorties du métier |
| `serveur-donnees.jsonl` | CPU, RSS, entrées-sorties et connexions PostgreSQL |
| `configuration.json`, `plan.jmx` | Paramètres et plan réellement exécutés |
| `ressources.csv` | CPU/RSS de l'injecteur et charge de l'hôte |
| `synthese.json`, `serveurs.json` | Vérification de la fenêtre et synthèse du palier |

Le manifeste regroupe les seize paliers, l'ordre réel, les empreintes communes
et l'état de vérification. Le journal indique les restaurations, les périodes
de repos et les transitions. Une exécution incomplète reste identifiée comme telle.

## Métriques et interprétation

Le [collecteur Linux](scripts/metrics_serveur.py) échantillonne toutes les cinq
secondes. CPU et I/O utilisent les compteurs cgroup v2 lorsqu'ils sont accessibles,
y compris les processus terminés. Le repli sur les processus encore vivants est
explicitement identifié ; une valeur inaccessible reste absente. La RSS peut
compter des pages partagées plusieurs fois ; la mémoire cgroup inclut aussi du
cache et reste une mesure distincte.

La base fournit les connexions totales et actives de la base dédiée, les blocs
lus et trouvés en cache et le nombre de transactions. La requête d'observation
se connecte à une autre base, afin d'exclure sa propre connexion du relevé.
Les statistiques PostgreSQL sont cumulatives et peuvent être légèrement retardées.
Les I/O cgroup de Docker rootless peuvent exclure le travail des auxiliaires FUSE.

Le [récepteur](scripts/collecteur_serveur.py) conserve l'heure du serveur et
horodate la réception sur l'hôte pour aligner les fenêtres avec JMeter. Le délai
de collecte et de transport limite la précision aux environs de la cadence de
cinq secondes. La synthèse exclut les intervalles traversant la fenêtre stable
et refuse les paliers avec moins de quinze relevés par service.

## Reproduction

### Lancement autonome et suivi

Depuis la racine d'Intern, la configuration locale de cette session est
préparée dans le dossier de travail voisin `.runtime-etape17`, hors du dépôt.
Le processus autonome continue après fermeture du terminal.

```sh
# Consulter l'avancement (16 paliers attendus).
python3 mesure/scripts/lancer17.py status --runtime ../.runtime-etape17

# Demander un arrêt propre si nécessaire.
python3 mesure/scripts/lancer17.py stop --runtime ../.runtime-etape17
```

Garder l'hôte allumé, sans mise en veille, et conserver le même état de fond.
Ne pas démarrer manuellement l'autre déploiement pendant une campagne.
Attendre l'état `complete`, seize paliers enregistrés et l'événement
`reference_restored` avant de considérer la campagne terminée. L'arrêt propre
conserve les fichiers déjà produits et rétablit le déploiement initial.
Un état `failed` ou `stopped` doit être examiné avant une nouvelle tentative.

Pour un lancement neuf, préparer une nouvelle configuration locale puis utiliser :

```sh
python3 mesure/scripts/lancer17.py start --runtime ../.runtime-etape17
```

### Paramètres du pilote

Les secrets, accès SSH et fichiers de travail restent dans une configuration
locale hors du dépôt. Préparer les variables suivantes puis lancer depuis la
racine d'Intern :

Pour créer une configuration de lancement sur un nouveau poste, définir et
exporter `DOCKER_BIN`, `DOCKER_HOST`, `DOCKER_CONFIG`, `DOCKER_ENV_FILE`,
`MESURE_SSH_CONFIG`, `JMETER_BIN` et `MESURE_RUNTIME`. Les chemins doivent
pointer vers les outils, accès et fichiers existants. `MESURE_RUNTIME` doit
être hors du dépôt Intern, par exemple le dossier voisin `.runtime-etape17`.
Définir aussi `MESURE_REFERENCE_PROJECT`, le nom exact du projet à arrêter
puis à rétablir. `MESURE_OUTPUT` désigne un nouveau dossier de résultats dans
`mesure/resultats/` ; conserver les preuves existantes.

Le fichier contient des chemins locaux, pas une copie des mots de passe :

```sh
python3 - <<'PY'
import json, os
from pathlib import Path
paths = {'docker': 'DOCKER_BIN', 'docker_config': 'DOCKER_CONFIG',
         'env_file': 'DOCKER_ENV_FILE', 'ssh_config': 'MESURE_SSH_CONFIG',
         'jmeter': 'JMETER_BIN', 'runtime': 'MESURE_RUNTIME',
         'output': 'MESURE_OUTPUT'}
config = {key: str(Path(os.environ[var]).resolve()) for key, var in paths.items()}
config.update(docker_host=os.environ['DOCKER_HOST'],
              reference_project=os.environ['MESURE_REFERENCE_PROJECT'])
runtime = Path(config['runtime'])
if runtime.is_relative_to(Path.cwd().resolve()):
    raise SystemExit('Le dossier privé doit rester hors du dépôt Intern')
runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
path = runtime / 'configuration.json'
if path.exists():
    raise SystemExit('Configuration existante : la conserver et la vérifier')
path.write_text(json.dumps(config, indent=2) + '\n')
path.chmod(0o600)
print('Configuration créée ; vérifier Docker avant le lancement.')
PY
python3 mesure/scripts/lancer17.py start --runtime "$MESURE_RUNTIME"
```

La commande directe équivalente suivante reste au premier plan du terminal :

```sh
python3 mesure/scripts/campagnes17.py \
  --docker "$DOCKER_BIN" --docker-host "$DOCKER_HOST" \
  --docker-config "$DOCKER_CONFIG" --env-file "$DOCKER_ENV_FILE" \
  --ssh-config "$MESURE_SSH_CONFIG" --jmeter "$JMETER_BIN" \
  --runtime "$MESURE_RUNTIME" --output "$MESURE_OUTPUT"
```

Les seize paliers représentent 45 min 20 s, auxquels s'ajoutent les repos
dynamiques, la préparation, les restaurations et les démarrages. Avec douze
repos de 30 s, compter environ 51 min 20 s hors transitions. Le pilote refuse de remplacer
un volume ou une base de mesure qui ne lui appartient pas. Les dossiers partiels
doivent être conservés et examinés avant reprise.

Vérifications locales reproductibles :

```sh
python3 -m unittest discover -s mesure/tests -p 'test_metrics_serveur.py'
python3 -m py_compile mesure/scripts/campagnes17.py \
  mesure/scripts/metrics_serveur.py mesure/scripts/collecteur_serveur.py \
  mesure/scripts/preparer_vm_mesure.py
```

## Diagnostic et reprise après incident

### Lire l'état sans modifier les services

Depuis la racine d'Intern, ces commandes lisent les informations locales :

```sh
python3 mesure/scripts/lancer17.py status --runtime ../.runtime-etape17
tail -n 30 mesure/resultats/etape17/journal.jsonl
tail -n 60 ../.runtime-etape17/controller.log
cat ../.runtime-etape17/last-error.txt
```

Les journaux privés peuvent contenir des chemins locaux ; conserver leur
diagnostic utile dans le rapport sans publier les secrets ni les chemins personnels.
`last-error.txt` contient la dernière erreur de commande et peut être remplacé
par une erreur de restauration. Lire aussi la trace du contrôleur pour distinguer
l'erreur initiale d'une erreur pendant le nettoyage.

| État | Signification | Action |
| --- | --- | --- |
| `preparing` | Préparation ou reprise des environnements | Attendre et consulter le journal |
| `running` + `palier_start` | Mesure en cours | Laisser tourner sans modifier les paramètres |
| `running` + `cooldown_start` | Observation du retour au repos | Attendre `cooldown_complete` ; échec si le repos dépasse 180 s |
| `failed` | Exception dans le pilote | Examiner les journaux, les fichiers partiels et la restauration |
| `complete` + `reference_restored` | Collecte terminée et restauration signalée | Vérifier les seize dossiers et la santé réelle de la référence |

Le manifeste et l'existence du processus sont deux informations distinctes.
Si le processus est mort alors que le manifeste indique encore `running`,
le fichier n'a pas été mis à jour après un arrêt brutal. Un processus actif
pendant une reprise peut aussi précéder le premier nouvel événement.
Ne pas interpréter ces seuls libellés comme une preuve de réussite.

### Cas observé : moteur Docker indisponible

La première campagne VM a enregistré les quatre paliers sans erreur.
Au démarrage de Docker, le client a signalé qu'il ne pouvait plus joindre
le moteur sur son socket. La remise en marche automatique de la référence
a échoué pour la même raison. Aucun résultat Docker n'avait alors été enregistré.
La cause de la disparition du moteur n'a pas été établie.

La réparation a suivi cet ordre : vérifier l'absence du moteur, redémarrer
le moteur rootless avec son répertoire de données existant, vérifier
`docker info`, remettre en marche la composition de référence et attendre
ses trois services sains, puis reprendre le pilote. Le script a été adapté
pour démarrer les services nécessaires à la vérification des versions lors
d'une reprise et ignorer une campagne dont les quatre paliers sont déjà complets.

Pour reproduire le redémarrage du moteur rootless utilisé ici, uniquement si
le pilote est arrêté et le moteur réellement absent, configurer les variables
locales `MESURE_ENGINE_BIN` (dossier contenant `dockerd-rootless.sh`),
`MESURE_ENGINE_RUNTIME` (ancien dossier du socket et des fichiers d'exécution)
et `MESURE_ENGINE_DATA` (ancien répertoire des images et volumes).
Ces emplacements doivent être ceux de l'installation existante : un nouveau
répertoire de données donnerait l'impression que les images et volumes ont disparu.
Ce bloc concerne cette installation rootless, pas un moteur géré autrement.

```sh
python3 - <<'PY'
import os, subprocess
from pathlib import Path
binary = Path(os.environ['MESURE_ENGINE_BIN']).resolve()
runtime = Path(os.environ['MESURE_ENGINE_RUNTIME']).resolve()
data = Path(os.environ['MESURE_ENGINE_DATA']).resolve()
work = Path(os.environ['MESURE_RUNTIME']).resolve()
if not all(path.is_dir() for path in (binary, runtime, data, work)):
    raise SystemExit("Vérifier les répertoires de l'installation existante")
env = dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'],
           XDG_RUNTIME_DIR=str(runtime))
command = [str(binary / 'dockerd-rootless.sh'),
           '--host=' + os.environ['DOCKER_HOST'], '--data-root=' + str(data),
           '--exec-root=' + str(runtime / 'exec'),
           '--storage-driver=fuse-overlayfs', '--pidfile=' + str(runtime / 'docker.pid')]
with (work / 'docker-recovery.log').open('a') as log:
    process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                               stdout=log, stderr=log, start_new_session=True)
print('Processus lancé :', process.pid, '; vérifier le journal puis docker info.')
PY
"$DOCKER_BIN" info --format '{{.ServerVersion}}'
"$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" \
  -f docker/compose.yaml -p "$MESURE_REFERENCE_PROJECT" \
  up -d --no-build --wait --wait-timeout 180
```

Attendre que `docker info` réussisse avant la commande Compose. Un processus
lancé n'est pas encore un moteur prêt. Un fichier socket présent peut être
un vestige d'un moteur arrêté. Ne pas supprimer les volumes pour corriger
une indisponibilité du moteur.

### Conditions pour reprendre la collecte

Conserver les dossiers complets. Examiner tout dossier commencé sans
`serveurs.json` : le pilote refuse de l'écraser. La reprise peut conserver les
paliers terminés, mais ne garantit pas les mêmes conditions qu'une exécution
continue. Le fichier `stop-requested`, s'il existe, bloque un nouveau lancement ;
en examiner la raison avant de préparer une reprise.

Après diagnostic, moteur prêt et preuves conservées, la reprise utilise :

```sh
python3 mesure/scripts/lancer17.py start --runtime ../.runtime-etape17
python3 mesure/scripts/lancer17.py status --runtime ../.runtime-etape17
```

L'interruption observée doit rester signalée dans l'analyse comparative.
Si les écarts suggèrent un effet du changement de séance ou de l'état de
l'hôte, refaire une série complète dans de nouveaux dossiers après stabilisation.
Les paliers conservés sont des mesures réelles ; ils ne prouvent pas que
la série reprise possède les conditions d'une séance ininterrompue.

## Présenter la méthode

Expliquer le parcours métier mesuré, les comptes distincts, les assertions,
la marge observée à l'étalonnage, puis les durées et paliers figés.
Montrer ensuite un `brut.csv`, sa configuration et les trois relevés serveur
du même palier. Enfin, montrer le journal des restaurations et des transitions,
les empreintes communes et l'incident éventuel. Les critères de clôture et la
commande de lecture des seize dossiers sont dans la
[procédure](PROCEDURE.md#campagnes-et-contrôle-final-de-létape-17).

Références : [statistiques PostgreSQL](https://www.postgresql.org/docs/16/monitoring-stats.html)
et [règles d'accès PostgreSQL](https://www.postgresql.org/docs/16/auth-pg-hba-conf.html).
