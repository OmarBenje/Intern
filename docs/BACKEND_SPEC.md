# Intern — Backend V1

Date : 30 septembre 2026. Spécification d'implémentation pour le dépôt Intern.

## Objectif et état vérifié

Rendre le parcours candidat utilisable par un frontend : compte, profil, documents privés, découverte d'offres, dossier versionné, validation individuelle, exécution et suivi. Cette spécification décrit les choix initiaux ; l'implémentation actuelle se trouve sous `metier/app`, avec ses routes, services et migrations. Le contrat en vigueur est détaillé dans [API.md](API.md).

La vision du 28 septembre (`VISION.md`) prévaut sur le cadrage du 23 septembre : plusieurs types de contrats, aucune restriction géographique implicite. Le schéma et ses FK composites sont conservés. Les réglages locaux PostgreSQL sur le port 5433 sont conservés.

## Recommandations vérifiées et choix

Sources officielles consultées le 30 septembre 2026 :

- [Sécurité Django 6.1](https://docs.djangoproject.com/en/6.1/topics/security/) : validation serveur, ORM, CSRF sur mutations, protection des téléchargements.
- [Authentification](https://docs.djangoproject.com/en/6.1/topics/auth/default/) : utilisateurs, mots de passe et sessions Django ; pas de JWT artisanal.
- [Transactions](https://docs.djangoproject.com/en/6.1/topics/db/transactions/) : transactions atomiques courtes ; aucun appel externe pendant un verrou.
- [QuerySets](https://docs.djangoproject.com/en/6.1/ref/models/querysets/) : `select_for_update`, préchargement des relations et pagination déterministe.
- [Tests](https://docs.djangoproject.com/en/6.1/topics/testing/tools/) : PostgreSQL réel, client CSRF et TransactionTestCase pour la concurrence.
- [Uploads](https://docs.djangoproject.com/en/6.1/topics/http/file-uploads/) : taille bornée, validation de contenu, fichiers privés hors racine web.
- [Déploiement](https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/) : secrets d'environnement, DEBUG désactivé, HTTPS, hosts explicites, `check --deploy`.
- [Tasks](https://docs.djangoproject.com/en/6.1/topics/tasks/) : l'API de tâches n'exécute pas elle-même les travaux. Le worker lit ici l'outbox PostgreSQL existante, sans ajouter un broker.
- [Greenhouse](https://docs.greenhouse.io/job-board.html) : import public ; envoi réservé à une clé Job Board partenaire. Une offre publique n'accorde pas un droit d'envoi par API.
- [R2 et boto3](https://developers.cloudflare.com/r2/examples/aws/boto3/) : stockage S3 privé configurable.

API JSON Django REST framework sous `/api/v1/`, mêmes origines et sessions. La [spec de migration DRF](DRF_MIGRATION_SPEC.md) remplace le choix initial de vues JSON natives. Les vues restent minces ; `services/` porte les mutations et `integrations/` les accès externes. Les IDs existants sont conservés avec contrôle systématique du propriétaire. Les champs modifiables sont explicitement autorisés. Aucun endpoint générique d'écriture de révision, autorisation, run ou événement.

## Contrat HTTP

JSON objet uniquement, champs inconnus rejetés. Erreurs `{ "error": { "code": "...", "message": "...", "details": {} } }`. 400 validation, 401 session absente, 403 CSRF, 404 ressource absente/étrangère, 409 conflit métier, 413 taille dépassée, 429 débit dépassé, 503 intégration indisponible. Listes `{results, count, page, page_size}`, 20 par défaut, maximum 100. Dates ISO 8601 UTC. Réponses privées `Cache-Control: no-store`.

| Routes (préfixe `/api/v1/`) | Contrat |
|---|---|
| `auth/csrf/` GET | Token CSRF, cookie ; obligatoire avant toute mutation |
| `auth/register/`, `auth/login/`, `auth/logout/` POST | Identité username/email/password/full_name à l'inscription ; session renouvelée à la connexion |
| `auth/me/` GET ; `auth/password/` POST | Identité courante ; changement avec ancien mot de passe |
| `auth/password-reset/`, `auth/password-reset-confirm/` POST | Réponse uniforme à la demande ; jeton Django à usage limité, URL issue de configuration serveur |
| `offers/`, `offers/<id>/` GET | Offres ouvertes non expirées, recherche, contrat, mode, lieu, rôle, pagination |
| `catalogue/` GET | Rôles, compétences et lieux pour les formulaires |
| `saved-offers/` GET ; `saved-offers/<offer_id>/` PUT/DELETE | Favoris personnels idempotents |
| `recommendations/` GET | Correspondances structurées et raisons ; aucune probabilité d'embauche |
| `profile/` GET/PATCH | Profil propre et version ; version incrémentée à chaque mutation pertinente |
| `profile/<experiences|education|projects|work-authorizations>/` GET/POST | Enfants du profil ; détail PATCH/DELETE par ID |
| `preferences/` GET/PUT | Champs salariaux, rôles, lieux, contrats et modes explicitement fournis |
| `documents/` GET/POST multipart | PDF vérifié (10 Mio max), kind resume/cover_letter, nom/empreinte calculés serveur |
| `documents/<id>/download/` GET ; `documents/<id>/` DELETE | Téléchargement privé ; suppression refusée si référencé |
| `profile/resume/` PUT | `{document_id}` : CV ready du même propriétaire |
| `applications/` GET/POST | `{offer_id, source_id}` ; création idempotente utilisateur/offre |
| `applications/<id>/` GET | Dossier, dernière révision et dernier run ; historiques `/revisions/`, `/runs/`, `/events/` paginés séparément |
| `applications/<id>/prepare/` POST | Nouvelle révision depuis profil/CV et formulaire source ; réponses factuelles connues seulement |
| `applications/<id>/revisions/` GET/POST | `{answers, document_ids}` : nouvelle révision à partir de la dernière ; aucune modification en place |
| `applications/<id>/approve/` POST | `{revision_id, content_hash, idempotency_key}` : accord limité à 24 h + run + outbox atomiques |
| `applications/<id>/revoke/` POST | Révocation avant soumission ; conflit si effet externe possible |
| `applications/<id>/status/` POST | `{status, reason}` : suivi manuel et événement d'audit ; pas de résolution implicite d'un envoi incertain |
| `applications/<id>/resolve/` POST | Résolution explicite d'un run incertain avec résultat et preuve/référence ; jamais relance automatique |
| `applications/<id>/tasks/`, `.../interviews/` GET/POST | CRUD propre ; détail PATCH/DELETE |
| `account/export/` GET | ZIP privé : données versionnées et fichiers ; taille bornée |
| `account/delete/` POST | Mot de passe exigé, compte désactivé, révocation et purge asynchrone récupérable |
| `/health/live/`, `/health/ready/` GET | Processus ; connexion PostgreSQL sans détails internes |

## Invariants candidature et worker

1. Toute écriture privée verrouille le compte actif puis le dossier/profil, dans cet ordre ; la désactivation coupe les nouvelles écritures.
2. Profil et offre sont copiés côté serveur. Formulaire et destination proviennent du connecteur ; aucune URL client ne devient une destination d'envoi.
3. Révisions immuables via l'API. Chaque correction crée un numéro suivant sous verrou, annule les accords antérieurs avant effet externe. Hash SHA-256 canonique sur snapshots, réponses et IDs/empreintes des documents triés. Toute approbation exige le hash affiché et la dernière révision.
4. Vérifier documents ready, propriétaire, empreinte des octets et champs requis avant accord et avant envoi. Informations manquantes signalées ; aucune expérience inventée.
5. Un run actif ou incertain par dossier. Clé UUID d'idempotence liée au propriétaire/dossier/révision. Accord, run et message outbox écrits dans la même transaction.
6. Worker : claim avec lease/token et `skip_locked`, réseau hors transaction, nouveau contrôle d'accord/hash/token/source avant phase `submitting`. Un ancien token ne peut terminer le run.
7. Succès uniquement sur confirmation du connecteur, atomiquement avec statut et événement. Timeout/5xx/arrêt après début d'envoi => `uncertain`, jamais retry. Une expiration de lease après phase dangereuse devient incertaine. Échec certain avant envoi conserve le dossier.
8. Connecteurs d'envoi activés explicitement par opérateur, secrets hors DB. Sans capacité configurée : erreur explicite, aucun faux succès. Les tests utilisent des doubles ; aucun CV réel envoyé pendant l'implémentation.
9. Export complet propre ; suppression désactive d'abord le compte, attend les runs pouvant encore agir, supprime les objets privés de façon idempotente, puis les lignes dans l'ordre des FK. Reçu final sans identité.

## Intégrations et limites de vérification

Livrer un import Greenhouse complet, relançable et atomique par board. Une réponse incomplète/échouée ne ferme aucune offre ; une réponse complète marque les sources absentes puis ferme uniquement les offres sans source active. URLs réseau construites depuis un hôte fixe et un token de board validé, timeouts, redirects refusés, réponse bornée.

Livrer l'interface d'adaptateur d'envoi et un adaptateur Greenhouse partenaire configurable, avec contrôle du formulaire frais avant envoi. Un site navigateur ou autre ATS pourra remplacer cet adaptateur après choix du premier portail. La génération rédactionnelle IA et l'extraction automatique du CV nécessitent un fournisseur distinct : le backend prépare déjà un dossier factuel révisable depuis le profil confirmé. Ne pas présenter ce dossier déterministe comme un agent IA rédactionnel.

Stockage local privé pour développement, R2 via boto3 pour production ; aucun bucket public. Dépendances verrouillées. Configuration Docker pour web/worker/PostgreSQL ; lancement de production explicite après migrations, pas d'application automatique des migrations destructrices.

## Lots et critères d'acceptation

A. Configuration, erreurs, auth : validation mot de passe, CSRF y compris login/register, 401/404 corrects, aucune élévation par champs JSON ; secrets de production exigés.
B. Catalogue/import : dédoublonnage, réimport, filtres/pagination, échec d'import non destructif, favoris isolés.
C. Profil/documents : CRUD et incréments de version, cohérence préférences, PDF invalide/trop gros refusé, téléchargement étranger 404, documents historiques conservés.
D. Dossiers : création idempotente, snapshots immuables, nouveau hash après correction, accord obsolète/expiré/révoqué refusé, double clic n'envoie qu'une fois.
E. Worker/suivi : transitions atomiques, lease concurrent, token périmé refusé, résultat inconnu bloqué, tâches/entretiens isolés.
F. Exploitation : export privé, purge récupérable, check/migrations sans dérive, tests PostgreSQL, vérification déploiement, README et contrat API reproductibles.

Ordre : A avant B/C ; B/C avant D ; D avant E ; F vérifie le parcours intégré. Tests unitaires des normalisations/hashes, tests HTTP avec deux comptes, tests transactionnels des doubles clics et claims. Réutiliser les tests de migrations existants. Ne pas annoncer un résultat de test avant exécution.

## Retour arrière

Les migrations existantes et données sont conservées. Revenir au code précédent arrête les nouveaux points d'entrée ; arrêter les workers avant rollback, conserver les messages/run incertains pour vérification. Ne jamais réinitialiser le volume PostgreSQL. Les nouveaux fichiers privés restent conservés tant que leur suppression n'est pas confirmée.

## Hors livraison locale

Frontend, déploiement distant, achat/création d'accès externes, envoi d'une candidature réelle, garantie universelle sur tous les ATS. L'activation réelle de R2 et d'un connecteur partenaire sera signalée séparément des tests automatisés.
