# Preuves de mesure à présenter au professeur

Ce dossier léger est destiné à Git. Son fichier `SHA256SUMS` permet de vérifier
les copies publiées avec `sha256sum -c SHA256SUMS` depuis ce dossier. Les CSV bruts volumineux restent dans les
campagnes locales ignorées par Git et dans une archive séparée à remettre avec
le rendu. Les fichiers privés `.execution/` et `../.execution-campagnes/` ne
font partie ni de ce dossier ni de l’archive de résultats.

## Campagnes retenues

| Campagne réelle | Rapport | Portée |
|---|---|---|
| Capacité VM/Docker, 18–19 octobre 2026 | [Rapport](capacite-20261018-195024-455892/analyse/rapport.md), [PDF](capacite-20261018-195024-455892/analyse/rapport.pdf) | 48 paliers ; capacité maximale non validée, répétitions divergentes et interruption documentée. |
| Workers Docker, 19 octobre 2026 | [Rapport](worker-20261019-103419-13231/rapport-workers.md) | 2/4 workers à 150, 180 et 200 utilisateurs ; amélioration observée avec 4 workers, limites de répétabilité conservées. |
| Workers VM, 19 octobre 2026 | [Rapport](worker-vm-20261019-143401-202396/rapport-workers.md) | 2/4 workers à 80, 100 et 130 utilisateurs ; 12 essais valides, zéro erreur, critère strict de répétabilité non satisfait pour certains p95. |

Chaque sous-dossier contient le protocole figé, les synthèses client/serveur et
`inventaire-bruts.csv` : chemin, taille et SHA-256 de chaque fichier de preuve
retenu. `SOURCE.json` identifie la campagne et l’empreinte de son manifeste
original. Le `manifest.json` publié est un extrait : les diagnostics de commandes
privés sont retirés. Son contenu ne doit pas être confondu avec le manifeste
original dont l’empreinte est donnée dans `SOURCE.json`.

Les anciennes tentatives et campagnes échouées restent conservées sur la machine.
Les incidents sont exposés dans [INCIDENTS.md](../INCIDENTS.md) et les audits.
La campagne de capacité retenue conserve dans l’archive ses tentatives remplacées.

## Archive à remettre séparément

L’archive locale est `../../../preuves-mesures/preuves-mesures-20261019.tar.gz`
(depuis ce dossier, soit `../preuves-mesures/` depuis la racine Intern).
Son nom et son empreinte figurent dans [ARCHIVE-SHA256.txt](ARCHIVE-SHA256.txt).
Elle contient les données originales des trois campagnes : résultats JMeter,
relevés serveur et hôte, configurations de mesure, manifestes, journaux d’événements
et comptes **fictifs** du protocole. Les journaux Java privés, secrets Docker/SSH,
snapshots SQL privés, sources privées et disques VM sont exclus.

Avant remise, copier l’archive et son fichier `.sha256` sur l’ENT ou un stockage
partagé accessible au professeur, puis fournir ce lien avec celui du dépôt.
Le lien distant n’est pas encore configuré et aucun fichier n’a été téléversé.

Après téléchargement, depuis le dossier contenant les deux fichiers :

```bash
sha256sum -c preuves-mesures-20261019.tar.gz.sha256
mkdir preuves-brutes
tar -xzf preuves-mesures-20261019.tar.gz -C preuves-brutes
```

Les chemins de chaque `inventaire-bruts.csv` sont relatifs à la campagne extraite.
Le professeur peut recalculer les statistiques à partir des CSV et confronter
les chiffres aux rapports. Les empreintes détectent une modification ; elles
ne prouvent pas à elles seules l’authenticité d’une exécution ou une validation
pédagogique. Une démonstration et une nouvelle mesure restent possibles avec
les scripts et prérequis documentés dans [WORKERS.md](../WORKERS.md).

## Ce qui va dans Git

- Code, tests, plans JMeter, protocoles, procédures et analyse des incidents.
- Ce dossier de preuves, rapports et synthèses de quelques mégaoctets.
- Les preuves historiques des étapes 15–18 déjà suivies, conservées ici sans
  suppression : le nouvel ignore ne retire pas de fichiers de l’historique.

Les dossiers locaux `mesure/resultats/capacite-*` et `mesure/resultats/worker-*`
sont ignorés. Ne pas utiliser `git add -f` pour les ajouter.

Pour régénérer la sélection légère :

```bash
python3 mesure/scripts/exporter_preuves.py
```

Pour créer une nouvelle archive, choisir un chemin neuf hors du dépôt :

```bash
python3 mesure/scripts/exporter_preuves.py --archive ../preuves-mesures/preuves-mesures-NOUVELLE-DATE.tar.gz
```

L’exporteur refuse d’écraser une archive existante et d’exporter une campagne
active. Une nouvelle campagne doit être sélectionnée explicitement avec
`--campagnes NOM1 NOM2 NOM3` ou ajoutée à la sélection du script.
