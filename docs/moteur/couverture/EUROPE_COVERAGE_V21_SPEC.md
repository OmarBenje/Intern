# Lot 28 — Vérification du contrat de stage

## Règles
rules-17 ne confirme plus une annonce sur le seul champ ATS internship.
Il faut un titre de stage reconnu ou une formulation de la description qui
décrit le stage proposé. Préserver les titres atypiques Wavestone, Deloitte,
Coface et les variantes néerlandaises, suédoises et hongroises corroborées par ATS.
Les mentions d'une expérience de stage passée ne suffisent pas.

Alternance (y compris _Alternant), Student Marketeer et événements Hackathon sans
rôle de stagiaire deviennent not_internship. Les intitulés proposant explicitement
stage et alternance (séparateur / ou virgule) restent uncertain. CDI/CDD explicite du poste proposé :
not_internship sans preuve de stage ; uncertain si la même offre présente aussi
un stage. Une perspective d'embauche après le stage, le statut des collègues ou
un CDI explicitement exclu ne constituent pas une contradiction.

## Publication et revue
La politique existante ne publie que confirmed/in_scope. uncertain reste conservé
pour revue, sans changement du cycle de vie et sans suppression. Les anciens
masquages manuels restent en place. Motif et extrait littéral dans facts.classification.
Le registre en lecture seule /admin/jobboard/offerenrichment/ permet de filtrer
les cas à vérifier et de lire leur motif (permissions opérationnelles existantes).
La fiche publique affiche les motifs des preuves lorsqu'elle est publiable.
Aucun nouveau droit d'accès public aux annonces exclues.

## Audit
audit_internship_contracts --report nouveau.json prévisualise les classifications
sur les IDs retenus au démarrage ; --apply recalcule les projections modifiées
avec enrich_offer, sans réseau ni mutation des sources ou statuts.
Rapport de progression par lots de 250, transitions, preuves et IDs visibles avant/
après. Les collecteurs peuvent faire évoluer le catalogue pendant le passage.
Relancer avec un nouveau fichier après interruption ; ne pas réutiliser un rapport.

## Validation
Corpus figé de 52 annonces publiques réellement contrôlées : 18 exclusions du
lot 27 et 34 vrais stages incluant les cas de conversion en CDI et des intitulés
atypiques. Tests synthétiques de contradictions, faux conflits, contrat seul,
événements et titres multilingues. Tests des adaptateurs, import et file ATS.
Les règles sont déterministes et conservatrices ; elles ne couvrent pas toutes
les formulations ni toutes les langues européennes.

## Résultat réel — 1 octobre 2026
15 726 fiches retenues réauditées au dernier passage. 26 fiches auparavant
publiées sont désormais uncertain : 19 contrats ATS sans confirmation textuelle,
5 intitulés stage/alternance et 2 intitulés ou textes à contrat contradictoire.
Ce sont des cas à vérifier, pas 26 faux stages démontrés. Les 18 masquages manuels
du lot 27 sont préservés et aucune de ces 18 annonces n'est encore confirmed.
Les 34 vrais stages du corpus restent confirmed après l'application en base.

Catalogue observé : 7966 avant le premier passage, 7941 après la vérification
finale. La baisse nette de 25 inclut une nouvelle fiche apparue pendant l'activité
des autres collecteurs ; les 26 IDs retirés sont consignés séparément.
Aucune suppression d'annonce ni modification de son statut par l'audit.

Premier rapport rules-16 conservé. La revue finale rules-17 corrige les contrats
mixtes en uncertain au lieu de not_internship (13 fiches sur tout le corpus,
dont cinq qui étaient publiées avant le premier audit). Les deux passages sont
conservés pour expliquer exactement les transitions.

Validation : 50 tests backend ciblés passent, dont les 52 annonces réelles ;
un test navigateur valide le motif affiché dans les preuves ; build frontend,
contrôle Django et diff-check passent. Collecteurs ATS et catalogue relancés avec
rules-17, disponibilité backend vérifiée HTTP 200.

Rapports :
- research/2026-10-01-contract-quality-audit.json : premier passage appliqué.
- research/2026-10-01-contract-quality-final.json : revalidation finale.
- research/2026-10-01-contract-quality-summary.json : bilan, IDs retirés,
  vérification des 18 exclusions et des 34 stages protégés.

## Limites
Les formations, missions estivales et termes non reconnus peuvent rester
uncertain. Les labels de contrat restent des indices, jamais une garantie
d'exactitude de l'employeur. Les règles ne démontrent pas l'absence de faux
positifs dans tout le catalogue ; elles rendent les incertitudes observées
explicites et empêchent les 18 cas de régression de redevenir publiables.
