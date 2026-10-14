# Étape 12 — Image de la couche métier

## Objectif et livrables

Construire l'application existante et accéder à PostgreSQL par le nom
`donnees`, sans port publié sur le métier.

- [Construction de l'image](../metier.Dockerfile).
- [Exclusion du contexte](../.dockerignore), source unique à la racine.
- [Composition des deux services](../compose.yaml).
- [Démarrage](../demarrer-metier.sh) et [vérificateur](../verifier-metier.sh).
- [Procédure et commande de mesure de taille](../PROCEDURE.md).

L'image comporte deux étapes : installation des dépendances verrouillées,
puis copie de l'environnement et du code dans une base Python réduite.
Le processus final utilise un compte sans privilèges et écoute sur toutes
les interfaces du conteneur. L'isolation vient des réseaux et de l'absence
de publication du port.

## Vérifications du 12 octobre 2026

| Contrôle | Résultat |
| --- | --- |
| YAML et chemins du contexte, Dockerfile et fichiers copiés | Réussis |
| Dépendances avant code, deux bases Python versionnées | Vérifiés statiquement |
| Cache d'installation absent de l'image finale | Décrit par la construction ; contenu final à vérifier |
| Une seule source Dockerfile et exclusion, avec liens valides | Vérifié |
| `POSTGRES_HOST=donnees`, port 5432 | Vérifié sur la déclaration |
| Métier sur frontal et interne, aucun port publié | Vérifié sur la déclaration |
| Dépendance conditionnée à la santé de la base | Vérifiée |
| Syntaxe des scripts shell | Réussie |
| Chargement local des paramètres Django | Réussi, sans connexion SQL |
| `manage.py check` local avec hôte `donnees` | Échec : nom accessible seulement dans le réseau des conteneurs |
| Construction et démarrage sur Docker Engine | Non exécutés : moteur requis indisponible |
| Connexion SQL depuis le métier, sonde HTTP et CV privés | À vérifier sur l'image construite |
| Taille de l'image | Non mesurée : image non construite |

Les commandes Docker disponibles délèguent toujours à Podman et échouent
avant l'exécution du projet, comme décrit au [rapport données](etape11.md).
La validation locale des paramètres ne prouve ni la compatibilité de toutes
les dépendances avec l'image cible ni la résolution DNS des services.

Les preuves de connexion, d'isolation et de taille seront générées par les
commandes de la procédure lors de leur exécution réelle. Aucun résultat Docker
n'est déduit des contrôles statiques.

État : **livrables préparés ; construction, connexion et taille sur Docker
Engine à vérifier**.

## Taille exacte de l'image

**Valeur en octets : non disponible.** La tentative de lecture du
14 octobre 2026 avec `docker image inspect intern-metier:etape12` échoue
avant l'inspection, car la commande Docker délègue à Podman et rencontre
l'erreur de configuration décrite ci-dessus. Aucun nombre n'a été mesuré.

La procédure affiche et conserve `taille_exacte_octets`, sans arrondi, ainsi
que l'identifiant de l'image. Ces résultats devront être reportés ici après
une construction et une inspection réussies sur Docker Engine.
