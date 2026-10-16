# Couverture Europe V3 — iCIMS et Taleo

## Objectif
Importer davantage de stages européens depuis les portails publics employeurs.
Publication inchangée : stage confirmé et localisation européenne explicite.
Aucune promesse d'exhaustivité ; un pays ne se déduit jamais du siège employeur.

## Sources et contrats observés le 30 septembre 2026
- iCIMS : Hines, SAS global, Arthur D. Little internships, Trinseo EMEA.
  Recherche publique `/jobs/search?searchKeyword=intern&in_iframe=1` ; pagination
  `pr` observée dans les liens ; fiches JSON-LD JobPosting. Le paramètre iframe
  correspond au lien public noscript. Identité vérifiée contre l'URL JSON-LD.
- Taleo : AIEA, `https://iaea.taleo.net/careersection/ex/jobsearch.ftl`.
  Identifiant portail lu dans le HTML ; POST public de recherche
  `/careersection/rest/jobboard/searchjobs`, puis fiches `jobdetail.ftl`.
  Ce POST lit les offres et ne soumet aucune candidature.

## Limites et sécurité
Hôtes inspectés uniquement, HTTPS, aucune session candidat ni API recruteur.
iCIMS : 10 pages, 180 détails, 80 Mio cumulés et 600 s ; Taleo : 10 pages,
100 détails et 300 s, réponses bornées. Doublons éliminés par identifiant source.
Les snapshots par mot-clé restent partiels, même sans erreur : aucune fermeture
par absence. Les erreurs initiales font échouer le pilote ; une erreur tardive
conserve les résultats déjà validés avec diagnostic durable.
Les dates explicites déjà expirées sont exclues à la collecte. La politique
commune de fraîcheur reste nécessaire pour les offres antérieurement importées.

## Acceptation
Pays explicite sur chaque localisation, rejet hors Europe et hors stage,
rejet des identités incohérentes, pagination bornée, erreurs réseau visibles,
import idempotent et aucune fermeture par absence. Import réel documenté après
sauvegarde locale ; sources planifiées seulement après pilote réussi.

## Résultat local vérifié

Audit du 30 septembre 2026 à 21:05 UTC : **920 → 928 stages publiés**, toujours
21 pays européens. Nouveaux résultats : Arthur D. Little 5, AIEA 2, Trinseo 1.
Hines et SAS : pilotes réussis mais aucune offre admise par le filtre strict lors
de ce passage. Cela ne prouve pas l'absence de stages chez ces employeurs.
Les titres génériques « Summer Analyst » restent notamment soumis au classifieur
commun ; cette extension n'assouplit pas la règle de publication.

Les cinq boards sont activés et planifiés. Le worker local a été relancé avec les
nouveaux modules ; il doit rester démarré pour exécuter les passages suivants.
282 tests backend passent, Ruff et contrôle des migrations passent. Aucune migration
nouvelle. Sauvegarde locale avant import : `~/.codex/backups/intern-coverage-v3-20260930/before-icims-taleo.dump`.
Preuve : [audit](../../research/2026-09-30-icims-taleo-coverage-audit.json).

La recherche iCIMS est actuellement limitée au mot-clé `intern`. Les autres
langues, les autres tenants Taleo/iCIMS et les portails nationaux restent à étendre
sur la base d'inspections réelles. Les deux familles sont implémentées pour ces
portails précis ; leur couverture européenne n'est pas exhaustive.
