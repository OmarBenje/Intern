# Couverture V5 — Teamtailor et Workable

## Objectif et périmètre
Ajouter deux familles de portails employeurs au moteur et au registre existants.
Tous domaines ; publication uniquement via la qualification commune stage confirmé
et localisation européenne. Les autres pistes de la recherche (EURES, WTTJ,
Eightfold et sources nationales) restent des lots distincts non implémentés ici.

## Collecte
- Teamtailor : flux RSS du sous-domaine officiel, titre, description HTML convertie
  en texte, identifiant numérique, toutes les localisations et statut remote.
- Workable : widget public, regroupement des localisations par shortcode, détails
  Markdown lus séquentiellement pour les contrats ou titres de stages potentiels.
  Trainee seul ne devient jamais un stage. Description manquante = erreur, pas import.
- Domaine et identifiants contrôlés ; aucune redirection réseau suivie. Aucun
  accès authentifié, installation d'ats-scrapers ou contournement d'accès.
- Workable : 120 détails maximum, 300 secondes, 2 Mio par réponse et 20 Mio par
  passage. HTTP 429 arrête la collecte des détails. Les erreurs sont conservées.
- Snapshots partiels : ni RSS ni widget ne fournissent ici une preuve d'exhaustivité
  suffisante pour fermer une offre absente. Les offres non revérifiées sont masquées
  par le filtre de fraîcheur commun.

## Intégration
Reconnaissance des URL, importeur commun, ordonnanceur et registre CSV étendus.
Les URL de détail sont ramenées au portail. Le registre reste épinglé à la révision
`6b44a1badc9bfbf5cf176f75265cc5729e520e99`. Les CSV déclarent 1 464 portails Teamtailor
et 4 752 Workable : ce ne sont ni des portails actifs vérifiés ni des stages.
Aucune migration ni nouvelle dépendance.

## Critères de recette
- Flux invalide, XML dangereux, identifiant malformé et URL usurpée refusés.
- Plusieurs lieux conservés, télétravail explicite conservé, aucun pays déduit
  du siège employeur ou du pays demandé.
- Absence de description et erreur réseau ne publient pas de fiche vide.
- Imports répétés idempotents ; absence dans un flux partiel ne ferme rien.
- Pilotes réels identifiés et gains attribués à leurs sources ; ne pas attribuer
  aux nouveaux connecteurs les imports des workers déjà en cours.

## Exploitation
```sh
uv run python manage.py register_source https://acme.teamtailor.com --company Acme --enable
uv run python manage.py register_source https://apply.workable.com/acme --company Acme --enable
uv run python manage.py import_ats_registry --providers teamtailor workable --limit 250
```
Les exemples Acme sont des placeholders. Les candidats sans activation ne sont pas
collectés. Les domaines carrières personnalisés doivent encore être résolus vers
leur tenant officiel ; leur seule présence ne suffit pas à une activation.

## Références
Protocoles étudiés dans les adaptateurs publics, implémentation locale adaptée aux
contrats de sécurité, de qualité et d'import d'Intern :
- https://github.com/kalil0321/ats-scrapers/blob/6b44a1badc9bfbf5cf176f75265cc5729e520e99/src/ats_scrapers/scrapers/teamtailor.py
- https://github.com/kalil0321/ats-scrapers/blob/6b44a1badc9bfbf5cf176f75265cc5729e520e99/src/ats_scrapers/scrapers/workable.py

## Recette complémentaire
La règle `rules-6` reconnaît un titre de stage anglais avec une preuve explicite
française dans la description (`votre stage`, `stage de 6 mois`, etc.). Les termes
ambigus seuls et les exclusions graduate/apprentissage restent inchangés.
Le parseur de découverte LinkedIn tolère les attributs HTML `class` et `style`
sans valeur ; ils avaient interrompu le worker réel.

304 tests backend passent sur PostgreSQL, Ruff passe, aucune migration à créer.
Sauvegarde avant pilotes :
`~/.codex/backups/intern-coverage-v5-20260930/before-new-ats.dump`.
Deux lots de 250 candidats ont été enregistrés, Teamtailor puis Workable.
Six portails pilotes : cinq imports réussis, Talan suspendu après erreur HTTP.
Stages visibles issus des nouveaux connecteurs : Fifty-Five 4, Flowdesk 1,
Sézane 17 ; Swan et Skeepers 0. Les 18 annonces stockées de Swan ne sont pas
publiées comme stages. Résultats et limites dans les rapports JSON V5.

Le backend et les deux workers ont été relancés ; les routes de santé backend et
proxy frontend répondent HTTP 200. Contrairement à l'état historique de V4,
Docker/PostgreSQL sont disponibles lors de cette recette.

Pilotes du registre Workday existant terminés : Philips 39 stages visibles, Thales
60 ; Red Hat et Orange suspendus (`country_facets_unavailable`). Les portails
pilotes fournissent donc 121 offres visibles au total, avant éventuelle fusion de
copies entre plateformes. Le catalogue complet affiche 1 290 offres au contrôle
2026-09-30 21:57 UTC ; son augmentation ne doit pas être attribuée intégralement à
V5, les autres workers étant actifs pendant la recette.
