# Couverture V4 — import direct JobSpy et registre ATS

## Objectif
Réduire les pertes entre découverte et publication. Une annonce lisible peut être
importée sans lien vers un ATS connu. Le registre fournit des candidats employeurs,
pas une affirmation de stages disponibles.

## Contrats
- JobSpy épinglé à `7f0ff3ab25a4a4cd204af421cf6378ede3da5569` (MIT), exécuté dans
  un sous-processus interruptible après 180 s. LinkedIn/Indeed/Glassdoor disponibles
  à la commande ; seuls les accès réellement testés sont qualifiés opérationnels.
- Recherches persistées dans DiscoveryQuery, résultats et erreurs dans DiscoveryResult.
  Worker distinct de la découverte ATS. Maximum 20 annonces par page et 200 par
  recherche/cycle ; curseur conservé entre passages. Aucun filtre des sept derniers
  jours : constitution d'un stock de recherche, toujours partiel.
- Publication : description présente, employeur, lien public source, stage confirmé,
  pays européen explicite dans la localisation source. Le pays de la requête n'est
  jamais une preuve ; remote sans résidence prouvée reste incertain.
- Identifiant source stable par plateforme et employeur ; idempotence entre recherches.
  Un lien employeur direct exactement identique avec même employeur/titre permet de
  marquer un résultat comme doublon connu. Aucune fusion automatique sur titre seul.
- Importeur commun : révisions, fraîcheur, transactions et verrous conservés.
  Les sources JobSpy sont alimentées par leurs requêtes, jamais par board.sync.
  Snapshots toujours partiels : aucune fermeture par absence.
- Résultat vide JobSpy : erreur explicite `jobspy_empty_unconfirmed`, car la bibliothèque
  peut masquer une erreur réseau en liste vide. Conservation des offres existantes,
  reprise après temporisation ; absence de résultat n'est pas une preuve d'exhaustivité.

## Registre
`kalil0321/ats-scrapers` épinglé à `6b44a1badc9bfbf5cf176f75265cc5729e520e99`.
Sept inventaires : Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Personio,
Recruitee. Lecture bornée, contrôle de schéma, correspondance provider/URL,
source et SHA-256 conservés par candidat. Pas de téléchargement de code de ce dépôt.
Commande avec limite, offset, sélection employeur et budget d'activation jusqu'à
10 pilotes ; les échecs consomment aussi le budget. Seul un pilote réussi valide
et planifie un portail. Les candidats non activés ne sont pas des sources actives.

## Vérification
Tests de qualification, géographie, remote, URL, données incomplètes, timeout,
résultat vide, pagination, reprise, idempotence et import partiel. Sauvegarde locale
avant imports, mesure avant/après et résultats réels documentés. Aucun changement
de schéma nécessaire. Respect des licences MIT des dépendances ; attribution du
registre dans les résultats de découverte.

## Limites
Les pages peuvent être bloquées ; aucun contournement de connexion ni achat de proxy.
Le plafond par requête ne couvre pas tout le marché. Les synonymes employeur et
les liens directs variant par tracking limitent la déduplication entre plateformes.
La fraîcheur commune masque les offres non revérifiées ; une recherche seule ne
prouve pas que toutes les annonces affichées par la plateforme sont encore ouvertes.

## Recette du 30 septembre 2026

Dépendance installée et verrouillée ; pilotes LinkedIn réels : FR 20/20, GB 17/20,
DE 16/20 annonces admises. Le catalogue est passé de **928 à 981** au dernier
contrôle avant l'incident Docker. Indeed FR : `jobspy_empty_unconfirmed`, conservé
comme erreur ; Glassdoor intégré comme option, pas testé ni activé.

Le registre a enregistré un lot de 1 000 candidats, avec un offset de reprise à
1 000, plus une sélection de 23 noms. Les cinq premières activations par préfixe
ont touché des homonymes/filiales américains (notamment Apple Roofing, Apple Tree
Dental et Accenture Federal Services) et n'ont ajouté aucun stage européen.
Cette sélection trop large ne doit pas servir de modèle : utiliser les noms exacts
et vérifier les URL. Le pilote suivant Philips/Red Hat/Orange/Thales a été bloqué
par l'indisponibilité de la base ; il n'est pas annoncé comme réalisé.

295 tests backend passent, dont 13 nouveaux, sur PostgreSQL 16.15 isolé. Ruff passe.
Contrôle des migrations avant incident : aucun changement. Le build Docker a échoué
sur une erreur d'entrée/sortie BuildKit/extraction numpy, puis le moteur Docker
s'est arrêté. La disponibilité locale ne doit pas être déduite des tests.
Sauvegarde avant imports : `~/.codex/backups/intern-coverage-v4-20260930/before-jobspy.dump`.

[Audit du pilote](../../research/2026-09-30-jobspy-pilot.json),
[registre général](../../research/2026-09-30-ats-registry-candidates.json),
[pilotes employeurs et limites](../../research/2026-09-30-ats-registry-pilot.json).

État final d'exploitation de ce tour : le redémarrage ordinaire puis la fermeture
et relance de Docker Desktop n'ont pas rétabli le moteur. PostgreSQL 5433 ne répond
pas ; les workers ne tournent pas. Aucun volume réinitialisé ou restauré. Après
rétablissement de Docker, contrôler le compteur et les sources, suspendre les cinq
pilotes sans stages européens si nécessaire, puis relancer les deux workers et le
pilote Workday exact. Les 981 offres sont le dernier total mesuré, pas une preuve
que l'API est actuellement disponible.
