# Couverture Europe V10 — Bundesagentur für Arbeit

## Objectif et sources

Ajouter les stages publics de la Jobsuche allemande avec leurs descriptions
complètes, tous secteurs, sans accepter automatiquement les offres classées
« Praktikum/Trainee ». Provider interne : `bundesagentur`.

Recherche et détails ont été vérifiés directement sur
`https://rest.arbeitsagentur.de/jobboerse/jobsuche-service` le 1er octobre 2026
(heure de Paris). La documentation utilisée est communautaire, pas un contrat
API officiel : [bundesAPI/jobsuche-api](https://github.com/bundesAPI/jobsuche-api).
Elle décrit le client public `jobboerse-jobsuche`, la recherche v6, les détails
v4 avec référence encodée en Base64 et la catégorie 34 partagée entre stages et
trainees. Aucun compte ni secret utilisateur n’est nécessaire pour ces appels.

## Collecte

Trois requêtes : `Praktikum`, `Praktikant`, `Internship`, avec `angebotsart=34`.
Aucun filtre métier. Recherche `/pc/v6/jobs`, détail `/pc/v4/jobdetails/{code}`.
Référence validée puis contrôlée sur la réponse de détail. Liens de candidature
vers la fiche publique `https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}`.

20 résultats par page, budget 240 secondes, réponse individuelle limitée à 2 Mio,
timeout réseau 20 secondes, sans redirection. Plafond local de 500 pages par
requête ; `truncated=true` signale qu’il reste des résultats. Aucun contournement
ni promesse d’exhaustivité : les mots-clés, les variations du classement et le
plafond peuvent limiter le rappel.

Un HTTP 404 du détail produit un résultat invalide et retire une éventuelle
ancienne copie de cette source. Les pannes et limitations de débit conservent
le curseur pour reprise. Une page vide inattendue ou des identifiants répétés
sur la même page sont des erreurs, pas des succès silencieux. Les champs
conservés excluent les listes de contacts, adresses de rue et coordonnées privées.

## Qualification

La catégorie source doit être `PRAKTIKUM_TRAINEE`, mais elle ne suffit pas.
Le moteur commun vérifie le titre et la description, exclut les emplois étudiants,
les programmes de diplômés et les contrats non stages. Une description complète
d’au moins 40 caractères et un employeur identifié sont obligatoires.

Chaque lieu est traduit depuis son pays déclaré : notamment `DEUTSCHLAND` → `DE`,
`OESTERREICH` → `AT`, `SCHWEIZ` → `CH`. Les autres libellés passent par le résolveur
commun. Jamais de pays inventé depuis le portail ou la recherche ; un lieu sans
preuve demeure indéterminé. Le filtre européen commun reste obligatoire.
Le télétravail explicite dans le titre est soumis à sa règle conservatrice.
`homeofficemoeglich` seul décrit une possibilité et n’établit pas un poste
entièrement à distance.

La fenêtre de publication est contrôlée : début futur ou fin passée exclut la
fiche. La fin est inclusive dans le fuseau Europe/Berlin et enregistrée comme
expiration à minuit le lendemain. Si elle manque, aucune date n’est inventée :
la fraîcheur des sources protège la publication.

## Intégration et exploitation

Worker dédié `run_bundesagentur_worker`, requêtes durables avec lease de dix
minutes, contrôle du jeton avant import, reprise exponentielle et Retry-After.
Prochaine page après une minute, nouveau cycle après douze heures. Les autres
workers de découverte et de catalogue excluent ce provider. Service Compose
`bundesagentur-worker` sous profil `app`.

L’import réutilise les révisions, l’enrichissement et les snapshots partiels.
Une absence dans une page ne ferme pas une offre. Les références déjà importées
pour le même employeur sont réutilisées entre requêtes. La déduplication entre
plateformes n’est pas exhaustive ; les volumes source ne sont pas des ajouts
uniques au catalogue.

## Vérification

Tests : faux stages dans la catégorie 34, pays inconnu/non européen, dates,
référence de détail, minimisation, 404 contre panne transitoire, pagination,
encodage Base64, idempotence, expiration persistée et perte de lease.
Rapport de pilote : `docs/research/2026-10-01-bundesagentur-results.json`.

## Limites et suite

Connecteur basé sur des endpoints publics non documentés officiellement, donc
susceptibles de changer. Les stages scolaires restent des stages dans le
périmètre actuel. Les trois recherches n’assurent pas l’exhaustivité européenne.
France Travail et NAV restent à étudier et intégrer selon leurs modalités d’accès.

Validation du pilote : 60 résultats examinés, 49 fiches publiables et 11 incertains.
346 tests backend passent ; Ruff sans erreur sur les fichiers concernés, aucune
migration nécessaire et configuration Compose valide. Worker local activé.
Le service Compose est configuré mais son image n’a pas été reconstruite ici.
