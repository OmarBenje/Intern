# Validation locale — Étape 3, couche données

**Date :** 11 octobre 2026.

## Méthode

La validation a utilisé **PostgreSQL 16.10**, **psql/pg_dump 16.13**,
**Django 6.1.1** et **psycopg 3.3.6**, avec des bases isolées pour la génération,
la restauration SQL et les tests Django. Les fichiers de démonstration ont été
placés dans un stockage privé dédié aux vérifications.

## Résultats

| Contrôle exécuté | Résultat |
| --- | --- |
| Création autonome du schéma et peuplement SQL | Réussis, transactions validées |
| Treize consultations SQL | Réussies ; [sortie SQL](resultats_requetes.txt) |
| Vérificateur direct des données et contraintes | **34 vérifications réussies** ; [sortie](resultats_sql.txt) |
| Tests Django schéma, migrations et recruteurs | **43 tests réussis** ; [sortie](resultats_django.txt) |
| `manage.py check` | Aucun problème signalé |
| `makemigrations --check --dry-run` | Aucune modification de modèle non couverte |
| `migrate --check` après restauration SQL | Aucun historique de migration manquant |
| Génération par migrations neuves et `seed_dev` final | Réussie ; mêmes cas de recette ; [sortie](resultats_generation.txt) |
| Vérification Django du mot de passe des huit comptes | Réussie ; huit sels et empreintes distincts |
| Empreintes des trois PDF privés | Correspondent aux métadonnées en base |
| Relance de `seed_dev` sur une base peuplée | Refusée sans écrasement |
| Réimport du schéma ou des données sur la base restaurée | Refusé |
| Ruff sur les nouveaux scripts et migrations | Réussi |
| Script `demarrer.sh` sur une base isolée neuve | Création, imports, consultations et 34 vérifications réussis ; [sortie](resultats_lancement.txt) |
| Relance de `demarrer.sh` sur la même base | Refusée avant import |

Le script de lancement a été exécuté sur un serveur PostgreSQL temporaire
accessible par socket locale. La commande de démarrage Compose documentée
comme option n'a pas été exécutée dans cette vérification.

Les 34 vérifications couvrent les effectifs et cas limites, l'activation,
la vérification distincte des recruteurs, les hashes, l'absence d'envoi externe,
puis **douze écritures invalides refusées** : entreprise absente ou inconnue,
CV courant d'un tiers, source d'une autre offre, dossier en double, login en
double, statut invalide, mauvais recruteur destinataire, CV transmis d'un tiers,
candidat miroir falsifié, type de CV invalide et suppression d'une offre
référencée. Un dernier contrôle confirme le recalcul automatique de l'alias du
hash. Les écritures de test sont annulées ; l'insertion de doublon emploie un ID
explicite pour ne pas avancer une séquence.

## Reproduire les vérifications

Depuis la racine d'Intern, configurer les variables `PG*` pour une base
isolée, puis suivre [l'installation SQL](README.md). Pour le vérificateur :

```sh
metier/.venv/bin/python donnees/verifier.py
```

Pour les tests Django, configurer les variables `POSTGRES_*` vers cette même
base et un nom de base de test distinct :

```sh
export TEST_DATABASE_NAME=test_intern_dev3
metier/.venv/bin/python metier/app/manage.py check
metier/.venv/bin/python metier/app/manage.py makemigrations --check --dry-run
metier/.venv/bin/python metier/app/manage.py migrate --check
metier/.venv/bin/python metier/app/manage.py test \
  jobboard.tests.test_schema \
  jobboard.tests.test_migrations \
  jobboard.tests.test_recruiters --noinput
```

Le rôle PostgreSQL des tests doit pouvoir créer une base de test.
`verifier.py` interroge PostgreSQL directement, sans utiliser l'ORM pour les
écritures invalides. Il vérifie les codes SQLSTATE et, lorsque nécessaire,
le nom de la contrainte qui a refusé l'écriture.

## Limites et prochaines étapes

### Revue des doublons et adaptation du CV

Les 251 fichiers Python source ont été comparés par empreinte, en excluant les
environnements virtuels, caches et dépendances : aucun fichier source non vide
de plus de 150 octets n'est identique à un autre. La liste de comptes qui était
recopiée dans `seed_dev.py` et `exporter.py` a été centralisée dans
`donnees/jeu_fictif.py`. Le vérificateur conserve des attentes indépendantes,
afin qu'une erreur dans le générateur ne modifie pas aussi les résultats attendus.

Le schéma SQL livré est un export des migrations, et `data.sql` un export du
jeu fictif : ce sont des livrables nécessaires à l'installation autonome,
sans seconde logique de génération à maintenir. Le blueprint historique dans
`docs/database/` décrit une conception antérieure et n'est pas utilisé pour
installer cette étape. Les clés composites et les champs miroirs de transmission
ont un rôle distinct documenté dans `MODELE.md` ; ils ne dupliquent pas les
contrôles HTTP de la prochaine étape.

Le CV générique d'une page est produit par `generer_cv.py`, source unique de
son contenu. Le rendu a été inspecté visuellement. Après génération du PDF,
les exports ont été régénérés et restaurés dans des bases isolées. Les 34
vérifications SQL ont réussi ; les huit mots de passe et les trois copies
privées du CV ont été contrôlés après restauration.

Cette validation prouve l'exécutabilité des livrables SQL et les invariants
énumérés. Elle ne valide pas l'ensemble de l'application : les 43 tests
sont une sélection pertinente pour la couche données.

À l'étape 4, reprendre et vérifier les contrats d'inscription et d'activation,
les sessions/CSRF, les autorisations, la candidature directe et les conditions
de publication. À l'étape 5, vérifier les écrans et leur fidélité au prototype.
La recette complète, l'installation de démonstration et les tests navigateur
relèvent de l'étape 6. La base ne peut pas déterminer l'identité d'une session
HTTP : R2 et R6 nécessitent aussi les contrôles serveur décrits dans le modèle.

Ce rapport porte sur la couche données. Il ne couvre pas la validation
interactive du prototype, le déploiement, les appels ATS, les envois réels
ou les tests de charge.
