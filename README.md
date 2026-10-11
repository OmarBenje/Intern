# Intern — Django et frontend

Le [suivi des livrables](LIVRABLES.md) indique les documents disponibles,
leur emplacement et leur état de vérification.

Intern sépare PostgreSQL 16, une API Django/DRF et un client React. Le schéma,
les règles d'accès et les contrats sont décrits dans
[la spécification backend](docs/BACKEND_SPEC.md). Le [client web](frontend/README.md)
couvre les parcours candidat et recruteur ; l'administration utilise Django
Admin. Les [pages entreprise](docs/COMPANY_PAGES.md) présentent les stages et
leurs sources.

L’[espace recruteur](docs/RECRUITER_WORKSPACE.md) ajoute le choix du rôle avant inscription, la vérification entreprise, les offres et le suivi des candidatures. Les routes `/api/v1/recruiter/` partagent l’authentification et les conventions v1 du candidat.

## Installer et démarrer en local

Prérequis : Python 3.12 ou plus récent, `uv`, Node.js 20.19+ ou 22.12+,
`npm`, Docker Engine avec Compose, et des ports libres **5433**, **8000** et
**5173**. Les commandes suivantes se lancent depuis la racine du dépôt.
Elles utilisent la configuration de développement ; ne pas réutiliser ses
identifiants en production.

1. Installer les dépendances Python et JavaScript :

   ```sh
   uv sync --project metier --frozen
   npm --prefix frontend ci
   ```

2. Démarrer PostgreSQL, attendre sa disponibilité et appliquer les migrations :

   ```sh
   docker compose up -d db
   docker compose exec db pg_isready -U intern_user -d intern
   uv run --project metier metier/app/manage.py migrate --noinput
   uv run --project metier metier/app/manage.py check
   ```

   Compose conserve sa base dans un volume. Sur une installation neuve, la
   base est vide. La commande `seed_dev` peut alors ajouter un jeu **fictif**
   pour la démonstration :

   ```sh
   uv run --project metier metier/app/manage.py seed_dev
   ```

   Elle refuse une base qui contient déjà des comptes ou entreprises. Les
   identifiants de démonstration sont dans [le guide des données](donnees/README.md).
   Ne pas lancer la recette en supprimant un volume qui contient d'autres
   données ; [la procédure de recette](tests/README.md) utilise une base isolée.

3. Dans un terminal, démarrer l'API avec l'origine Vite autorisée pour le CSRF :

   ```sh
   CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5173 \
     uv run --project metier metier/app/manage.py runserver 127.0.0.1:8000
   ```

   Vérifier `http://127.0.0.1:8000/health/ready/`. Le PostgreSQL local est
   publié sur **127.0.0.1:5433** ; l'API écoute sur **127.0.0.1:8000**.

4. Dans un second terminal, démarrer le client :

   ```sh
   npm --prefix frontend run dev
   ```

   Ouvrir `http://127.0.0.1:5173/login`. Vite relaie `/api/v1` vers Django.
   Utiliser `127.0.0.1` dans les deux URL pour les cookies et le CSRF.

5. Pour les tâches asynchrones, lancer dans un troisième terminal :

   ```sh
   uv run --project metier metier/app/manage.py run_worker
   ```

Pour une connexion PostgreSQL personnalisée, copier
`metier/.env.example` vers `metier/.env`, adapter ses variables et passer
`--env-file metier/.env` aux commandes `uv run`. Régler les mêmes valeurs
dans l'environnement de Compose. Django ne charge pas `.env`
automatiquement. Si le port **8000** est occupé, démarrer Django sur un autre
port et définir `API_PROXY_TARGET=http://127.0.0.1:<port>` pour Vite ; le
préfixe côté navigateur se règle avec `VITE_API_ROOT`.

Le [cahier de recette](tests/cahier_de_tests.pdf), sa
[source lisible](tests/cahier_de_tests.html) et les commandes de
[reproduction](tests/README.md) documentent l'intégration. Le
[comparatif des pages entreprise](docs/research/company-pages-2026-10-01.md)
décrit les choix de présentation.

