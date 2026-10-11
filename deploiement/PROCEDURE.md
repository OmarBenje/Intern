# Déploiement sur trois machines virtuelles

Exécuter les étapes dans cet ordre, en conservant le même répertoire local
pour les VM, les clés d'administration et les exports. Les secrets et les
images restent hors du dépôt. Les scripts utilisent VirtualBox et SSH depuis
le poste de préparation ; aucun code applicatif n'est modifié.

| Étape | Procédure | Vérification et résultats |
| --- | --- | --- |
| 7 — Machines | [Modèle, clones et identités](scripts/PROCEDURE.md) | [Rapport et capture VirtualBox](docs/etape7.md) |
| 8 — Réseau | [Plan d'adressage et Netplan](reseau/README.md) | [Adresses, routes et pings](docs/etape8.md) |
| 9 — Services | [PostgreSQL, Django et Nginx](DEPLOIEMENT.md) | [Services et recette navigateur](docs/etape9.md) |
| 10 — Validation | [Isolation, mesures et OVA](VERIFICATION.md) | [Matrice et exports](docs/etape10.md), [mesures de référence](docs/mesures.md) |

Le client consulte uniquement le proxy via `http://127.0.0.1:8080`.
Les liaisons internes utilisent `intnet-app` : proxy `10.10.10.10`, métier
`10.10.10.20`, base `10.10.10.30`. Seul le proxy conserve un adaptateur NAT.
Les règles d'accès et les réglages des services figurent dans les procédures
des étapes 8 et 9.
