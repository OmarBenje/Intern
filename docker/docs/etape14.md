# Étape 14 — Isolation et comparaison mesurée

## Livrables

| Livrable | Emplacement |
| --- | --- |
| Matrice remplie, tableau comparatif et analyse | [comparaison.md](../../docs/comparaison.md) |
| Compte rendu de deux pages | [PDF](../../docs/compte_rendu_comparaison.pdf) |
| Neuf tentatives de connexion | [matrice brute](joignabilite-etape14.json) |
| Trois séries et trente latences | [mesures brutes](mesures-etape14.json) |
| 34 contrôles SQL sur Docker Engine | [résultats SQL](sql-etape14.txt) |
| Huit contrôles navigateur sur Docker Engine | [recette](recette-etape14.txt) |
| Code Python réellement exécuté | [empreintes](empreintes-app-etape14.json) |
| Santé, persistance après recréation et contenu final | [preuve de synthèse](verification-etape14.json) |
| Reproduction | [procédure](../PROCEDURE.md) et [vérificateur](../verifier-etape14.py) |

## Moteur et protocole

Campagne réelle sur **Docker Engine 28.3.3 rootless**, **Docker Compose 2.39.4**,
VPNKit et fuse-overlayfs, sur le même poste Linux que la référence VM.
Le moteur est isolé et ne remplace pas Podman. Ses images sont importées depuis
les constructions existantes et identifiées dans les mesures brutes.
Les VM et les conteneurs Podman de démonstration sont arrêtés pendant la campagne.
Les conteneurs Docker sont laissés sains après les essais.

Les neuf liaisons sont testées avec les trois services sains. Les quatre cas
interdits utilisent les adresses réellement attribuées, pour ne pas confondre
un échec DNS avec l'isolation réseau. Les trois séries partent de conteneurs
arrêtés, avec le volume existant, comme les VM partent d'un état installé.
Le sondage HTTP a un intervalle de 0,5 seconde et un délai de cinq secondes.
Le client et la route correspondent à la référence VM ; quatre offres sont
confirmées à chaque consultation. Trente secondes au repos précèdent la mémoire
et dix appels sont réalisés par série. Les médianes sont calculées à partir
des valeurs brutes, sans suppression d'une série lente.

La mémoire comprend le moteur et les auxiliaires rootless, les shims et les
processus FUSE, même lorsqu'ils ne sont plus descendants du daemon.
Le disque compte une seule fois les couches communes et les liens physiques.
Les répertoires et métadonnées du moteur, les archives et caches de construction
ne sont pas assimilés aux fichiers des images et du volume.

Docker annonce pour ces images **372 903 397 octets** (métier),
**54 419 777 octets** (proxy) et **442 763 077 octets** (PostgreSQL).
Les identifiants correspondent aux images précédemment inspectées avec Podman.
Les tailles annoncées par les deux moteurs diffèrent ; elles sont conservées
avec leur moteur de mesure. L'empreinte disque comparative est calculée depuis
les fichiers uniques et leurs blocs, et non en additionnant ces trois tailles.

## Contrôle des erreurs fréquentes

| Erreur à éviter | Contrôle et résultat |
| --- | --- |
| Schéma modifié ignoré sur volume existant | Imports uniquement au premier démarrage ; `migrate --check` refuse une migration absente ; réinitialisation destructive explicitement distinguée de `down` |
| Métier lancé avant la disponibilité SQL | Dépendance `service_healthy` ; sonde TCP de PostgreSQL ; trois services sains à chaque relevé |
| Base réglée sur localhost | `POSTGRES_HOST=donnees` ; 34 contrôles SQL exécutés depuis le métier |
| Perte des données après recréation | Volume nommé `pgdata` ; arrêt/recréation sans suppression du volume et contrôles SQL après relance |
| Image métier dépassant le gigaoctet | Base slim ; exclusions actives ; Git, uv et cache uv absents de l'image finale vérifiée |
| Réinstallation des dépendances après changement de code | Manifest et verrou avant le code ; cache de couches effectivement réutilisé lors des constructions |
| Base accessible depuis l'hôte | Aucun port publié sur données ou métier ; deux tentatives depuis l'hôte échouent ; seul le proxy publie 8080 sur la boucle locale |

Le proxy et la base n'ont aucun réseau commun ; leurs accès directs échouent.
Les huit contrôles navigateur confirment le chemin client/proxy/métier/base,
les sessions/CSRF et les statiques. La configuration Nginx est testée réellement.

## Organisation finale

```text
docker/
  metier.Dockerfile
  proxy.Dockerfile
  compose.yaml
  .dockerignore
  PROCEDURE.md
  proxy.conf
  demarrer.sh
  verifier-etape14.py
  rediger-comparaison.py
  generer-comparaison.py
  docs/                     preuves et captures
docs/
  comparaison.md
  compte_rendu_comparaison.pdf
deploiement/                déploiement VM conservé
```

`.dockerignore` à la racine est un lien vers `docker/.dockerignore`, pour que
le contexte de construction utilise cette source unique. Le lien
`docker/Dockerfile` garde les références existantes vers `metier.Dockerfile`.
Les scripts SQL et le CV restent dans `donnees/` : les montages et constructions
les réutilisent, sans copie concurrente de leurs sources.

## Limites de la comparaison

La campagne décrit ces deux configurations ; elle n'isole pas causalement
l'effet de l'hyperviseur. Les versions correctives de Python et Nginx, les quotas
CPU/RAM, les workers Nginx, les sondes de démarrage et le stockage diffèrent.
Les empreintes Python révèlent aussi une différence du service de logos par
rapport à la référence VM. Les quatre offres fictives et la recette sont
vérifiées sur le déploiement actuel. Les snapshots sont comptés côté VM,
pas côté Docker ; le moteur et ses auxiliaires sont comptés côté Docker,
tandis que VBoxSVC était exclu côté VM. La RSS peut doubler des pages partagées.

**Le temps humain de mise en place depuis zéro n'a pas été chronométré**.
Le tableau indique donc « non chronométré » au lieu d'inventer une durée.
Le PDF explique les écarts chiffrés, leurs causes plausibles et les contreparties
de l'isolation par noyau partagé. Son nombre de pages et son rendu ont été contrôlés.

Référence : [Docker Engine rootless](https://docs.docker.com/engine/security/rootless/).
