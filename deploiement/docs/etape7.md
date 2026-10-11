# Étape 7 — Vérification des machines

Préparation réalisée les 11–12 octobre 2026, vérification finale le 12 octobre
(heure de Paris), sur VirtualBox `7.2.8_RPMFUSIONr173730`.

## Résultat

Le modèle `vm-modele` a été créé depuis l'OVA officielle Ubuntu Server 24.04 LTS
datée du 26 septembre 2026, initialisé avec cloud-init puis mis à jour.
La somme SHA-256 correspond au manifeste officiel téléchargé par HTTPS.
Le système annonce Ubuntu 24.04.5 LTS ; après redémarrage, le noyau est
`6.8.0-146-generic`, la cible est `multi-user.target` et aucun service n'est
en échec. `apt-get -s upgrade` indique zéro mise à jour immédiatement applicable ;
`libopeniscsiusr` et `open-iscsi` restent différés par le déploiement progressif Ubuntu.

| Machine | vCPU | RAM | Disque logique | Snapshot | État final |
| --- | ---: | ---: | ---: | --- | --- |
| vm-proxy | 1 | 1 Gio | 20 Gio | base propre | Éteinte |
| vm-metier | 2 | 2 Gio | 20 Gio | base propre | Éteinte |
| vm-donnees | 2 | 2 Gio | 20 Gio | base propre | Éteinte |

Le modèle est conservé éteint. Il ne constitue pas une quatrième couche applicative.

## Contrôles réellement exécutés

- Import et démarrage effectifs du modèle dans VirtualBox, puis connexion SSH.
- Clonage intégral et vérification de trois disques de base indépendants : les
  clones ne dépendent pas du disque du modèle. Chaque snapshot utilise ensuite
  un disque différentiel rattaché au disque de son propre clone.
- Fixation du nom dans `/etc/hostname` et `/etc/hosts`, régénération de
  `/etc/machine-id`, du lien D-Bus et des clés hôtes SSH.
- Redémarrage de chaque clone et lecture par SSH de son nom, de son identifiant,
  de `/etc/hostname`, de l'identifiant D-Bus et de la cible `multi-user.target`.
- Comparaison des trois identifiants entre eux et avec celui du modèle : distincts.
- Comparaison des trois MAC : distinctes.
- Lecture des ressources et des snapshots via `VBoxManage showvminfo`.
- Vérification de l'arrêt et de l'absence de redirection de ports sur les clones.
- Vérification de syntaxe Python, shell et des dix blocs Bash de la procédure ;
  lecture des deux fichiers de l'ISO NoCloud et contrôle des chemins SSH avec espaces.

## Preuves et reproduction

- [Capture réelle de la liste VirtualBox](virtualbox-machines.png).
- [Sorties CLI et champs pertinents](preuves-etape7.txt).
- [Identités et snapshots relevés](identites-etape7.json).
- [Procédure et commandes](../scripts/PROCEDURE.md).
- [Initialisation du modèle](../scripts/seed_modele.py).
- [Finalisation du modèle](../scripts/finaliser_modele.sh).
- [Clonage et vérification après redémarrage](../scripts/cloner_etape7.py).

Les preuves CLI sont issues des VM réelles. Les chemins locaux sont omis.
La capture graphique de la liste VirtualBox a été réalisée le 12 octobre 2026
et intégrée à l’index des livrables. Aucune approbation pédagogique n'est déduite
de ces vérifications techniques.

## État avant l'étape 8

Les trois VM gardent leur NAT de préparation, sans redirection de ports.
Le réseau interne, l'adressage statique et l'isolation cible restent à construire
et à vérifier. Aucune couche applicative ni donnée de projet n'a été installée.
Les snapshots ont été pris après la préparation des identités et avant cette
configuration réseau.

Les images, disques et la clé privée d'administration sont stockés hors du dépôt.
Le compte `adminvm` s'utilise avec la clé SSH dédiée ; la procédure explique
comment réactiver temporairement un accès local.
