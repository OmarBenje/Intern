# Résultats de mesure

| Dossier | Rôle |
| --- | --- |
| `campagne/` | Dernière campagne exécutée : seize paliers VM/Docker et leur vérification |
| `etape17/` | Preuves historiques utilisées par l’analyse et le rapport de l’étape 18 |
| `etape18/` | Analyse des preuves historiques de `etape17/` |
| `archives/` | Campagnes précédentes et diagnostics, conservés pour leur provenance |

Le travail privé correspondant à la campagne courante se trouve hors du dépôt,
dans `../.execution-campagnes/active/` depuis Intern. Les anciens dossiers privés
sont dans `../.execution-campagnes/archives/`.

`bash outils/executer_etape.sh 17 nouvelle` archive la campagne inactive sous une
date UTC identique dans les deux arborescences, puis prépare la suivante aux
mêmes emplacements standards. `17 lancer` démarre ensuite les mesures.

Les journaux, CSV bruts et configurations de mesure gardent leur contenu d’origine :
les chemins présents dans les traces archivées décrivent leur lieu d’exécution.
Déplacer un dossier ne réécrit pas ces preuves. Les guides de lancement sont
centralisés dans [EXECUTION.md](../../EXECUTION.md).
