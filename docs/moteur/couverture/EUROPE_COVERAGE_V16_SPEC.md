# Lot 23 — File de vérification des sources ATS

## Objectif et admission
Vérifier progressivement les candidats du registre avec les connecteurs existants.
Toute l'Europe est éligible, tous secteurs. Pilote de 100 candidats.
`run_ats_probe_worker --enroll 100 --once --limit 100 --report fichier.jsonl`
admet au plus 100 candidats non configurés, de manière idempotente.
Par défaut Greenhouse, Lever et Ashby ; `--providers` sélectionne les autres
connecteurs existants. Ordre déterministe des IDs, sans prétention à prioriser
les entreprises les plus productives. Aucune admission implicite par le worker.

## Vérification
Traitement séquentiel, pause minimale d'une seconde par candidat et budgets HTTP
des connecteurs conservés. Lecture d'un snapshot public et qualification stricte
stage/Europe avant import. Les sources utiles passent à l'importeur normal : une
seconde lecture peut différer, seules les fiches réellement visibles décident
de l'activation. Aucun pays déduit du siège ou du nom d'entreprise.

## Persistance et reprise
AtsProbe : candidat unique, état, tentatives, échéance, erreur, résultat, bail
UUID de 30 minutes. Claim transactionnel skip-locked ; réseau hors transaction.
Arrêt brutal : reprise après expiration du bail. Erreurs codifiées, aucune
exception brute ni credential dans les rapports. Retry-After respecté.
Sans stage confirmé (même snapshot partiel) : nouvelle vérification après 7 jours.
Erreur : backoff de 1 heure à 7 jours. Source active : worker catalogue existant.
Les boards déjà configurés ne sont pas admis automatiquement. enabled=False
arrête une entrée ; un board désactivé après admission reste arrêté.

## Bilan
/coverage/ expose ats_queue, affiché sur /engine : inscrites, testées, actives,
en attente, en erreur, en cours, prochaine vérification et fiches visibles.
JSONL par tentative, dernier état conservé en base. Les compteurs ne démontrent
pas l'unicité entre plateformes. Aucune fusion automatique ni exhaustivité promise.

## Exploitation et validation
Migration 0027_ats_probe_queue. Service Compose ats-probe-worker sans admission
automatique, restart unless-stopped. Worker local avec poll-interval 60, limit 1.
Images Compose non reconstruites. Tests : admission bornée/idempotente, France
acceptée, US exclu, lieu structuré, reprise après bail, attente sept jours,
backoff, reprise après erreur et métriques. Build et tests du bilan desktop/mobile.

## Résultat réel du pilote — 1 octobre 2026
100 candidats vérifiés : 95 sans stage européen confirmé, 5 erreurs (3 HTTP,
1 localisation invalide, 1 réponse trop volumineuse). Zéro activation, zéro
nouvelle fiche visible dans cet échantillon. Il ne représente pas tous les
candidats ni toutes les entreprises européennes ; l'ordre des IDs favorise le
début de l'inventaire. Aucun gain de couverture revendiqué pour ce pilote.

Les neuf sources vides suspendues au lot 21 ont été inscrites explicitement à
une nouvelle vérification dans sept jours, sans réactivation immédiate. Total
file : 109 sources, 100 testées. Rapports : ats-probe-pilot.jsonl,
ats-probe-adopted.json et ats-probe-summary.json dans docs/research/2026-10-01-*.
Worker local lancé et sa lecture de la file vérifiée dans les logs. API publique
vérifiée : ats_queue expose 109 inscrites, 100 testées, 104 en attente, 5 erreurs.
21 tests ciblés passent, build frontend réussi et 2 tests Playwright passent,
dont affichage du bilan et vérification mobile. Ruff et Compose config valides.
Les premiers tests ont rencontré un schéma incomplet pendant les modifications
parallèles de taxonomie ; réexécution réussie après disponibilité de sa migration.
