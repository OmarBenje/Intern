# Couverture Europe V9 — import direct JobTech / Suède

## Objectif

Importer les stages publiés dans Platsbanken depuis l’API publique JobSearch,
avec leur description complète. La découverte `jobsearch_se` existante reste
indépendante : le nouveau provider `jobtech` publie directement les annonces
qualifiées. Ce lot couvre la Suède, pas l’ensemble des sources nationales.

## Contrat de collecte

- API officielle : https://jobsearch.api.jobtechdev.se/swagger.json ; recherche
  `/search`, détail `/ad/{id}`. Aucun identifiant privé nécessaire.
- Quatre recherches : `internship`, `praktik`, `praktikant`, `LIA`, tous secteurs.
- 20 fiches par page, ordre `pubdate-desc`, offset maximal 2000 suivant le
  contrat public. Un plafond atteint remonte `truncated`, jamais une promesse
  d’exhaustivité. Des changements de classement entre pages restent possibles.
- Budget de 240 secondes par page ; lecteur HTTP borné existant, sans redirection.
  Un détail inaccessible empêche l’avancement du curseur et déclenche une reprise.
- Identifiant numérique validé ; le détail doit correspondre au résultat.
  Pas de stockage des listes de contacts ou des coordonnées de l’employeur.

## Qualification et publication

Le pays de recherche ne constitue aucune preuve. La paire de taxonomie
`country=Sverige`, `country_code=199` donne `SE`. Tout autre pays ou combinaison
incomplète reste indéterminé. Ce premier adaptateur ne traduit pas toute la
taxonomie mondiale. Chaque localisation est conservée ; le filtre européen
commun reste obligatoire, avec ses règles prudentes sur le télétravail.

Le titre et la description doivent identifier un stage. Les catégories de
contrat JobTech ne suffisent pas. Les règles `rules-7` ajoutent une corroboration
suédoise : `praktik`, `praktikant` ou `LIA` dans le titre, avec `praktikperiod(en)`,
`praktiken`, `praktikplats` ou `LIA-praktik` dans le texte. Les exclusions explicites
restent prioritaires. Aucun secteur professionnel n’est imposé.

Description d’au moins 40 caractères, employeur identifié, annonce explicitement
non supprimée et date limite valide sont requis. Les dates sans fuseau sont
interprétées en Europe/Stockholm. La date limite est enregistrée sur l’offre ;
l’API publique exclut ensuite automatiquement les offres expirées. Les mises à
jour d’une offre partagée avec une autre source ne remplacent pas sa date canonique.

Lien de candidature : fiche publique Platsbanken. Identité stable par identifiant
JobTech et employeur, réimport idempotent. Les doublons entre différentes plateformes
ne sont pas tous résolus : aucun rapprochement hasardeux par titre seul.

## Exécution et reprise

`run_jobtech_worker --seed-countries SE --once --limit 4` configure les quatre
requêtes puis exécute un passage. Le worker continu utilise `--poll-interval 30
--limit 1`. Lease de dix minutes, contrôle du jeton avant écriture, curseur durable,
nombre total source enregistré, reprise exponentielle respectant Retry-After.
Pages suivantes après cinq minutes ; nouveau cycle après douze heures.

Le scheduler ATS et la découverte ignorent ce provider. Le service Compose
`jobtech-worker` est disponible sous le profil `app`. Les snapshots sont toujours
partiels : absence dans une recherche ne ferme pas une offre. Un détail désormais
supprimé ou non qualifié rend sa source inconnue ; la fraîcheur et la date limite
protègent aussi le catalogue en l’absence d’une nouvelle observation.

## Validation

Tests : taxonomie, preuves suédoises, faux positifs, suppression, expiration,
identité, minimisation des contacts, pagination plafonnée, panne de détail,
idempotence, date persistée, reprise et perte de lease. Résultats du pilote dans
`docs/research/2026-10-01-jobtech-results.json`.

## Suite

Bundesagentur allemande reste à implémenter. France Travail et NAV nécessitent
une vérification de leurs modalités d’accès. Les quatre recherches JobTech ne
prouvent pas l’exhaustivité des stages suédois ou européens.

Validation locale finale : 336 tests backend passent, Ruff sans erreur sur les
fichiers concernés, aucune migration nécessaire, configuration Compose valide.
Backend et frontend répondent HTTP 200 sur `/health/ready/`. Worker JobTech
observé actif. Pilote audité : 24 offres JobTech publiables sur 76 résultats ;
1 821 offres dans le catalogue global à l’instant du rapport, incluant les autres
collecteurs actifs. Ce total n’est pas le nombre d’ajouts du présent lot.
