# Lot 20 — NAV / Arbeidsplassen, Norvège

## Objectif et accès

Importer les stages depuis le flux officiel NAV, tous secteurs, avec leurs
modifications et retraits. Documentation : https://navikt.github.io/pam-stilling-feed/ .
Conditions de réutilisation : https://arbeidsplassen.nav.no/vilkar-api .

Le flux est accessible avec un jeton public destiné aux expérimentations ; un
jeton consommateur pérenne peut être fourni via `NAV_FEED_TOKEN`. Le connecteur
n’enregistre aucun jeton en base ou dans les rapports. Le jeton public est lu à
chaque passage et peut être remplacé par NAV. Aucune inscription ni prise de
contact avec NAV n’est effectuée par ce lot. Le fonctionnement local reste un
pilote expérimental, sans garantie d’accès durable.

## Protocole

Le provider `nav` suit les événements `/api/v1/feed`, puis consulte l’état actuel
via `/api/v1/feedentry/{uuid}`. Les chemins sont construits depuis des UUID validés,
sur un hôte fixe, sans suivre les URL fournies par le flux ni les redirections.
1000 événements au maximum par page, 20 détails par passage, budget 240 secondes,
60 secondes pour rechercher la page initiale, 20 secondes pour les autres
requêtes et 5 Mio par réponse. Les erreurs HTTP et réseau gardent
le curseur ; 404 d’une fiche retire son ancienne copie des offres publiables.

Le chargement initial commence 184 jours avant la configuration (NAV indique
qu’une annonce ne reste pas active plus de six mois). La date de départ est
persistée dans la requête. `If-Modified-Since` est utilisé seulement pour trouver
la première page. Les pages suivantes utilisent leur identifiant stable.

Le curseur contient l’UUID de page et l’offset local. Un préfixe `tail:` indique
que tous les événements disponibles ont été traités : le worker continue alors
de surveiller cette page, au lieu de repartir du début. Cadence : dix secondes
entre passages de rattrapage, deux minutes à la fin du flux. ETag/304 ne sont pas
implémentés dans ce premier lot ; chaque polling relit la page bornée.

## Qualification, retraits et fraîcheur

Les titres contenant `internship`, `intern`, `praktikant`, `praksisplass` ou
`student placement` déclenchent la lecture du détail. Ce préfiltre ne constitue
pas une qualification. « Intern utlysning » (recrutement interne), les emplois
étudiants et les programmes trainee ne deviennent pas automatiquement des stages.
Les règles communes exigent des preuves de stage et un pays européen explicite.
Les formes linguistiques non reconnues restent incertaines ; le rappel n’est pas
exhaustif. Toutes les localisations sont conservées et le pays ne provient jamais
du portail. Le télétravail explicite reste soumis à la règle prudente du moteur.

Toute offre déjà connue est relue lorsqu’un événement la concerne, même après
changement ou suppression du titre. La réponse actuelle du détail prévaut sur
les anciennes métadonnées de l’événement. Une fiche inactive rend sa source non
publiable. Les dates d’expiration sont obligatoires et interprétées selon la fin
de journée norvégienne annoncée par NAV. L’API locale exclut automatiquement les
offres expirées.

Arriver à la fin du flux confirme aussi l’absence de changement pour les offres
actives connues : leur date de vérification est actualisée. En cas d’arrêt du
worker, la limite commune de fraîcheur retire progressivement les offres dont
la synchronisation n’est plus confirmée.

Seuls les champs utiles à l’annonce sont conservés. La liste structurée des
contacts et les adresses de rue ne sont pas stockées. Le bouton de candidature
utilise l’URL de candidature fournie, si présente et HTTPS ; sinon la fiche NAV
reste le point d’accès à l’offre. Le contenu de la description reste celui de la
source. Les snapshots sont partiels et ne ferment jamais des offres par absence.

## Intégration

`run_nav_worker --seed-countries NO --once` configure le chargement initial.
Worker continu : `run_nav_worker --poll-interval 10 --limit 1`.
Service Compose `nav-worker`, profil `app`, variable `NAV_FEED_TOKEN` optionnelle.
Les schedulers ATS et de découverte ignorent ce provider. La page Moteur distingue
les pages restantes de l’état « en veille sur le flux ». Les volumes d’événements
ne sont pas présentés comme un nombre d’offres uniques.

## Validation

Tests de pays/contrat/expiration, lien de candidature, fiche inactive, identité,
absence de contacts structurés, refus des chemins arbitraires, déduplication des
événements d’une page, polling en fin de flux, retrait après masquage du titre,
idempotence et préservation du curseur sur échec. Rapport de pilote dans
`docs/research/2026-10-01-nav-results.json`.

Résultats locaux : 367 tests backend réussis, build frontend et configuration
Compose valides, aucune migration. Pilote repris depuis une page obtenue en direct :
1000 événements, 1 stage qualifié et publié chez Merchant Group AS, Bergen/Norvège.
Le pilote est désactivé après mesure ; le rattrapage de six mois a son propre
curseur. Des timeouts de recherche initiale ont été observés ; le worker conserve
les diagnostics et réessaie avec backoff. Accès durable et exhaustivité non prouvés.

Vérification finale : après allongement du timeout de recherche initiale à 60 s,
le worker principal a démarré et parcouru plusieurs pages de 1000 événements avec
avancement du curseur et sans erreur. Le rattrapage est donc effectivement en cours,
mais non terminé. Les 14 tests ciblés NAV/couverture passent également après ce réglage.
