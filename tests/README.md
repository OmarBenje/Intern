# Recette d'intégration

Le [cahier de tests](cahier_de_tests.pdf) suit les parcours définis dans
l'analyse. Sa [source HTML](cahier_de_tests.html) permet de relire le tableau
et de régénérer le PDF. Le script [recette_navigateur.mjs](recette_navigateur.mjs)
exécute les contrôles T01 à T15 dans Chrome contre Vite, Django, Django Admin
et PostgreSQL réels. Le jeu de données est entièrement fictif.

## Préparer une base neuve et isolée

Depuis la racine d'Intern, installer les dépendances comme indiqué dans le
[README principal](../README.md). Ne pas réinitialiser le volume PostgreSQL de
développement. La commande suivante crée un conteneur **éphémère**, avec un
port différent de la base habituelle :

```sh
docker run -d --rm --name intern-recette-postgres \
  -e POSTGRES_USER=intern_recette \
  -e POSTGRES_PASSWORD=recette_locale_6 \
  -e POSTGRES_DB=intern_recette \
  -p 127.0.0.1:55432:5432 postgres:16-alpine
```

Attendre que la commande suivante confirme la connexion :

```sh
docker exec intern-recette-postgres pg_isready -U intern_recette -d intern_recette
```

Dans le terminal de la recette :

```sh
export POSTGRES_DB=intern_recette
export POSTGRES_USER=intern_recette
export POSTGRES_PASSWORD=recette_locale_6
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=55432
export PRIVATE_STORAGE_ROOT="$(mktemp -d /tmp/intern-recette-media.XXXXXX)"
uv run --project metier metier/app/manage.py migrate --noinput
uv run --project metier metier/app/manage.py seed_dev
```

`seed_dev` refuse une base déjà peuplée. Un nouveau conteneur permet une
nouvelle recette sans altérer les données de travail. Les identifiants fictifs
sont centralisés dans [le jeu d'essai](../donnees/jeu_fictif.py).

## Parcours navigateur et API

Dans un terminal conservant les variables PostgreSQL ci-dessus :

```sh
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5173 \
  uv run --project metier metier/app/manage.py runserver 127.0.0.1:8000 --noreload
```

Dans un deuxième terminal, depuis la racine d'Intern :

```sh
npm --prefix frontend run dev
```

Dans un troisième terminal, exécuter la recette. Chrome doit être installé :

```sh
RECETTE_PASSWORD='Intern-Demo-2026!' node tests/recette_navigateur.mjs
```

Le script vérifie l'inscription inactive puis son activation dans Django Admin,
le CSRF, la connexion candidat et recruteur, le catalogue, la cohérence
offre/source, la création d'un dossier sans doublon, les ressources privées
par ID modifié dans l'URL et la déconnexion. Il n'envoie aucune candidature à
un service externe. Si le port 8000 est occupé, choisir un autre port pour
Django, lancer Vite avec `API_PROXY_TARGET=http://127.0.0.1:<port>` et passer
`RECETTE_ADMIN_URL=http://127.0.0.1:<port>` au script.

## Contrôles complémentaires

Avec les mêmes variables PostgreSQL, utiliser un nom de base de test réservé à
la recette Django :

```sh
TEST_DATABASE_NAME=test_intern_recette \
  uv run --project metier metier/app/manage.py test jobboard --noinput
uv run --project metier metier/app/manage.py check
uv run --project metier metier/app/manage.py makemigrations --check --dry-run
uv run --project metier ruff check metier/app/jobboard metier/app/config --select E4,E7,E9,F,I
npm --prefix frontend run build
npm --prefix frontend run lint
npm --prefix frontend run test:e2e
```

Les tests Django couvrent les cas métier et l'administration sur une base de
test créée puis détruite automatiquement. Les tests Playwright du frontend
utilisent des réponses API contrôlées ; seul `recette_navigateur.mjs` vérifie
ici les trois couches ensemble. Les détails observés et les limites figurent
dans le cahier.

Après la recette, arrêter seulement le conteneur créé pour elle :

```sh
docker stop intern-recette-postgres
```

Le répertoire temporaire des CV fictifs peut ensuite être supprimé. Une
installation sur une machine virtuelle vierge et la revue du prototype
nécessitent encore un contrôle distinct avant le rendu final.

## Régénérer le PDF

```sh
node tests/generer_cahier.mjs
```

Le script lit `cahier_de_tests.html` et écrit `cahier_de_tests.pdf` sans accès
réseau. Toute correction du tableau doit être faite dans sa source HTML avant
de régénérer le PDF.