`--once` consomme au maximum un envoi et termine. Lancer également
`purge_accounts` pour traiter les demandes de suppression ;
`cleanup_backend` nettoie les sessions expirées, compteurs et réponses
d'import expirées. Ces commandes sont prévues pour une exécution planifiée
par l'exploitant.

## Architecture HTTP

La [spec de migration DRF](docs/DRF_MIGRATION_SPEC.md) décrit le contrat préservé et les recommandations officielles. Les vues utilisent `api_view`, les serializers de commande et de lecture ont des champs explicites, et les services gardent les transactions et règles métier. Authentification par session avec CSRF, y compris pour les requêtes anonymes. Pagination et erreurs conservent le format v1.

## Parcours API

Les routes privées du candidat demandent une session. L'inscription, la
connexion, le reset de mot de passe et la lecture du catalogue public n'en
demandent pas. Lire [le contrat API](docs/API.md) pour les corps et erreurs.

1. `GET /api/v1/auth/csrf/` : conserver le cookie et le `csrf_token`.
2. `POST /api/v1/auth/register/` : compte et profil minimal inactifs, en attente de validation par un superviseur.
3. Après activation, `POST /api/v1/auth/login/` crée la session et retourne un nouveau jeton CSRF.
4. Compléter `/profile/`, ses expériences/formations et `/preferences/`.
5. Envoyer un PDF à `/documents/`, puis sélectionner le CV avec `/profile/resume/`.
6. Consulter `/offers/` ; créer `/applications/` avec l'offre et sa source.
7. `/applications/<id>/prepare/` prépare une révision factuelle. `/revisions/` crée une correction sans modifier l'historique.
8. `/approve/` reçoit l'ID de révision, son hash affiché et une clé UUID d'idempotence. Le worker soumet seulement si l'adaptateur est explicitement disponible.
9. Consulter `/runs/` et `/events/`, puis gérer tâches, entretiens et statuts.

Les réponses `missing_fields` servent au frontend à demander les informations manquantes. Un timeout après soumission donne `uncertain` : aucune relance automatique. L'action `/resolve/` nécessite une vérification humaine et une référence/explication, après expiration du worker en vol.

## Sources et connecteur

Créer une `Company` et un `SourceBoard` depuis le shell Django ou l'admin catalogue ; le board doit avoir `provider=greenhouse`, `instance=global`, `board_key=<token public>`, `company`, `enabled=True`, `base_url` et `submission_mode=unsupported` par défaut.

```bash
uv run --project metier metier/app/manage.py import_offers --board-id 1
```

Le connecteur lit le catalogue public sur un hôte fixe. Réimporter conserve les IDs ; un import incomplet ne ferme aucune offre. Le catalogue ne devine pas les contrats, pays, salaires ou modes de travail absents des données structurées.

**Envoi partenaire Greenhouse uniquement**, réservé aux boards pour lesquels l'opérateur possède une clé autorisée. L'activer exige `submission_mode=partner_api` et `GREENHOUSE_API_KEYS='{"board-token":"secret"}'` dans l'environnement. Ne pas stocker ces clés dans un board ni dans Git. Aucun ATS n'a encore été choisi pour le lancement ; ce connecteur reste dormant par défaut.

Cette première intégration prend en charge identité, questions texte, choix simples/multiples et PDF CV/lettre. Les formulaires de localisation, conformité, démographie, fichiers personnalisés et types inconnus sont bloqués explicitement avant l'envoi. Leur prise en charge nécessite l'extension et la validation du connecteur. La préparation actuelle reprend les faits confirmés du profil ; elle ne génère pas encore de rédaction IA ni d'extraction automatique de CV.

## Fichiers et suppression

Développement : fichiers privés dans `.private-media/`, jamais servis comme des fichiers statiques. Production R2 : définir `PRIVATE_STORAGE_BACKEND=r2`, `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` ; bucket privé. Les téléchargements passent par le contrôle de propriétaire. PDF uniquement, 10 Mio, structure analysée, contenu actif refusé, empreinte vérifiée. Prévoir également une limite de corps de **12 Mio au reverse proxy** ; le plafond Django de mémoire ne remplace pas cette limite.

