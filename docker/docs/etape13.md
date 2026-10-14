# Étape 13 — Proxy et composition

## Objectif et livrables

Assembler les trois couches pour servir Intern depuis un seul point d'entrée.

- [Image du proxy](../proxy.Dockerfile) et [configuration Nginx](../proxy.conf).
- [Composition des trois services](../compose.yaml).
- [Commandes de démarrage, arrêt et redémarrage](../demarrer.sh).
- [Procédure](../PROCEDURE.md).
- [Capture réelle des trois services sains](etape13-services.png).
- [Preuves de composition et de redémarrage](preuves-etape13.json).

## Réalisation

Le proxy utilise l'image officielle Nginx 1.28.0 Alpine. Le client est construit
avec Node 22.23.3 Alpine et `VITE_API_ROOT=/api/v1`. Les statiques Django sont
collectés depuis l'image métier, sans nouvelle définition des dépendances.
L'image finale contient Nginx, sa configuration, le client et les statiques.

Les routes API, administration et santé sont transmises à `metier:8000`.
Le Host est conservé pour les sessions et le CSRF. Seul le proxy publie
`127.0.0.1:8080:80` ; il rejoint uniquement `frontal`. Le métier rejoint
`frontal` et `interne`, tandis que PostgreSQL rejoint uniquement `interne`.
`pgdata` reste le seul volume nommé.

Le métier attend la santé de PostgreSQL et le proxy attend celle du métier.
Le script métier est l'`ENTRYPOINT` de son image, avec Gunicorn comme `CMD` :
la composition conserve ainsi les vérifications et la commande de lancement.
Le script de construction assemble les images dans l'ordre métier puis proxy.

## Vérifications réelles du 14 octobre 2026

Les essais utilisent **Podman 5.8.2 et podman-compose 1.5.0**, hors du sandbox,
dans le projet isolé `intern-etape13` et sur un nouveau volume fictif.
Une surcharge locale désactive le label SELinux du seul conteneur PostgreSQL
pour lire les montages SQL. Elle ne change ni les réseaux ni les ports
et ne fait pas partie de la configuration Docker livrée.

| Contrôle | Résultat |
| --- | --- |
| Construction métier et proxy | Réussie ; cache de couches réutilisé |
| Trois services, deux réseaux et un volume nommé | Conforme |
| Santé des trois conteneurs | `healthy` avant et après redémarrage |
| Publication de port | Proxy seulement, boucle locale 8080 |
| Réseaux réellement attachés | Conformes au découpage ci-dessus |
| `nginx -t` | Réussi |
| `/health/ready/` via le proxy | HTTP 200, requête SQL réelle réussie |
| Vérificateur SQL depuis le métier | **34 contrôles réussis**, écritures d'essai annulées |
| Arrêt par une commande Compose `down` | Réussi ; aucun conteneur du projet en marche |
| Volume après arrêt | Conservé |
| Redémarrage par une commande Compose `up -d --no-build` | Réussi, trois services sains |
| Données après recréation | 34 contrôles SQL réussis ; initialisation ignorée sur volume existant |
| Recette Chrome réelle | **Huit contrôles réussis** |
| Capture des services | Fenêtre du terminal réellement capturée et inspectée |

La [recette navigateur](recette-etape13.txt) couvre sessions et CSRF,
connexion candidat, catalogue, CV privé, connexion recruteur, administration
et statiques. Tous les appels API du navigateur utilisent
`http://127.0.0.1:8080`, sans erreur JavaScript.
Les [résultats SQL](sql-etape13.txt) et les [preuves JSON](preuves-etape13.json)
conservent les observations. Le scénario de recette existant est réutilisé
avec un dossier et un préfixe de sortie distincts : les preuves VM sont conservées.

![Trois services en marche sur Podman](etape13-services.png)

[Connexion réelle](etape13-connexion.png) ·
[Tableau de bord réel](etape13-tableau-de-bord.png).

## Tailles des images

| Image | Taille exacte non compressée |
| --- | ---: |
| Métier avec script de démarrage intégré | **388 668 320 octets** |
| Proxy, client et statiques inclus | **55 975 819 octets** |
| PostgreSQL 16.15 Bookworm | **450 942 316 octets** |

Les identifiants figurent dans les preuves JSON. Ces valeurs ne sont pas
l'empreinte disque totale, qui doit tenir compte des couches partagées
et du volume de données.

## Limites

Les trois couches ont été exécutées réellement avec Podman et Compose.
**Docker Engine et Docker Compose natif restent à vérifier**.
Le script `demarrer.sh` est vérifié statiquement ; les opérations équivalentes
de démarrage et d'arrêt ont été exécutées avec podman-compose, qui ne propose
pas le même argument `--wait`. La santé a été attendue puis contrôlée
explicitement pendant ces essais.

Le projet isolé reste en marche après la capture, sur le port 8080.
L'arrêter avant de lancer un autre projet sur ce port. Aucun déploiement VM
n'a été modifié. La matrice complète de joignabilité et la comparaison des
ressources relèvent de l'étape suivante.

Références : [image officielle Nginx](https://hub.docker.com/_/nginx),
[image officielle Node](https://hub.docker.com/_/node).
