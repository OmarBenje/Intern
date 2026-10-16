# Implémentation du schéma Django

Évolution du 30 septembre : API et services métier livrés ensuite ; voir [BACKEND_IMPLEMENTATION.md](../backend/BACKEND_IMPLEMENTATION.md) pour les vérifications actuelles et limites externes. Le rapport ci-dessous conserve la livraison du schéma du 28 septembre.

Date : 28 septembre 2026. **Les 34 modèles du schéma V1 sont implémentés et les migrations `0009` à `0014` sont appliquées à la base PostgreSQL locale.**

## Organisation

Les imports existants restent valides : `from jobboard.models import Offer, CandidateProfile`. Le fichier `models.py` est devenu un package pour garder chaque domaine lisible.

| Fichier | Modèles |
|---|---|
| [catalogue.py](../../metier/app/jobboard/models/catalogue.py) | Company, Role, Skill, Location, Offer, OfferLocation, OfferSkill, SourceBoard, ImportRun, OfferSource, CompensationBand, SavedOffer |
| [profiles.py](../../metier/app/jobboard/models/profiles.py) | CandidateProfile, Experience, Education, Project, CandidateSkill, WorkAuthorization, SearchPreference, PreferenceRole, PreferenceLocation, PreferenceContract, PreferenceWorkMode |
| [documents.py](../../metier/app/jobboard/models/documents.py) | Document |
| [applications.py](../../metier/app/jobboard/models/applications.py) | Application, ApplicationRevision, RevisionDocument, SubmissionAuthorization, AgentRun, ApplicationEvent, Interview, ApplicationTask |
| [operations.py](../../metier/app/jobboard/models/operations.py) | OutboxMessage, DeletionRequest |

Les tables sont celles gérées par Django, préfixées `jobboard_`, pas celles du schéma isolé `intern_blueprint`. Le SQL du dossier `database` reste une référence pédagogique ; **ne pas l’appliquer à la place des migrations**.

## Correspondance avec le blueprint

Trois noms existants sont conservés pour respecter le code du projet : `Offer.description` correspond à `description_text`, `Location.name` à `label`, `CandidateProfile.presentation` à `summary`. Le champ `presentation`, ajouté dans le code avant cette implémentation mais pas encore migré, est désormais pris en charge.

`Offer.application_url` et `CandidateProfile.resume_url` restent comme champs de transition. La destination canonique d’une candidature est `OfferSource.apply_url` ; le CV vérifié est `CandidateProfile.current_resume`. Une ancienne URL de CV ne devient pas automatiquement un document prêt : aucun fichier externe n’a été téléchargé et aucune empreinte n’a été inventée.

Les associations existantes conservent leur nom de table, leurs IDs et leurs liens : offres/lieux, offres/compétences, profil/compétences et préférences/rôles/lieux. Les colonnes historiques `candidateprofile_id` et `searchpreference_id` sont conservées via `db_column`.

Django applique les comportements `PROTECT`, `CASCADE` et `SET_NULL` via son collecteur de suppression. Les clés étrangères PostgreSQL empêchent les références orphelines ; les opérations SQL directes ne reproduisent pas automatiquement toutes les cascades de l’ORM. Les clés composites supplémentaires utilisent `NO ACTION`, différables mais immédiates par défaut.

## Migrations

| Migration | Effet |
|---|---|
| `0009_catalogue` | Enrichit le catalogue, adopte les associations existantes, ajoute la recherche générée/GIN, transforme `job` en `employment`, copie `is_active` vers `status`, crée les sources legacy et les clés/slugs. |
| `0010_profile_location_text` | Renomme le texte de localisation du profil pour libérer `location` pour la FK. |
| `0011_profiles_documents` | Ajoute parcours, documents, préférences normalisées et associations ; copie exactement les anciens booléens. |
| `0012_applications_operations` | Ajoute dossiers, révisions, autorisations, runs, suivi, outbox et demandes de suppression. |
| `0013_finalize_catalogue_preferences` | Retire les booléens remplacés, rend clés/slugs obligatoires après backfill et active les dates automatiques de modification. |
| `0014_composite_foreign_keys` | Ajoute 13 clés composites pour contrôler propriétaires, types de document, sources et appartenance au dossier. |

Les migrations `0001` à `0008` n’ont pas été réécrites. Le modèle utilisateur Django est conservé.

Les slugs historiques incluent l’ID pour éviter qu’une normalisation identique de deux noms perde un enregistrement. Les lieux reçoivent `legacy:<id>` sans inventer un pays. Les sources historiques sont rattachées à un board désactivé, fournisseur `legacy`, sans prétendre qu’un connecteur ATS a été configuré.