`POST /account/delete/` désactive le compte immédiatement. `purge_accounts` efface les blobs avant les métadonnées ; une panne conserve les clés permettant une reprise. La purge attend toute soumission incertaine ou upload encore `pending`. Après arrêt confirmé des processus d'upload, l'opérateur peut récupérer des IDs exacts vieux de 24 h avec `purge_accounts --recover-pending <ids> --confirm-upload-workers-stopped`. L'âge seul n'autorise pas la suppression. Une soumission incertaine nécessite d'abord une vérification opérateur du résultat distant.

## Docker applicatif

```bash
docker compose --profile app build
docker compose --profile app run --rm web .venv/bin/python app/manage.py migrate
docker compose --profile app up -d web worker
```

Le profil `app` ajoute web/worker et leurs volumes sans changer le port local de PostgreSQL. Le lancement n'applique pas automatiquement de migrations. Image exécutée avec un utilisateur non root. `/health/live/` vérifie le processus, `/health/ready/` vérifie PostgreSQL.

## Production

Fournir `DJANGO_DEBUG=false`, une `DJANGO_SECRET_KEY` aléatoire d'au moins 50 caractères, `DJANGO_ALLOWED_HOSTS`, `POSTGRES_PASSWORD` propre à l'environnement, `PUBLIC_BASE_URL=https://...`, R2 et un backend email. `MAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` active `SMTP_HOST/PORT/USERNAME/PASSWORD/TLS` (TLS par défaut). La console email est destinée au développement.

```bash
uv run --project metier --env-file metier/.env metier/app/manage.py check --deploy
uv run --project metier --env-file metier/.env metier/app/manage.py collectstatic --noinput
```

HTTPS, cookies secure et HSTS sont activés quand DEBUG est désactivé. Si le TLS est terminé par un proxy, `TRUST_HTTPS_PROXY=true` exige que ce proxy **écrase** `X-Forwarded-Proto`. Ne pas faire confiance aux en-têtes envoyés directement par un client. Servir `staticfiles/` depuis le proxy pour l'admin, jamais `.private-media/`. Effectuer une sauvegarde PostgreSQL et vérifier la restauration avant une mise en production.

## Vérifier

```bash
uv run --project metier metier/app/manage.py check
uv run --project metier metier/app/manage.py makemigrations --check --dry-run
uv run --project metier metier/app/manage.py test jobboard --noinput
uv run --project metier ruff check metier/app/jobboard metier/app/config --select E4,E7,E9,F,I
```

Les tests utilisent une base PostgreSQL dédiée, jamais SQLite. `TEST_DATABASE_NAME` permet un nom isolé. Les tests transactionnels utilisent de vraies connexions concurrentes pour les approbations et les claims du worker. Les appels R2/ATS sont contrôlés dans les tests : ils ne prouvent pas une intégration distante activée et n'envoient aucune candidature réelle.

## Moteur de stages en Europe

Le catalogue public, les recommandations et les suggestions du tableau de bord publient uniquement les **stages confirmés en Europe**, ouverts et récemment vérifiés. Ce périmètre est imposé par le serveur : les paramètres client ne peuvent pas faire apparaître des emplois ordinaires ou des annonces hors Europe. Les données techniques importées d'un board complet ne sont pas toutes publiées.

Voir la [spec et son bilan de livraison](docs/INTERNSHIP_ENGINE_SPEC.md), le [guide d'exploitation](docs/INTERNSHIP_ENGINE_RUNBOOK.md) et le [contrat API](docs/API.md). Le worker du catalogue est séparé du worker d'envoi de candidatures.

```bash
uv run --project metier metier/app/manage.py run_catalogue_worker --once
uv run --project metier metier/app/manage.py re_enrich_catalogue --all
```

Le premier traite une passe de tâches arrivées à échéance ; le second recalcule les preuves et l'éligibilité depuis les données déjà importées, sans réseau ni suppression d'historique. Pour des collectes périodiques, superviser `run_catalogue_worker` sans `--once`, ou utiliser le service Compose `catalogue-worker` après construction de l'image et application des migrations.
