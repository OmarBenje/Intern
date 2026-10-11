# Modèle relationnel — Intern DEV, étape 3

## Relations principales

| Table SQL | Identité et relations |
| --- | --- |
| `auth_user` | PK `id`, login `username` unique, hash `password`, alias SQL généré `mot_de_passe_hash`, état `is_active`, privilèges administrateur |
| `jobboard_candidateprofile` | PK `id`, compte `user_id` unique et obligatoire ; CV courant optionnel |
| `jobboard_recruiterprofile` | PK `id`, compte `user_id` unique et obligatoire ; entreprise optionnelle avant vérification |
| `jobboard_company` | PK `id` ; une entreprise peut avoir zéro à plusieurs offres et recruteurs |
| `jobboard_offer` | PK `id`, entreprise `company_id` obligatoire ; zéro à plusieurs dossiers |
| `jobboard_sourceboard` | PK `id` ; configuration d'une source de catalogue, sans identifiants externes dans la recette |
| `jobboard_offersource` | PK `id`, FK vers offre et source ; unicité du couple source/identifiant externe |
| `jobboard_document` | PK `id`, propriétaire `owner_id` obligatoire ; type, clé de stockage privée, empreinte SHA-256 du fichier |
| `jobboard_application` | PK `id`, candidat, offre et source obligatoires ; couple candidat/offre unique |
| `jobboard_recruiterjob` | PK `id`, propriétaire recruteur obligatoire ; lien unique vers l'offre publiée, facultatif pour un brouillon |
| `jobboard_recruiterapplicant` | PK `id`, candidature unique, poste destinataire, copie des données transmises et CV ; candidat et offre recopiés pour les FK composites |

Un compte peut exister sans profil candidat, notamment pour l'administration.
Les privilèges ne reposent pas sur un champ de rôle envoyé par le navigateur :
la couche métier devra utiliser la session, les profils et les droits du compte.
Le modèle distingue le poste privé du recruteur (`recruiterjob`) et son offre
dans le catalogue (`offer`). Le partage d'une entreprise ne partage pas la
propriété des postes.

Le schéma complet comprend 72 tables, dont celles nécessaires aux référentiels,
documents, préférences, révisions et opérations de l'application.
Conserver ces tables dans l'export permet d'utiliser les mêmes migrations à
l'étape métier, plutôt que construire une seconde base incompatible.

## Garanties et règles

| Règle | Garantie en base à l'étape 3 | Vérification métier ultérieure |
| --- | --- | --- |
| R1 | `offer.company_id` non nul avec FK vers une entreprise existante | Droits de gestion du catalogue |
| R2 | FK vers les propriétaires ; FK composite du CV courant ; transmission liée à la candidature, son candidat, son offre, le poste destinataire et le propriétaire/type du CV | Filtrage par session, partage explicite, contrôle des téléchargements et conservation des données transmises |
| R3 | `application_source_offer_fk` lie `(source_id, offer_id)` à la même source d'offre | Validation et message d'erreur de l'API |
| R4 | `application_user_offer_unique` sur `(user_id, offer_id)` | Retour idempotent de la candidature directe |
| R5 | Login unique ; hash salé lent scrypt ; alias `mot_de_passe_hash` généré depuis `password` | Validation des saisies, création et vérification du hash, politique d'e-mail |
| R6 | États d'activation, vérification d'e-mail et d'entreprise stockés séparément ; compte de recette en attente inactif | Refus de connexion inactive, activation par administrateur et conditions de publication |

### Choix de conception

Intern utilise une PK technique `id`, référencée par les événements et les
transmissions, et ajoute un `UNIQUE(user_id, offer_id)`. L'interdiction des
doublons est garantie par cette contrainte d'unicité.

Django utilise le champ `password` pour l'authentification standard. La colonne
SQL `mot_de_passe_hash` est **générée** depuis ce champ :
elle se recalcule automatiquement et ne peut pas diverger. Scrypt assure
un hachage salé lent. La SHA-256 des documents identifie leur contenu et
n'est jamais utilisée pour hacher les mots de passe.

### Cohérence d'une candidature transmise

`recruiterapplicant` recopie le candidat et l'offre de la candidature. Ces deux
valeurs permettent de vérifier trois relations **en SQL** :

1. `(application_id, candidate_id, offer_id)` référence la candidature et ses
   vrais candidat et offre.
2. `(job_id, offer_id)` référence le poste de cette même offre.
3. `(resume_id, candidate_id, resume_kind)` référence un CV du même candidat ;
   `resume_kind` est contraint à `resume`.

Le modèle renseigne ces valeurs lors des sauvegardes Django. Une écriture SQL
qui les falsifie, change de destinataire ou transmet le CV d'un tiers est
refusée par une FK composite. Un CV absent reste autorisé par le schéma ;
l'obligation d'un CV prêt lors de la candidature directe sera vérifiée par
l'API à l'étape 4.

La base ne connaît pas la session HTTP. Les contraintes relationnelles ne
remplacent donc pas les tests d'autorisation et de publication de l'étape métier.
