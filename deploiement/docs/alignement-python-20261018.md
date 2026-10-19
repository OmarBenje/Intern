# Alignement de Python applicatif, 18 octobre 2026

Le Python de l’application VM a été aligné sur celui de Docker : **3.12.15**.
L’intervention a eu lieu en maintenance exclusive, hors campagne de mesure.
Le Python système Ubuntu n’a pas été remplacé et les résultats des anciennes
campagnes n’ont pas été modifiés ni requalifiés.

## Versions vérifiées après intervention

| Composant | VM métier | Docker existant et image reconstruite |
|---|---|---|
| Python | 3.12.15 | 3.12.15 |
| Django | 6.1.1 | 6.1.1 |
| DRF | 3.18.1 | 3.18.1 |
| Gunicorn | 23.0.0 | 23.0.0 |

La version exacte est définie dans
[metier/.python-version](../../metier/.python-version). Le build Docker la
compare à l’interpréteur de l’image. L’installation VM utilise ce même pin
et les dépendances figées dans `uv.lock`. Les futures campagnes comparent
désormais également le correctif Python ; une différence est refusée.

## Intervention réelle

1. Vérification qu’aucune mesure ni maintenance n’était active, puis prise
   du verrou partagé. Les VM étaient arrêtées au départ.
2. Installation locale d’une distribution officielle Astral Python 3.12.15,
   puis transfert vers `/opt/intern/python/` dans la VM métier, sans ajouter
   de NAT aux VM privées.
3. Préparation hors ligne de `/opt/intern/metier/.venv-python-3.12.15` à partir
   du cache uv et du verrou existants. L’ancien environnement reste actif.
4. Tests applicatifs VM dans une base PostgreSQL créée pour l’intervention,
   avec un rôle et une règle d’accès temporaires. Les données de référence
   ne servent pas de base de tests.
5. Bascule du lien `.venv` après réussite des tests, démarrage du service et
   vérification HTTP réelle de `/health/ready/` sur la VM métier.
6. Suppression du rôle et de la base de test, restauration du fichier d’accès
   PostgreSQL et des politiques de mises à jour, arrêt des VM démarrées par
   l’intervention et redémarrage du proxy Docker de référence.

L’ancien environnement reste conservé sur la VM dans
`/opt/intern/metier/.venv-before-python-1792344867598144629`.
Le helper d’activation revient à cet environnement si le nouveau service
ne démarre pas ou ne répond pas au contrôle de santé. Les tests couvrent
également un échec de renommage et un environnement non validé.

## Vérifications réalisées

| Vérification | Résultat |
|---|---|
| Suite Django complète dans Docker existant, base dédiée | **573 tests réussis**, 116,834 s |
| Même suite dans le nouvel environnement VM, base dédiée | **573 tests réussis**, 216,568 s |
| Tests du pilote de mesure et de la comparaison des versions | **101 tests réussis** |
| Tests de maintenance, préparation et retour arrière Python | **33 tests réussis** |
| Tests des outils de lancement, dont le choix du Python local | **57 tests réussis** |
| Nouveau build du Dockerfile, tag de validation distinct | Réussi ; version et bibliothèques identiques à la VM |
| Origine Docker après remise en état | HTTP 200, `{"status": "ok"}` |
| État final des trois conteneurs de référence | `healthy` |
| État final des VM | Arrêtées, comme avant intervention |
| Erreurs de nettoyage de l’intervention | Aucune |

Ces durées sont celles des suites de tests, pas des mesures de capacité
comparables entre VM et Docker. Les appels distants des tests applicatifs
sont simulés ; ce n’est pas une validation du parcours public Cloudflare.

## Difficultés rencontrées et prévention

- Le catalogue intégré à uv 0.11.29 ne proposait pas Python 3.12.15.
  Les métadonnées officielles d’uv 0.13.1 ont permis l’installation sans
  modifier le Python système. Leur chemin est désormais
  `crates/uv-python-managed/download-metadata.json`, contrairement à l’ancien
  chemin qui répondait 404. Le chemin et la version du catalogue sont épinglés
  dans l’installation VM et dans la configuration du lanceur local.
- Le premier contrôle automatique d’autorisation a expiré avant le lancement
  de la maintenance. La nouvelle tentative a été autorisée ; aucune opération
  VM n’avait démarré lors de l’expiration.
- Chaque préparation invalide un ancien marqueur de tests ; une bascule exige
  un nouveau résultat réussi pour la version épinglée. La préparation refuse
  de modifier un environnement déjà actif.

## Preuves locales

Le dossier privé `.execution/python-alignment/` contient `report.json`,
`docker-tests.log`, `vm-tests.log`, `docker-build.log`, les journaux des trois
suites de régression et les vérifications de version après bascule.
Le rapport confirme `status: complete`, `cleanup_errors: []` et la réponse
de santé de l’origine. L’image de validation porte le tag
`intern-metier:python-alignment-verification` ; les images des services de
référence n’ont pas été remplacées pour ce test de build.