La migration des préférences conserve les cas « tous faux » comme ensembles vides. Pour une nouvelle préférence, les choix doivent être créés explicitement par le futur parcours d’onboarding : le modèle n’ajoute pas silencieusement de lignes par signal.

Les backfills rendent les vérifications FK immédiates dans leur transaction avant les opérations DDL suivantes. Cela évite l’erreur PostgreSQL « pending trigger events » avec des données préexistantes.

## Contraintes livrées

- Unicité des candidatures, favoris, identités externes, numéros de révision, commandes outbox et confirmations dédupliquées.
- Même propriétaire pour CV courant, filiation documentaire, documents d’une révision, autorisation et preuves.
- Cohérence offre/source, board/import et dossier/révision/run/événement.
- Un seul run actif **ou incertain** par dossier ; référence d’autorisation obligatoire pour l’envoi.
- Types autorisés, dates ordonnées, montants non négatifs, devise/période salariales cohérentes, hash au format SHA-256.
- Objets JSON pour snapshots/payloads et tableau JSON pour réponses ; une révision gelée exige un hash.
- Vecteur de recherche calculé par PostgreSQL, index GIN et index ciblés pour catalogue, tracker, file et historique.

Les contraintes Python de `Meta` sont traduites en SQL par Django. Les FK composites sont ajoutées explicitement par la dernière migration : ne pas les supprimer en croyant qu’elles doublonnent les FK simples de l’ORM.

## Administration

Le catalogue (entreprises, rôles, compétences, lieux, offres) est modifiable avec les permissions Django usuelles. Les lieux et compétences d’une offre sont éditables en inline.

Les profils, documents et objets de workflow sont consultables **en lecture seule par les superutilisateurs**. Les membres du staff disposant uniquement de permissions de catalogue n’accèdent pas aux CV/réponses. Cette séparation évite que l’admin permette de contourner les futurs services d’approbation, d’envoi et de purge.

## Validation exécutée

**32 tests passent sur PostgreSQL 16.14**, avec Django 6.1.1 :

- Création depuis une base vierge ; recherche textuelle et contraintes métier.
- Migration d’un jeu ancien comportant offres, comptes, lieux, compétences et préférences, puis retour vers `0008` et nouvelle migration ; IDs et associations conservés.
- Cas de données étrangères, documents de mauvais type, source incompatible, reprise bloquée après résultat incertain et commandes répétées.
- Accès administrateur : staff refusé pour les documents ; superutilisateur autorisé à lire mais pas à modifier les dossiers privés.

La sauvegarde réelle a aussi été restaurée dans une base temporaire, migrée avec succès, puis cette base de répétition a été supprimée. Les migrations ont ensuite été appliquées à la base locale ; les comptes existants, les IDs des tables initiales et les 13 FK composites ont été contrôlés.

Commandes depuis la racine du projet :

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test jobboard --noinput
.venv/bin/python manage.py showmigrations jobboard
```

`check` ne signale aucune erreur ; `makemigrations --check --dry-run` ne détecte aucune différence. Vérification de style effectuée avec Ruff sur les modèles, tests et administration, règles `E4,E7,E9,F,I`.

La sauvegarde préalable des fichiers et de PostgreSQL se trouve dans :

`/home/omar-benjelloun/.codex/backups/intern-schema-20260928T120124Z/`

Le rollback a été testé sur des données historiques de test. Un retour complet vers `0008` supprimerait les nouvelles tables et leurs données : utiliser la sauvegarde ou préparer une migration adaptée si du travail a déjà été créé avec le nouveau schéma.

## Limite de cette livraison

Cette livraison implémente **le stockage et ses contraintes**, pas un agent de candidature opérationnel. Restent à développer : API et écrans, connecteurs ATS, upload/contrôle R2, calcul du hash canonique, gel effectif des révisions et fichiers, validation temporelle des autorisations, workers/leases, mises à jour atomiques de statut/historique, export et purge.

Un appel ORM brut peut encore modifier une révision gelée ou créer une autorisation au hash différent de celui de la révision : comme dans l’architecture, ces invariants requièrent les services métier, pas uniquement la forme du schéma. Les points d’écriture correspondants ne sont pas exposés dans l’admin. Les contrôles SQL ne constituent pas non plus un système de permissions pour une future API.

`auto_now` actualise les dates lors de `save()` ; un futur service utilisant `QuerySet.update()` devra fournir `updated_at` explicitement. La version du profil devra être incrémentée lors de modifications pertinentes du profil et de ses enfants.
