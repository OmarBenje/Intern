# Couverture Europe — extension 2

Date : 30 septembre 2026. Périmètre autorisé : premier chantier du backlog,
élargir les sources européennes. Ce lot ajoute les portails publics SAP
SuccessFactors Recruiting Marketing (RMK) vérifiés chez SAP, Schaeffler et ZF.
Il ne prétend pas achever la couverture de tout le marché européen.

## Problème et résultat attendu

Les sept connecteurs existants ignorent les portails RMK de grands employeurs.
Les stages européens qui y sont publiés ne peuvent donc pas entrer dans notre
catalogue. Ajouter une huitième famille de collecte, la découverte de ces sources,
leur enregistrement et leur actualisation par le worker existant.

## Sources observées

- https://careers.sap.com/search/?q=internship
- https://jobs.schaeffler.com/search/?q=internship
- https://jobs.zf.com/search/?q=internship

Les recherches renvoient des liens `/job/.../<id>/`. Les fiches contiennent du
HTML public avec microdonnées `schema.org/JobPosting`, `streetAddress` ou
`addressCountry`, et des zones `data-careersite-propertyid`. Il ne s'agit pas d'une
API SuccessFactors privée. Le portail SAP actuel renvoie aussi vers careers.sap.com
pendant sa migration : https://jobs.sap.com/en/jobs/?experience=Internship.

## Contrat d'import

1. Registre fermé de domaines inspectés ; aucune URL arbitraire, aucun login,
   aucun contournement de refus HTTP. Réutiliser les connexions TLS avec validation
   DNS et hôtes autorisés du collecteur HTML existant.
2. Recherches explicites `internship`, `Praktikum`, `stage`, `tirocinio`.
   Pagination depuis les liens publics observés uniquement. Dédupliquer les IDs
   avant téléchargement des fiches. Limites : quatre pages par terme, 240 IDs,
   80 Mio et 600 secondes. Les titres sans signal lexical de stage sont ignorés
   avant téléchargement ; une annonce au titre non explicite peut donc être manquée.
3. Chaque fiche doit contenir le marqueur JobPosting et un titre/une description
   exploitables. Le pays vient des microdonnées ou d'un code pays explicite dans
   l'adresse structurée de la fiche, jamais du siège ni d'une ville devinée.
4. Passer contrat, description et lieux au classificateur existant. Un stage
   hors Europe, une alternance, un working student ou une localisation ambiguë
   ne devient pas une offre publique. Ne pas déduire le mode de travail.
5. Conserver la provenance et les champs effectivement lus dans la révision
   source. Un doublon d'ID ne crée pas une seconde offre au cycle suivant.
6. Une recherche par mots-clés est toujours un snapshot partiel, même si sa
   pagination semble terminée. Aucune réconciliation d'absence ni fermeture
   d'autres annonces. Une fiche invalide est diagnostiquée sans invalider les
   autres ; un refus ou une limite stoppe les lectures de ce passage.
7. Brancher l'import pilote et le planificateur existants. Réutiliser leases,
   reprise, backoff et règles de fraîcheur. Les anciens workers doivent être
   redémarrés pour charger le nouveau connecteur.

## Recette

- Tests : microdonnées pays/adresse, HTML imbriqué, listes de lieux, absence de
  pays, faux stages, liens hors domaine, pagination répétée ou bornée, fiche
  invalide, snapshot partiel et import idempotent.
- Exécuter les imports publics des trois employeurs et relever leur résultat.
- Comparer catalogue admissible avant/après ; donner le nombre réellement servi
  par l'API, les diagnostics et les employeurs activés. Une erreur d'accès est
  un résultat à rapporter, pas une couverture acquise.
- Tests backend pertinents, vérification Django et absence de dérive de schéma.

## Suite du chantier couverture (hors de ce lot)

Taleo et iCIMS, autres domaines SuccessFactors après inspection, flux nationaux,
accès EURES/JobTeaser/WTTJ, partitions persistantes par ville et fenêtre temporelle,
panel indépendant des stages manqués. Leurs accès et formats doivent être vérifiés
avant de choisir les prochains connecteurs. Le pays de chaque source pilote ne
limite pas le périmètre Europe du produit.

## Livraison et mesures

Implémenté et testé en local le 30 septembre 2026.

| Employeur | Stages européens publiés | Diagnostic |
| --- | ---: | --- |
| Schaeffler | 55 | Recherche par mots-clés, partielle |
| SAP | 21 | Recherche partielle ; quatre pages atteintes pour internship |
| ZF Group | 3 | Recherche par mots-clés, partielle |

Catalogue : **841 → 920**, soit **79 stages supplémentaires**, dans **21 pays**
(la Bulgarie s'ajoute aux 20 pays précédents). Aucun résultat hors des deux critères
obligatoires dans le queryset public audité. La présence sur un portail employeur
ne remplace pas une confirmation humaine du recrutement.

Preuve : `research/2026-09-30-successfactors-coverage-audit.json`.
**272 tests backend réussis**, dont 11 tests du nouveau connecteur ; vérifications
Django réussies, aucune migration nécessaire. Le worker local
`run_catalogue_worker --poll-interval 30 --limit 2` a été lancé avec ce code.
Aucun déploiement distant effectué.

Sauvegarde préalable :
`/Users/omarbenjelloun/.codex/backups/intern-coverage-v2-20260930/before-successfactors.dump`.

Les pilotes ZF et Schaeffler ont précédé l'optimisation de présélection des titres ;
le pilote SAP l'utilise. La fraîcheur continue de gouverner la visibilité des
annonces ; aucune absence dans ces recherches ne les ferme.
La suite du chantier listée plus haut n'est pas déclarée livrée.
