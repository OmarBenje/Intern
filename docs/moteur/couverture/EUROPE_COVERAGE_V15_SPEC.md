# Lot 22 — Récupérer les stages manqués

## Périmètre et preuves
Audit réseau des dix sources suspendues du lot 21, avec les connecteurs publics
existants et leurs limites. Résultats :
`research/2026-10-01-ats-recall-audit.json` (URL, volume, complétude, titres et liens).
Les résultats vides ne prouvent pas une absence globale de recrutement.
Ryanair renvoie un snapshot partiel vide : aucune conclusion d'exhaustivité.
Les anciennes et nouvelles plateformes Satispay sont traitées séparément.

## Défauts démontrés et corrections
1. L'activation utilisait uniquement `Location.country_code`, même lorsque la
   qualification avait reconnu un pays explicite dans le texte du lieu.
   Utiliser `OfferEnrichment.country_codes` sur les offres déjà publiables.
   Aucun pays déduit du nom d'entreprise ou du siège. Test réel en base :
   `London, United Kingdom` sans code structuré maintient la source active.
2. Certaines offres anglaises ont `Intern` dans le titre et une description
   `As a … Intern`, mais aucune occurrence d'`internship`. La règle ajoutée dans ce lot reconnaît
   cette corroboration, bornée à 100 caractères sans franchir une phrase ou
   un saut de ligne. Un titre seul, `Internal`, ou le mot allemand `intern`
   ne suffit pas. Les exclusions de métiers seniors et événements restent
   prioritaires ; la qualification européenne reste indépendante.

## Exécution et résultats
Celonis (board 1047) réactivé, import public relancé et projections recalculées.
10 fiches visibles : GB 2, ES 3, FR 2, DE 3. Parmi elles, 4 sont nouvellement
qualifiées (ES 1, DE 3) ; les 6 autres étaient encore visibles mais auraient
perdu leur fraîcheur faute de collecte. Ne pas annoncer dix nouveaux stages.
Rapport avec IDs avant/après : `research/2026-10-01-ats-recall-recovery.json`.

Correction du bilan du lot 21 : les six fiches Celonis n'étaient pas toutes
hors pays prioritaires ; les pays reconnus dans les libellés avaient été ignorés
par son compteur. Les rapports initiaux sont conservés comme historique.
Aucun nouveau stage italien ou irlandais confirmé dans cet échantillon.
Les autres sources restent suspendues ; aucun filtre n'est assoupli pour gonfler
le volume. Les connecteurs actifs ont été relancés avec la correction et le worker
catalogue, absent lors de l'inspection, a été relancé.

## Validation
54 tests ciblés passent (qualification, activation, import, collecte, couverture).
Ruff passe ; healthcheck backend HTTP 200. Première suite complète interrompue
par des refus de connexion PostgreSQL puis des erreurs de schéma de test ; une
seconde exécution vérifie son état après rétablissement de la base.

Deuxième suite complète : 410 tests exécutés, 408 réussis et 2 erreurs dans
`WorkflowConcurrencyTests` (création Company en SQL sans `logo_source_url`,
contrainte NOT NULL). Ces tests et le schéma des logos ne sont pas modifiés par
ce lot. Les modifications parallèles du workspace sont préservées ; la suite
complète ne peut pas être déclarée verte.
