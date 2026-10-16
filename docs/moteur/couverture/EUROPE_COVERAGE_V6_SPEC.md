# Couverture V6 — EURES

## Objectif
Importer directement les stages EURES, tous secteurs, en conservant les frontières
stage confirmé et pays européen prouvé. EURES est une source supplémentaire, pas
une preuve d'exhaustivité du marché européen.

## Contrats
- Requête publique POST /eures/api/jv-searchengine/public/jv-search/search :
  positionOfferingCodes=[internship], pays EURES, pages de 20, tri récent.
- Lire la fiche publique par identifiant avant import. Seuls les champs utiles à
  l'offre sont conservés ; pas de carnet de contacts ou de fiche personne.
- Le pays et la ville proviennent de locations dans le profil de la fiche, jamais
  du pays demandé. Code EL ramené à GR. Les localisations multiples sont conservées.
- Le code contrat doit être exactement internship. Apprenticeship/trainee/traineeship
  ne sont pas assimilés à un stage ; les exclusions du classificateur s'appliquent.
- Description réelle et employeur renseigné requis. Aucun texte synthétique ne
  remplace une fiche absente. Fiche 404 ou invalide enregistrée comme résultat invalide.
- Import commun : source EURES par employeur, identifiant stable par annonce,
  révisions, qualification et fraîcheur habituelles. Idempotence inter-pages et
  inter-requêtes. La fusion floue entre plateformes reste hors périmètre.

## Ordonnancement
DiscoveryQuery provider=eures, une requête par pays, langue en (langue de demande,
pas filtre sur les langues des annonces). Curseur persistant ; lease de 10 minutes.
Réseau hors transaction, vérification du lease avant import et avancement du curseur.
Une erreur réseau sur les détails empêche l'avancement de la page ; reprise avec
backoff et Retry-After. Un HTTP 400 ou 307 n'est jamais traité comme liste vide.
Une réponse 200 de schéma valide avec total=0 constitue un passage réussi vide.

Un passage : 20 détails maximum, 240 secondes, 2 Mio par réponse, aucun redirect.
Reprise après 5 minutes entre pages, cycle suivant après 12 heures. Plafond de
200 pages par pays, indicateur truncated si le plafond est atteint. Les recherches
sont toujours partielles et ne ferment pas d'offres par absence. Une annonce non
revérifiée finit masquée par le filtre commun de fraîcheur. L'ordre des résultats
peut changer pendant un cycle ; le cycle suivant repart de la première page.

Le worker EURES est indépendant. Les workers catalogue et découverte ATS excluent
ses requêtes et ses sources ; ils ne doivent pas les importer en parallèle.
Aucune migration et aucune dépendance supplémentaire.

## Commandes
```sh
uv run python manage.py run_eures_worker --seed-countries DE BE FI --once --limit 3
uv run python manage.py run_eures_worker --poll-interval 30 --limit 1
```

## Recette
Tester géographie, contrat ambigu, employeur manquant, identité de fiche différente,
protection des contacts, flux vide confirmé, erreur sur détail, reprise du curseur,
lease perdu, source désactivée, imports répétés, absence dans une recherche partielle.
Mesurer les sources EURES publiables séparément des autres workers actifs.

## Sources inspectées
- Endpoint public testé en lecture : https://europa.eu/eures/api/jv-searchengine/public/jv-search/search
- Référence de protocole : https://github.com/kalil0321/ats-scrapers/blob/6b44a1badc9bfbf5cf176f75265cc5729e520e99/src/ats_scrapers/scrapers/eures.py

L'implémentation locale ne reprend pas la conversion apprenticeship/trainee en
internship du scraper de référence. Le paquet ats-scrapers n'est pas installé.

## Correction après pilote et résultat
Le pilote live a démontré que le code internship d'EURES est bruité : certains
emplois étudiants, apprentissages et emplois permanents portent ce code. La
qualification locale ignore donc ce code comme preuve suffisante et exige aussi
une confirmation textuelle. Le champ contract_type local reste unknown ; la
qualification est calculée sur le titre et la description. Un détail nouvellement
refusé rend sa source existante unknown et la retire de la publication.

Première collecte : 41 détails (DE 20, BE 16, FI 5). Le contrôle initial trop
permissif avait admis 36 fiches ; leurs sources ont été suspendues et requalifiées
avant remise en service. Résultat corrigé : **13 stages publiables**, DE 4, BE 8,
FI 1. Les autres fiches restent hors publication, même si EURES les qualifie de
stage. Rapport : `research/2026-10-01-eures-pilot.json`.

315 tests backend passent ; Ruff et validation Compose passent ; aucune migration.
31 pays configurés pour le worker dédié. Configuration Compose ajoutée, sans
reconstruction de l'image Docker ; exploitation locale via uv.
Sauvegarde : `~/.codex/backups/intern-coverage-v6-20261001/before-eures.dump`.
