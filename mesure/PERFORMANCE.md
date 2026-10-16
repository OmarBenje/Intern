# Configuration des nouvelles mesures

La même application est utilisée pour le déploiement normal et les mesures.
Seule la configuration des services dédiés aux mesures change :

| Environnement | `AUTH_LOGIN_RATE_LIMIT_ENABLED` |
| --- | --- |
| Déploiement normal | `true` par défaut, protection active |
| Docker de mesure | `false` dans `compose.test.yaml` |
| Service VM `intern-mesure17` | `false` dans son fichier séparé `mesure17.env` |

Ce réglage désactive les compteurs IP et identité de la connexion uniquement.
Les mots de passe, sessions, CSRF et autres limitations d'authentification
restent vérifiés. Ne pas ajouter `false` au fichier du déploiement normal.

Les étapes 15 et 16 reconstruisent l'image dédiée `intern-metier:mesure` et
appliquent la configuration au projet isolé. L'étape 17 reconstruit aussi cette
image, utilise son code pour les VM et vérifie le réglage des deux environnements
avant d'injecter la charge. L'image du déploiement normal garde son propre nom.
La reconstruction sera nécessaire au prochain lancement ; elle n'est pas une
campagne de charge.

## Pauses entre les paliers de l'étape 17

Le nouveau [protocole](protocole-performance.json) conserve les paliers et
les durées de mesure : montée de 30 s, stabilisation de 15 s, plateau de 120 s
et marge finale de 5 s. Il remplace les repos fixes de 900 s par cette règle :

- attendre au moins 30 s ;
- observer 30 s continues avec CPU inférieur ou égal à 5 % d'un cœur et lectures
  et écritures disque inférieures ou égales à 1 Mio/s, pour chacun des trois services ;
- vérifier l'absence de connexion active sur la base de mesure et une réponse
  HTTP 200 de `/health/ready/` ;
- arrêter la campagne avec une erreur si ces conditions ne sont pas réunies
  en 180 s. Les relevés absents ou périmés ne comptent pas comme du repos.

La mémoire des caches n'a pas à revenir à zéro. Les seuils sont des choix du
protocole à valider lors de l'étalonnage, pas des exigences du sujet.
Ils restent identiques pour VM et Docker. Le journal et les relevés `repos/`
conservent les durées réelles et la preuve du retour au repos.

Pour seize paliers, la durée programmée de mesure est de 45 min 20 s. Si chaque
repos dure 30 s, le total devient environ 51 min 20 s, hors construction des
images, démarrages, restaurations et collecte des relevés. La durée réelle
dépend du retour au repos ; ce n'est pas une garantie de durée.

## Reprendre les vérifications

Réexécuter les contrôles de l'étape 16 avec cette configuration avant une
nouvelle campagne. Ne pas comparer directement ses résultats avec les anciennes
campagnes dont la protection était active.

Pour l'étape 17, choisir un **nouveau dossier de résultats et un nouveau dossier
privé de travail** : ne pas reprendre un ancien export de sources ni une campagne
préparée avec le protocole précédent. Utiliser ensuite les actions habituelles
`17 preparer`, `17 lancer`, `17 statut` et `17 arreter` décrites dans
[EXECUTION.md](../EXECUTION.md). `17 preparer` ne lance pas la charge.

Après la campagne, vérifier sa nouvelle sortie avec
`python3 mesure/scripts/verifier17.py --output "$MESURE_OUTPUT"`.
L'action `17 verifier` sans paramètre continue de vérifier les preuves historiques.

Le fichier [protocole.json](protocole.json) reste associé aux preuves historiques.
Le vérificateur sélectionne le protocole d'après l'empreinte du manifeste ;
il continue de contrôler les pauses de quinze minutes des anciennes campagnes.
Les résultats existants ne sont pas modifiés.
