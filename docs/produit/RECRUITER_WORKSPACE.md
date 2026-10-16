# Espace recruteur

Le choix **Candidat / Recruteur** précède maintenant l’e-mail, le nom et le mot de passe. Les comptes existants restent candidats. La session, la protection CSRF, les erreurs et la pagination utilisent le même contrat que l’API candidat.

## Parcours et écrans

| Écran | Route frontend | API principale |
| --- | --- | --- |
| Choix du rôle, inscription | `/register`, `/recruiter/signup` | `POST /api/v1/auth/register/` |
| Vérification entreprise | `/recruiter/verify` | `/api/v1/recruiter/verify/` |
| Tableau de bord | `/recruiter/dashboard` | `/api/v1/recruiter/dashboard/` |
| Offres | `/recruiter/jobs` | `/api/v1/recruiter/jobs/` |
| Création en quatre étapes | `/recruiter/jobs/new` | `POST /api/v1/recruiter/jobs/` |
| Modification | `/recruiter/jobs/:id/edit` | `PATCH /api/v1/recruiter/jobs/:id/` |
| Intégrations ATS | `/recruiter/integrations` | `/api/v1/recruiter/integrations/` |
| Kanban par offre | `/recruiter/jobs/:id/applicants` | `/api/v1/recruiter/jobs/:id/applicants/` |
| Kanban global | `/recruiter/candidates` | `/api/v1/recruiter/candidates/` |
| Fiche candidat en panneau | `/recruiter/candidates/:id` | `/api/v1/recruiter/candidates/:id/` |

La navigation horizontale, les boutons, les formulaires et les tokens de couleur/typographie sont partagés avec le candidat. Le panneau utilise un dialogue modal natif, se ferme avec Échap et restitue le focus à la carte. Le kanban et le tableau défilent horizontalement sur petit écran.

## Inscription et contrôle d’accès

`POST /api/v1/auth/register/` accepte `role: "candidate" | "recruiter"`. L’omission conserve `candidate` pour les anciens clients. L'inscription répond `201 pending` et laisse le compte inactif jusqu'à la validation du superviseur. Après activation, la connexion et `/auth/me/` retournent le rôle. Aucun endpoint ne permet de modifier son rôle ou de s’attribuer des permissions administrateur.

Le compte recruteur possède un `RecruiterProfile`, sans profil candidat. Les principales routes privées candidat lui sont refusées côté serveur. Un candidat reçoit un refus sur les ressources recruteur, sauf l’action explicite de candidature directe. Les lectures publiques du catalogue restent publiques.

Chaque offre, candidat et configuration ATS est recherché dans le workspace du compte connecté. Un identifiant d’une autre entreprise renvoie 404. Partager un domaine d’e-mail ne donne jamais accès au workspace d’un autre compte. Cette livraison représente **un workspace par compte**, sans invitations d’équipe ni changement de rôle à la volée. Plusieurs comptes peuvent référencer la même entreprise du catalogue via `Company.recruiter_profiles`, sans partager leurs offres privées ni leurs candidatures. L’opérateur peut sélectionner une entreprise existante dans l’administration avant la première publication ; cette association reste ensuite protégée pour conserver l’identité des offres déjà publiées.

## Vérification

1. L’inscription recruteur refuse les principaux domaines personnels. Le formulaire transmet `role` à `POST /api/v1/auth/email-availability/` dès l’étape e-mail ; cette route et l’inscription finale utilisent la même validation serveur et le code `professional_email_required`. La liste des domaines est conservée uniquement côté serveur. Pour les anciens clients qui omettent `role`, la vérification d’adresse reste celle du candidat.
2. `POST /recruiter/verify/send-code/` avec `{}` envoie un code à six chiffres à l’adresse de la session. Le code est haché, valable dix minutes, à usage unique. Envoi et essais sont limités.
3. `POST /recruiter/verify/code/` avec `{ "code": "123456" }` valide l’e-mail.
4. `POST /recruiter/verify/` reçoit `company_name`, `siren`, `website_url` HTTPS et `linkedin_url` facultatif. Le contrôle SIREN porte sur le format et la clé ; il ne prouve pas l’existence ou l’appartenance de l’entreprise.
5. Le statut devient `pending`. L’opérateur vérifie les justificatifs et l’appartenance au domaine, puis passe le profil à `verified` dans l’administration Django. La publication exige **à la fois** ce statut et l’e-mail validé. Une révocation dans l’admin suspend les offres.

La configuration email existante s’applique : console en développement, SMTP via `MAIL_BACKEND` et les variables SMTP en production. Aucun compte n’est déclaré automatiquement vérifié à partir d’un simple domaine. OAuth Google Workspace/Microsoft 365 et vérification d’un numéro VAT étranger ne sont pas implémentés.

## Offres et candidatures

