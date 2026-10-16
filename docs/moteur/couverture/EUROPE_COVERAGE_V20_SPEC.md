# Lot 27 — Admission ATS priorisée par couverture européenne

## Objectif
Tester jusqu'à 100 nouveaux employeurs déjà associés à un stage européen publié,
en privilégiant les pays les moins représentés. Mesurer les fiches effectivement
visibles après contrôle, sans les assimiler à des stages uniques entre plateformes.

## Sélection
Extension de discover_ats_from_offers avec --prioritize et limite maximale 100.
Compter les offres publiables par pays européen, une occurrence par offre/pays.
Collecter les liens ATS reconnus et les correspondances exactes de noms dans les
inventaires épinglés de tous les connecteurs. Classer toutes ces pistes ensemble
par le plus faible effectif des pays de leur offre témoin ; à égalité, lien dans
l'annonce avant correspondance de registre, puis ordre stable des IDs/URLs.

Un nouveau portail par employeur normalisé (casse) dans ce passage. Exclure les
boards déjà configurés et préserver les probes existants, délais et arrêts.
Conserver origine, offre témoin, pays, score et empreinte de registre dans les
preuves et le rapport. Une correspondance de registre reste une piste dont
l'identité est à contrôler. Pas de rapprochement flou ni d'URL inventée.
Signaler tout déficit si moins de 100 nouvelles entreprises sont disponibles.
Les pays sans offre témoin ne peuvent pas être découverts par cette méthode.

## Exécution et vérification
File AtsProbe existante, préfiltrage stage/Europe inchangé, reprises et backoff
existants. Traitement ciblé des IDs admis ; suivi des workers concurrents par état
persistant, jamais par nombre de lignes du journal uniquement. Contrôler les
portails productifs et mettre à l'écart les conflits d'identité. Rapport avant/
après avec IDs visibles, nouveaux IDs, pays européens, états et erreurs.
Les statistiques de catalogue global peuvent évoluer pendant le passage.

## Validation prévue
Tests du classement entre fournisseurs, déduplication des employeurs, limites,
absence d'assouplissement du filtre stage/Europe et non-réinscription des probes.
Exécution réelle, bilan d'erreurs et de sources vides compris. Pas de promesse
de 100 portails productifs ni d'exhaustivité européenne.

## Résultat réel — 1 octobre 2026
100 pistes inscrites (toutes par nom exact dans le registre), aucun déficit.
50 portails actifs, 34 en attente de revérification, 16 erreurs avec backoff.
520 nouvelles fiches encore publiables après contrôle, sur 17 pays : FR 344,
DE 79, IT 20, ES 15, GB 14, NL 12, AT 8, BE 7, CH 7, IE 4, NO 2, PL 2,
PT 2, GR 1, LU 1, RO 1, SE 1. Ce sont des fiches, pas un décompte prouvé de
stages uniques entre plateformes. La priorité au pays témoin ne garantit pas
que le portail recrutera dans ce même pays.

Principaux apports : Wavestone 130, Pernod Ricard 95, Coface 32, Drees & Sommer 29,
Sia 24, Red Bull 23. Le catalogue observé passe de 7420 à 7949 ; l'écart global
de 529 inclut l'activité des autres workers et ne doit pas être attribué au lot.

18 fiches ont été masquées durablement après revue : contrats contradictoires,
alternance, événement, emplois étudiants ou description insuffisante pour
corroborer le contrat ATS. Les raisons et empreintes sont conservées dans le
rapport d'exclusions. Le classificateur et les connecteurs n'ont pas été modifiés
dans ce lot : ces erreurs de contrat à la source constituent une limite restante.
Les intitulés atypiques conservés ont été contrôlés dans leur description :
stage explicite Wavestone, Audit Academy Deloitte, Red Bull Creators et Coface ;
formation pratique juridique de 3–6 mois chez TYTAN. Aucun conflit d'identité
employeur trouvé lors du contrôle des portails productifs ; vérification par
données d'entreprise ATS et échantillons de descriptions, pas audit exhaustif
indépendant de chaque employeur.

11 erreurs Workday country_facets_unavailable et 5 upstream_http_error.
Les sources vides/partielles restent à revérifier : un résultat vide ne prouve pas
l'absence de stages. Aucune tentative de contournement.

17 tests ciblés passent (découverte et file ATS), lint et diff-check valides.
Aucune migration ni modification frontend nécessaire.

## Preuves
- research/2026-10-01-prioritized-discovery.json : sélection, pays témoins et scores.
- research/2026-10-01-prioritized-before.json : IDs visibles avant le pilote ciblé.
- research/2026-10-01-prioritized-pilot*.jsonl : journaux des traitements ciblés.
- research/2026-10-01-prioritized-results.json : états persistants des 100 probes,
  nouvelles fiches encore visibles, titres et pays, bilan global séparé.
- research/2026-10-01-prioritized-exclusions.json : 18 exclusions motivées.
- BRANDUNG : identité confirmée sur sa [fiche Personio publique](https://brandung.jobs.personio.de/job/2744965),
  qui rattache le projet Solia au recrutement BRANDUNG (consultée le 1 octobre).
