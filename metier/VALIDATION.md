# Validation locale de la couche métier

Date : 11 octobre 2026.

## Périmètre contrôlé

- chargement de la configuration Django après déplacement du backend ;
- absence de migration manquante ;
- inscription candidat et recruteur en attente de validation ;
- connexion, session, CSRF et refus des comptes inactifs ;
- séparation des rôles et accès limités au propriétaire ;
- cycle métier principal d'une candidature ;
- imports Python et règles statiques essentielles ;
- absence d'une seconde copie de `manage.py`, `config/` ou `jobboard/`.

## Résultats

| Contrôle | Résultat |
| --- | --- |
| `manage.py check` | Aucun problème signalé |
| `makemigrations --check --dry-run` | Aucune migration manquante |
| Tests ciblés Django/PostgreSQL | 41 tests réussis |
| Ruff `E4,E7,E9,F,I` | Aucun problème signalé |
| `git diff --check` | Aucun défaut d'espacement |
| Recherche des anciennes sources à la racine | Aucune copie trouvée |

Les tests ont utilisé une base PostgreSQL temporaire séparée. Ils ne modifient
pas la base de démonstration et ne contactent aucun service distant. Le fichier
`api.http` reste à exécuter avec le serveur lancé pour la présentation
interactive au jury.
