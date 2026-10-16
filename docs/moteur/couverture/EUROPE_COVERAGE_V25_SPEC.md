# Lot 32 — Diagnostic par source et trois pertes confirmées

## Mesure
Commande `audit_source_funnel --report nouveau.json`, en lecture seule, tous les
boards enabled (incluant les boards en pause, signalés). Une partition exclusive
des lignes OfferSource persistées : source inactive/périmée, offre masquée/fermée,
non-stage, stage incertain, hors Europe, géographie incertaine, expirée, publiée,
autre règle. Statistiques indépendantes stage/Europe, dernier import et ses
limites, exemples bornés, classement par volume à examiner. Un nombre incertain
n'est pas un nombre de stages perdus. Les totaux par source peuvent se recouper.
Le nombre normalisé n'est pas le nombre brut upstream : les collecteurs qui
préfiltrent ne permettent pas de reconstruire rétrospectivement ce compteur.

## Trois corrections
1. Lever : utiliser le pays ISO explicite uniquement pour le lieu principal qui
   correspond exactement au libellé categories.location. Ne pas l'appliquer aux
   lieux secondaires. Conserver remote et le fallback explicite du lot 31.
2. Greenhouse : reconnaître une liste séparée par virgules uniquement si la
   métadonnée multi_select Locations confirme tous ses éléments. Rapprocher chaque
   élément d'une adresse d'office correspondante. Aucun simple découpage qui ferait
   confondre Paris, Texas avec Paris en France ; ne pas ajouter d'offices hors liste.
3. Classification danoise : titre Praktikant/videopraktikant + mention explicite
   d'une période de stage (Praktikperiode:) dans le descriptif. Priorités des
   exclusions et contradictions inchangées. Version rules-18, preuve littérale.

## Validation réelle
Instantanés publics Winamax, Qube et WPP Media, projection avant/après, tests des
contre-exemples géographiques et contrats. Rafraîchir seulement ces trois boards,
puis compter les fiches nouvellement visibles, réévaluer les titres ambigus et
les doublons possibles. Rapports conservés avant/après, aucune promesse de volume.

## Résultat exécuté

1615 boards activés en configuration audités, y compris les sources vides ou en
pause explicitement signalées. Avant : 8134 lignes sources publiées, 5615 stages
incertains, 75 géographies incertaines ; ces incertitudes ne sont pas 5690 stages
récupérables. Les trois pertes corroborées par flux public ont été priorisées :
WPP Media 17, Qube 4, Winamax 2. Imports réels complets : 977, 199 et 29 annonces
normalisées respectivement. Catalogue 8134 → 8157 fiches visibles (+23).

Les 23 fiches couvrent DK 18, FR 6, GB 4 : les pays se recoupent. Qube comprend
une annonce donnant explicitement accès à un stage de 3–6 mois, un placement
industriel ou un poste graduate ; son titre original reste visible. Le compteur
est celui des fiches, pas des postes uniques. Trois groupes de titres suspects,
zéro fusion certaine proposée, aucune fusion réalisée.

68 tests ciblés, lint ciblé, Django check et build frontend passent. Motif danois
traduit dans la vue des preuves et l'administration. Rapports before/projection/
pilot/after/results sous `docs/research/2026-10-01-source-funnel-*`.
