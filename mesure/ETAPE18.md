# Étape 18 — Analyser et comparer

## Objectif

Établir l'écart entre les VM et Docker, l'expliquer à partir des mesures et
indiquer leurs limites. La structure du rapport conserve le travail demandé,
le tableau de synthèse et les quatre questions d'analyse dans leur ordre.

## Travail réalisé et livrables

| Livrable | Emplacement |
| --- | --- |
| Rapport rédigé et tableau de synthèse rempli | [Markdown](docs/rapport-charge.md) |
| Rapport A4 de quatre pages | [PDF](docs/rapport-charge.pdf) |
| Trois courbes regroupées, deux séries visibles | [PNG](docs/courbes/ensemble.png), [PDF](docs/courbes/ensemble.pdf) |
| Débit selon les utilisateurs | [PNG](docs/courbes/debit.png), [SVG](docs/courbes/debit.svg) |
| Latence au 95e centile | [PNG](docs/courbes/latence-p95.png), [SVG](docs/courbes/latence-p95.svg) |
| Taux d'erreur | [PNG](docs/courbes/erreurs.png), [SVG](docs/courbes/erreurs.svg) |
| Calculs des écarts et empreintes d'entrée | [JSON](resultats/etape18/analyse.json), [CSV](resultats/etape18/comparaison.csv) |
| Empreintes des douze artefacts d'analyse | [SHA256SUMS](resultats/etape18/SHA256SUMS) |
| Analyse et export reproductibles | [Analyse](scripts/analyser18.py), [export PDF](scripts/generer_rapport18.py) |

## Résultat et limites

À vingt utilisateurs, les débits moyens sont 19,479 consultations/s pour les
VM et 19,642 pour Docker, soit +0,83 % pour Docker. Les p95 sont respectivement
44/29 ms et 20,25/20 ms, selon les séries. Les erreurs restent nulles.

**Saturation non observée dans la plage de 1 à 20 utilisateurs.** Les courbes
portent cette indication. La charge de saturation et le premier goulot serveur
ne sont donc pas déterminés. Le métier est le service le plus chargé en CPU
mesuré, sans saturation démontrée. Le rapport distingue le plafond du profil
avec réflexion d'une limite du serveur ; il ne transforme pas le dernier palier
en point de saturation.

L'incident Docker, la variation de latence VM, les différences de ressources
et de compteurs CPU/I/O sont conservés dans l'analyse. Le démarrage et la mémoire
au repos sont repris des mesures des étapes 10 et 14, avec leurs périmètres.
La collecte vérifiée n'établit ni la capacité maximale ni une tenue en production.

## Reproduction et vérification

Depuis la racine d'Intern, dans un environnement Python disposant de la
[dépendance graphique](requirements-analyse.txt) :

```sh
# Installation seulement si Matplotlib est absent de l'environnement choisi.
python3 -m pip install -r mesure/requirements-analyse.txt
python3 mesure/scripts/analyser18.py
python3 mesure/scripts/generer_rapport18.py
pdfinfo mesure/docs/rapport-charge.pdf
(cd mesure && sha256sum -c resultats/etape18/SHA256SUMS)
```

L'analyse revérifie les seize paliers depuis les fichiers bruts, sans modifier
les archives de l'étape 17. Elle conserve les répétitions séparées et calcule
les écarts Docker/VM à charge égale. Elle produit les courbes, les calculs et
les empreintes des sources. Le rapport Markdown est la source rédigée ; vérifier
ses chiffres et son interprétation si les campagnes sont remplacées.
L'export PDF reprend cette source et refuse une page qui déborde ; quatre pages
A4 doivent être annoncées par `pdfinfo`. Aucun service ni aucune charge ne sont
relancés par ces deux scripts.

Les liens, l'intégrité des résultats d'entrée, les quatre pages PDF et leur
mise en page ont été vérifiés. La [procédure](PROCEDURE.md) décrit aussi les
prérequis et les contrôles des étapes précédentes.
