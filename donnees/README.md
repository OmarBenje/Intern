# Étape 3 — Couche données

Le jeu d'essai met en œuvre les données prévues dans
[l'analyse fonctionnelle](../analyse/cas_d_usage.md). Les scripts sont destinés
à PostgreSQL 16 et correspondent aux migrations Django actuelles, jusqu'à
`0034_recruiter_applicant_integrity`. Ils se restaurent sans lancer Django.

## Livrables à remettre

| Fichier | Rôle |
| --- | --- |
| [schema.sql](schema.sql) | Création des tables, clés, index, fonctions et contraintes |
| [data.sql](data.sql) | Jeu entièrement fictif, référentiels et historique de migrations |
| [requetes.sql](requetes.sql) | Treize consultations commentées, avec résultats attendus |
| [MODELE.md](MODELE.md) | Relations principales et correspondance avec R1–R6 |
| [VALIDATION.md](VALIDATION.md) | Procédure exécutée, preuves et limites |
| [cv_fictif.pdf](cv_fictif.pdf) | CV de démonstration sans donnée personnelle réelle |
| [schema_visuel.png](schema_visuel.png) / [PDF](schema_visuel.pdf) | Vue simplifiée des relations principales |

## Lancement guidé

Depuis la racine d'Intern, installer les dépendances Python avec
`uv sync --frozen`. Prévoir un serveur PostgreSQL 16 démarré, les clients
`psql` et `createdb`, et un compte autorisé à créer une base et l'extension
`pg_trgm`. Le serveur local configuré par le projet utilise le port 5433.

Si PostgreSQL est géré par la configuration Compose du projet, le démarrer
avec Docker Engine depuis la racine d'Intern :

```sh
docker compose up -d db
```

Utiliser les identifiants définis par cette configuration ou par le fichier
`.env`. Avec un serveur PostgreSQL déjà installé, renseigner son hôte, son
port et son utilisateur dans les variables ci-dessous.

```sh
export PGHOST=127.0.0.1
export PGPORT=5433
export PGUSER=intern_user
export PGDATABASE=intern_dev3
# Fournir le mot de passe via .pgpass ou PGPASSWORD si nécessaire.
bash donnees/demarrer.sh
```

Le script réalise l'installation SQL décrite plus bas et lance les vérifications.
Il s'arrête si la création échoue, notamment si la base existe déjà. Pour un
nouvel essai, choisir un nom de base neuf. La base reste disponible après la
vérification pour permettre les consultations.

Avec les mêmes variables de connexion, ouvrir une session SQL :

```sh
psql -X
```

Puis afficher les tables et quelques données :

```sql
\dt
SELECT title, status FROM jobboard_offer ORDER BY id;
SELECT username, is_active FROM auth_user ORDER BY id;
\q
```

Résultat attendu : quatre offres, huit comptes dont `attente` inactif,
et `PASS — 34 vérifications` à la fin du script. L'étape données se consulte
dans PostgreSQL ; les écrans de l'application sont décrits dans le prototype.
La [sortie du lancement vérifié](resultats_lancement.txt) conserve le résultat
d'une exécution sur une base isolée.

## Visuel des relations

![Relations principales](schema_visuel.png)

Le [PDF du schéma](schema_visuel.pdf) permet de lire ou partager le visuel.
Il représente neuf tables principales ; le schéma complet contient 72 tables.
Les résultats des consultations se trouvent dans [resultats_requetes.txt](resultats_requetes.txt).

Pour régénérer le visuel, utiliser les dépendances documentaires déjà définies
dans `analyse/requirements-docs.txt` et la commande `pdftoppm` (Poppler), puis :

```sh
python donnees/generer_schema.py
```

## Document de démonstration

Le CV présente un profil adapté à une recherche de stage dans une mise en
page en deux colonnes. C'est un document générique,
sans identité nominative, partagé par les trois profils de test ; ses trois
références de stockage privées permettent de vérifier les droits de propriété.

Pour régénérer le PDF, utiliser les dépendances documentaires déjà définies
dans `analyse/requirements-docs.txt`, puis :

```sh
python donnees/generer_cv.py
```

Après toute modification du PDF, régénérer le jeu fictif dans une base neuve
et réexporter `data.sql` : la taille et l'empreinte des documents doivent suivre
le fichier livré.

## Jeu fictif

| Compte | Rôle / état | Cas couvert |
| --- | --- | --- |
| `alice` | Candidate active | Un dossier transmis à `recruteur_a`, un CV |
| `bob` | Candidat actif | Un dossier transmis à `recruteur_b`, un CV |
| `vide` | Candidate active | Un CV, aucune candidature |
| `attente` | Candidat inactif | Compte en attente, aucun CV ni dossier |
| `recruteur_a` | Recruteuse vérifiée | Atelier Démo, un stage et une candidature reçue |
| `recruteur_b` | Recruteur vérifié | Même entreprise, autre stage et autre candidature |
| `recruteur_non_verifie` | Recruteuse non vérifiée | Compte actif, sans offre ; vérification distincte de l'activation |
| `admin` | Administrateur actif | Gestion et activation des comptes à vérifier à l'étape métier |

Trois entreprises : Atelier Démo (deux offres), Laboratoire Exemple (deux
offres sans candidature), Entreprise Sans Offre (aucune offre). Les quatre
offres sont des stages fictifs à Paris. Les deux transmissions sont des données
de recette préconstruites, sans envoi ni consentement d'une personne réelle.

E-mail : `<login>@example.test`. Mot de passe de démonstration commun :
`Intern-Demo-2026!`. Chaque compte a une empreinte **scrypt** avec un sel distinct.
Les sources utilisent `https://example.test` et `submission_mode=unsupported`.
Aucun import réseau ni worker n'est nécessaire.

## Installation SQL autonome

Créer une **nouvelle base dédiée**, par exemple `intern_dev3`. Le rôle
PostgreSQL doit pouvoir créer l'extension `pg_trgm`. Le client `psql` 16.13
ou ultérieur de la branche 16 prend en charge les commandes `\restrict`
présentes dans les exports.

Définir les variables standard PostgreSQL pour cette base :

```sh
export PGHOST=127.0.0.1
export PGPORT=5433
export PGUSER=intern_user
export PGDATABASE=intern_dev3
# Fournir PGPASSWORD ou un fichier .pgpass si le serveur le demande.
createdb "$PGDATABASE"
psql -X -v ON_ERROR_STOP=1 -f donnees/schema.sql
psql -X -v ON_ERROR_STOP=1 -f donnees/data.sql
psql -X -v ON_ERROR_STOP=1 -f donnees/requetes.sql
metier/.venv/bin/python donnees/verifier.py
```

Chaque import est transactionnel. La création échoue si les tables existent ;
le peuplement refuse des utilisateurs ou entreprises préexistants. Ne pas
exécuter `migrate` avant l'installation SQL. L'historique de migrations inclus
permet ensuite à Django de reconnaître ce schéma.

Pour les futurs téléchargements de CV, copier le PDF dans le stockage privé :

```sh
mkdir -p .private-media/dev/alice .private-media/dev/bob .private-media/dev/vide
cp donnees/cv_fictif.pdf .private-media/dev/alice/cv.pdf
cp donnees/cv_fictif.pdf .private-media/dev/bob/cv.pdf
cp donnees/cv_fictif.pdf .private-media/dev/vide/cv.pdf
```

Adapter le chemin si `PRIVATE_STORAGE_ROOT` est personnalisé. Ces fichiers ne
sont pas servis comme fichiers publics. Les dates de contrôle des sources sont
rafraîchies à l'import pour la démonstration locale ; cela ne constitue pas une
vérification sur Internet.

## Régénération à partir de Django

Sur une autre **base neuve dédiée**, après installation des dépendances du
projet, faire correspondre les variables Django à celles de PostgreSQL :

```sh
export POSTGRES_DB="$PGDATABASE"
export POSTGRES_HOST="$PGHOST"
export POSTGRES_PORT="$PGPORT"
export POSTGRES_USER="$PGUSER"
# Définir POSTGRES_PASSWORD comme PGPASSWORD si nécessaire.
export PRIVATE_STORAGE_BACKEND=local
export PRIVATE_STORAGE_ROOT=/tmp/intern-dev3-cv
metier/.venv/bin/python metier/app/manage.py migrate --noinput
metier/.venv/bin/python metier/app/manage.py seed_dev
metier/.venv/bin/python donnees/exporter.py
```

Choisir un répertoire privé neuf pour éviter les collisions de fichiers.
`seed_dev` est la source lisible du peuplement et refuse une base contenant déjà
des comptes ou entreprises. `exporter.py` vérifie les comptes de démonstration
avant l'export. Les définitions des comptes sont centralisées dans
`jeu_fictif.py`, utilisé par ces deux outils. Les migrations sont la source du schéma ; ne pas corriger le SQL
exporté seul sans mettre les migrations en cohérence.

Le [blueprint historique](../docs/database/schema.sql) documente une conception
antérieure. Il ne remplace pas les scripts de livraison de cette étape.