Les offres supportent `draft`, `active`, `paused`, `archived`. Les brouillons sont privés et autorisés pendant la vérification. La création comprend informations générales, missions/compétences, critères, aperçu. Le texte est enregistré et affiché sans HTML exécutable. La duplication (`POST /jobs/:id/duplicate/`) produit un nouveau brouillon sans candidatures ni lien de catalogue.

Les filtres sont `q`, `status`, `contract_type`, `location`, `origin`, avec `page`/`page_size` suivant le contrat v1. Les champs d’origine, propriétaire, statistiques et identifiants du catalogue ne sont pas modifiables par le client.

La publication crée ou met à jour une `Offer` et une source `intern` dans le catalogue existant. Les compétences, langues, formation et salaire complètent la description publique. **La règle existante des stages confirmés en Europe reste appliquée** : les contrats alternance/CDI ou offres hors Europe peuvent être gérés dans le workspace mais ne sont pas présentés dans le moteur candidat. Les offres directes restent fraîches tant que l’offre est active, l’entreprise vérifiée, l’e-mail validé et le compte actif ; elles n’attendent pas un collecteur ATS externe. La révocation d’une de ces conditions retire immédiatement l’offre des listes et de sa fiche publique, même si sa source vient d’être vérifiée. Suspendre/archiver masque la publication.

La fiche publique porte `recruiter_job_id`. Son bouton décrit les données transmises avant l’action explicite `POST /recruiter/jobs/:id/apply/` avec `{}`. Le serveur crée la candidature habituelle, un instantané du profil professionnel et une référence au CV courant. Les renvois sont idempotents. Il faut un compte candidat et un PDF prêt. Un recruteur ne peut pas parcourir librement les profils candidats ni leurs documents privés.

Le kanban utilise les étapes `new`, `recommended`, `review`, `interview`, `accepted`, `rejected`. `PATCH /candidates/:id/` reçoit `stage`, `rejection_reason` et `interview_at` (ISO 8601). Le motif est obligatoire pour un refus. Le statut candidat est synchronisé et un événement est conservé. L’entretien est enregistré dans le suivi recruteur ; il n’envoie pas d’invitation calendrier. Le lien mail ouvre le client de messagerie, sans envoi automatique.

Le CV transmis est disponible via `/candidates/:id/resume/` après contrôle de propriété de la candidature ; `?download=1` télécharge le PDF. Un retrait de candidature ou une désactivation du candidat retire cet accès. Les modifications ultérieures du profil ou du CV ne remplacent pas l’instantané envoyé. Le document est retenu tant qu’il est référencé ; l’export/suppression de compte tient compte des nouvelles données.

Le tableau de bord calcule ses métriques depuis les données. Les vues sont des consultations de la fiche publique (hors propriétaire), pas des visiteurs uniques. Aucun score ni résumé IA n’est simulé : les valeurs restent absentes jusqu’à l’intégration d’un moteur d’évaluation. Le filtre `min_score` accepte 0 à 100.

## Intégrations et limites explicites

Les cartes Greenhouse, Lever, Workday, Ashby, SmartRecruiters, Welcome to the Jungle et flux XML/JSON enregistrent une URL HTTPS propre au workspace. Elles restent **en attente d’activation**. La sauvegarde ne fait aucun appel à cette URL, n’importe aucune offre et ne prétend pas établir une connexion OAuth/API. Le raccordement authentifié des ATS, leur synchronisation et les scores/synthèses IA restent à implémenter avec les fournisseurs retenus.

Cette livraison ne comprend pas les invitations d’équipe, rôles internes Admin/Lecteur ni l’édition de la marque employeur. La page entreprise couvre les informations de vérification.

# A implémenter

connexions ATS/OAuth et calculs IA. Les configurations ATS sont enregistrées en attente.
La validation des e-mails professionnels est centralisée dans l’API, dès l’étape e-mail et lors de la création du compte.

## Installation et validation

Depuis `Intern/` :

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
TEST_DATABASE_NAME=test_intern_recruiter .venv/bin/python manage.py test \
  jobboard.tests.test_recruiters jobboard.tests.test_auth_api \
  jobboard.tests.test_onboarding_api jobboard.tests.test_account_operations \
  jobboard.tests.test_documents_api jobboard.tests.test_catalogue_api --noinput
```

Depuis `frontend/` :

```bash
npm run build
npm run lint
npm run test:e2e -- tests/recruiter.spec.ts tests/register.spec.ts tests/login.spec.ts tests/onboarding.spec.ts
```

La migration additive `0031_recruiter_workspace` crée les quatre modèles. La migration `0032_recruiter_company_memberships` permet le rattachement de plusieurs recruteurs à une entreprise et conserve les associations existantes. Les tests serveur utilisent PostgreSQL et des e-mails en mémoire ; les tests navigateur contrôlent l’API avec des réponses de test et ne valident donc pas une connexion à un ATS réel.
