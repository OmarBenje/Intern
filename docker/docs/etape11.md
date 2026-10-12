# Étape 11 — Service de données

## Objectif et livrables

Obtenir le jeu fictif dans PostgreSQL, avec persistance dans un volume nommé
et accès réservé au réseau de la couche métier.

- [Déclaration du service, du réseau et du volume](../compose.yaml).
- [Variables d'environnement à renseigner](../.env.example).
- [Procédure d'initialisation et de persistance](../PROCEDURE.md).
- [Vérificateur de peuplement](../verifier-donnees.sh).

Les deux scripts SQL de la couche données sont réutilisés sans modification.
Le code applicatif et le déploiement VM sont conservés.

## Prérequis examinés

La procédure VM décrit les installations PostgreSQL, Django/Gunicorn et Nginx.
Les variables de connexion sont externalisées dans la couche métier.
Le rapport de l'étape 10 contient trois séries de mesures et leur configuration.
Ces éléments permettent de préparer le redéploiement de la même application.
Le temps humain de mise en place VM n'a pas été mesuré.

## Contrôles exécutés le 12 octobre 2026

| Vérification | Résultat |
| --- | --- |
| Lecture YAML avec PyYAML | Réussie |
| Un service `donnees`, image PostgreSQL versionnée | Réussi |
| Variables base, utilisateur et mot de passe obligatoires | Réussi |
| Volume nommé au répertoire de données PostgreSQL 16 | Réussi |
| Deux sources SQL existantes, lecture seule, ordre schéma puis données | Réussi |
| Un seul réseau interne, aucun port publié | Réussi sur la déclaration |
| Sonde TCP vers le serveur final | Présente ; comportement à vérifier en exécution |
| Syntaxe `sh -n docker/verifier-donnees.sh` | Réussie |
| `git diff --check` | Réussi |
| Validation native `docker compose config` | Non exécutée : moteur requis indisponible |
| Démarrage, peuplement dans le conteneur et persistance | Non exécutés |
| Connexion depuis le métier et refus depuis le proxy | À vérifier après ajout de ces services |

## Limite d'exécution

Le programme `docker` disponible est une enveloppe Podman et le socket Docker
pointe vers un socket Podman. Les commandes `docker --version` et
`docker compose version` échouent avant de lire le projet :

```text
Emulate Docker CLI using podman.
Failed to obtain podman configuration: set sticky bit on: chmod /run/user/1000/libpod: read-only file system
```

Docker Engine n'est donc pas disponible pour cette validation. Les vérifications
statiques ne constituent pas une preuve de peuplement ou de persistance Docker.
La procédure indique les commandes pour produire ces preuves sur le moteur requis.
Les fichiers de résultats ne sont pas créés avant leur exécution réelle.

État : **configuration préparée et contrôlée statiquement ; validation Docker
restante**. Aucune approbation de l'étape n'est déduite de cet état.
