# Étape 17 — Campagnes VM et Docker

## Objectif et livrables

Conserver les résultats JMeter bruts des deux déploiements et relever les
métriques serveur pour chaque palier. Deux séries sont prévues, avec inversion
de l'ordre : VM puis Docker, ensuite Docker puis VM.

**Campagne courante : 16 paliers, 22 206 échantillons, zéro erreur et aucun
incident**, vérifiés dans [resultats/campagne/verification.json](resultats/campagne/verification.json).

Les preuves historiques présentées ci-dessous restent les entrées de l’étape 18.

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
python3 mesure/scripts/verifier17.py --runtime ../.execution-campagnes/archives/2026-10-14
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

Le mode opératoire est centralisé dans [EXECUTION.md, étape 17](../EXECUTION.md#étape-17--campagnes).
Depuis Intern :

```sh
bash outils/executer_etape.sh 17 preparer
bash outils/executer_etape.sh 17 lancer
bash outils/executer_etape.sh 17 statut
```

Le dossier privé courant est `../.execution-campagnes/active` et les résultats
courants sont dans `resultats/campagne`. La sélection est conservée entre les
terminaux. Pour contrôler cette campagne sans relancer de charge :

```sh
python3 mesure/scripts/verifier17.py --output mesure/resultats/campagne --runtime ../.execution-campagnes/active
```

Les anciens fichiers privés sont dans `../.execution-campagnes/archives/`.
Les essais interrompus et diagnostics sont rangés dans `resultats/archives/`.
Le dossier `resultats/etape17` conserve les preuves historiques utilisées par
l’analyse de l’étape 18. Les CSV bruts, journaux et empreintes sont conservés.
Le [classement des résultats](resultats/README.md) précise le rôle des dossiers.

Pour demander un arrêt propre : `bash outils/executer_etape.sh 17 arreter`.
Pour archiver une campagne inactive et préparer la suivante :
`bash outils/executer_etape.sh 17 nouvelle`, puis `17 lancer`.
Garder l’hôte allumé, sans mise en veille, et attendre `complete`, seize paliers
et l’événement `reference_restored`. Les erreurs et critères de repos bloquants
sont affichés par `17 statut` et conservés dans le journal.

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
