# Étalonnage — nouvelle exécution

Début des mesures : 2026-10-16T17:57:32.797873+00:00 (UTC). Les configurations exactes, dates et
empreintes sont conservées dans les sous-dossiers et dans `etalonnage.json`.

| Essai | Débit réussi (req/s) | p95 (ms) | Erreurs |
| --- | ---: | ---: | ---: |
| statique-1 | 442.917 | 6.00 | 0 |
| statique-20 | 1855.800 | 23.00 | 0 |
| controle-1 | 9.642 | 51.20 | 0 |
| controle-2 | 9.617 | 50.00 | 0 |

Écart entre contrôles : débit 0.26 % ;
p95 2.37 %.
Critère de répétabilité (écarts ≤ 10 %, aucune erreur) :
**réussi**.

Ce rapport porte uniquement sur ces quatre essais. Il ne valide pas une
nouvelle campagne VM/Docker, une saturation ni l’approbation pédagogique.
Les preuves archivées dans `mesure/resultats/etape16` restent distinctes.
