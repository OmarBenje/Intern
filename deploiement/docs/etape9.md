# Étape 9 — Déploiement réparti vérifié

## Objectif et réalisation

Les trois couches d'Intern sont installées sur les VM Ubuntu Server 24.04 LTS,
dans l'ordre données, métier, proxy. Le code applicatif est inchangé ; les
adresses, identifiants et paramètres HTTP sont externalisés dans les
[configurations et la procédure de déploiement](../DEPLOIEMENT.md).

| Machine | Service et adresse | Snapshot avant installation |
| --- | --- | --- |
| vm-donnees | PostgreSQL 16, `10.10.10.30:5432` | avant donnees |
| vm-metier | Django/Gunicorn, `10.10.10.20:8000` | avant metier |
| vm-proxy | Nginx, `10.10.10.10:80` et `10.0.3.15:80` | avant proxy |

Les snapshots et leurs UUID réellement relevés sont conservés dans le
[manifeste des snapshots](snapshots-etape9.json). Les deux scripts SQL livrés
ont créé une base neuve `intern`, contenant huit comptes et quatre offres
fictifs. Le rôle `intern_user` possède les tables sans privilèges de
superutilisateur, de création de base ou de rôle.

PostgreSQL écoute uniquement sur l'adresse interne. Les connexions réseau à
la base exigent SCRAM et proviennent uniquement de la machine métier, selon
`pg_hba.conf` et le filtrage nftables. Gunicorn utilise un compte système dédié
et un environnement privé extérieur au dépôt. Nginx sert le build React, les
statiques Django et transmet les requêtes d'API au métier en conservant le Host.

## Vérifications exécutées

Le 12 octobre 2026, les trois VM ont été arrêtées puis démarrées ensemble.
PostgreSQL, nftables, Gunicorn et Nginx sont actifs et activés au démarrage.
Les ports d'écoute et les routes correspondent à la configuration livrée.
Les VM métier et données n'ont plus d'adaptateur NAT ni de route IPv4 par défaut.
Seul le proxy conserve le NAT et la redirection `127.0.0.1:8080 → 80` ; la
redirection d'administration SSH temporaire est retirée.

Les contrôles Django et les migrations ont réussi. Les **34 vérifications SQL**
ont été exécutées depuis la VM métier contre la base réelle ; leurs écritures
d'essai ont été annulées. Les empreintes SHA-256 des **249 fichiers applicatifs**
et des **15 fichiers du build client** sont identiques entre le poste de
préparation et les VM. Les cinq configurations installées contrôlées sont
également conformes aux fichiers livrés.

L'hôte reçoit un HTTP 200 de `/health/ready/`, avec une requête réelle de Django
vers PostgreSQL. La **recette navigateur de huit contrôles** a réussi contre
les services réels, sans simulation de l'API :

1. Disponibilité de toute la chaîne proxy, métier, base.
2. Refus d'une session anonyme et d'une mutation sans jeton CSRF.
3. Connexion candidat dans React et session conservée après rechargement.
4. Catalogue fictif accessible depuis le proxy.
5. Téléchargement du CV privé par son propriétaire.
6. Connexion recruteur et chargement de son tableau de bord.
7. Administration Django et fichiers statiques accessibles.
8. Appels d'API sur la seule origine du proxy et absence d'erreur JavaScript.

Preuves : [sorties des contrôles VM](preuves-etape9.txt),
[manifest des empreintes](artefacts-etape9.json),
[résultats navigateur](recette-etape9.txt). Les scripts reproductibles sont
[verifier_etape9.py](../scripts/verifier_etape9.py) et
[recette_etape9.mjs](../scripts/recette_etape9.mjs).

## Captures réelles

![Connexion servie par le proxy](etape9-connexion.png)

![Tableau de bord candidat chargé depuis les trois VM](etape9-tableau-de-bord.png)

Ces captures proviennent du navigateur connecté à `http://127.0.0.1:8080`,
avec les comptes fictifs livrés. Les VM restent démarrées pour la consultation.

## Portée et suite

La configuration `DJANGO_DEBUG=true` permet cette démonstration HTTP locale
avec le code existant. Les secrets PostgreSQL et Django sont générés localement,
stockés hors du dépôt et transférés dans un fichier invité protégé.

L'installation et son fonctionnement après redémarrage sont vérifiés.
La matrice complète des accès autorisés et interdits, les mesures répétées
avec médiane et les trois exports OVA sont consignés dans le
[rapport de l'étape 10](etape10.md).
