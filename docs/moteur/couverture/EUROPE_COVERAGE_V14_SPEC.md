# Lot 21 — Activation ciblée des entreprises ATS

## Objectif
Augmenter les stages européens visibles via les connecteurs existants. Priorités :
Italie, Pays-Bas, Espagne, Royaume-Uni et Irlande, tous secteurs. Aucun quota
artificiel ni assouplissement des preuves stage/localisation.

## Exécution
`activate_ats_candidates --ids … --report fichier.json` prévisualise un choix
explicite de 1 à 10 candidats non configurés. `--execute` effectue les imports.
La sélection est une piste, jamais une preuve de localisation : seuls les lieux
des offres qualifiées déterminent le rendement dans les pays ciblés.

Chaque source est traitée avec les connecteurs, budgets, leases et qualification
existants. Un import en échec est suspendu par le service de validation existant.
Un import sans stage visible dans les pays ciblés est mis en pause. Les sources
déjà configurées sont refusées pour préserver les choix opérateur.

## Mesure et reprise
Rapport écrit avant mutation et après chaque source : IDs candidat/board, URL,
erreur, offres visibles, offres des pays ciblés et nouveaux IDs visibles. Les
changements des autres workers ne sont pas attribués au lot. Les doublons entre
plateformes restent possibles : ces compteurs ne prouvent pas des stages uniques.
Après interruption, relancer uniquement les IDs non configurés ; inspecter une
entrée `running` avant toute reprise. Pas de worker permanent supplémentaire.

## Validation
Tests : prévisualisation sans mutation, budgets, sources existantes préservées,
activation avec stage cible, suspension sans stage cible et poursuite après erreur.
Pilotes réels documentés dans `docs/research/2026-10-01-ats-expansion-*.json`.

## Résultat vérifié — 1 octobre 2026
13 sources testées, 3 retenues en collecte continue : Deloitte Netherlands,
Cabify, Picnic. Après contrôle qualité : 48 nouvelles fiches visibles sur ces
sources, dont 37 dans les pays prioritaires (36 NL, 1 ES). Les 11 autres sont
européennes hors pays prioritaires. Aucun gain confirmé IT/GB/IE dans ce pilote.
10 sources mises en pause, dont Celonis : ses 6 fiches européennes hors cibles
restent temporairement visibles jusqu'à expiration de leur fraîcheur et ne sont
pas comptées dans le gain des sources retenues.

Sept événements/programmes Deloitte avaient été acceptés via le contrat ATS.
La règle `rules-8` exclut désormais les titres Career Week/Fair, Business Course
et Talent Class, même avec un contrat `internship`. Les stages en organisation
d'événements restent acceptés. Projection recalculée pour le lot et les titres
concernés du catalogue. Les rapports initiaux sont conservés ; le fichier
`ats-expansion-verified.json` porte les compteurs après correction.

374 tests backend passent ; Ruff et Django check passent. API et frontend
retournent 200 sur leur healthcheck. Collecteurs locaux relancés avec rules-8.
Audit de liens : zéro rapprochement assez certain pour proposer une fusion.
Aucune garantie d'unicité entre plateformes ni d'exhaustivité des pays.
