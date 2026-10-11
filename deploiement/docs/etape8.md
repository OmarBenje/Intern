# Étape 8 — Vérification du réseau

Configuration et vérification exécutées le **12 octobre 2026** (heure de Paris)
sur les trois VM réelles, avec VirtualBox `7.2.8_RPMFUSIONr173730`.

## Résultat

Les trois machines utilisent le réseau interne **`intnet-app`** sur
`10.10.10.0/24`. Les interfaces ont été identifiées par leurs MAC dans chaque VM.
Les adresses sont présentes après arrêt et redémarrage sur la topologie cible.

| Machine | Interface interne | Adresse statique | Interface NAT | Route IPv4 par défaut |
| --- | --- | --- | --- | --- |
| vm-proxy | enp0s3 | 10.10.10.10/24 | enp0s8 | Oui, via le NAT |
| vm-metier | enp0s3 | 10.10.10.20/24 | Aucune | Aucune |
| vm-donnees | enp0s3 | 10.10.10.30/24 | Aucune | Aucune |

Le NAT du proxy a attribué `10.0.3.15/24` à `enp0s8`, avec la passerelle
`10.0.3.2`. Il s'agit d'une adresse DHCP de préparation, pas de l'adresse interne.
Sa seule redirection finale est **`127.0.0.1:8080 → port 80`**.

## Connectivité vérifiée

Chaque commande `ping -c 2 -W 2` a transmis deux paquets et reçu deux réponses.

| Depuis | Vers | Résultat |
| --- | --- | --- |
| vm-proxy | 10.10.10.20 — métier | 2/2, 0 % de perte |
| vm-proxy | 10.10.10.30 — données | 2/2, 0 % de perte |
| vm-metier | 10.10.10.10 — proxy | 2/2, 0 % de perte |
| vm-metier | 10.10.10.30 — données | 2/2, 0 % de perte |
| vm-donnees | 10.10.10.10 — proxy | 2/2, 0 % de perte |
| vm-donnees | 10.10.10.20 — métier | 2/2, 0 % de perte |

La condition de passage réseau est satisfaite : chaque machine joint les deux autres.

## Travaux et contrôles

- Snapshot **`avant reseau`** pris sur chacune avant les changements ; les
  snapshots `base propre` de l'étape 7 sont conservés.
- Configuration Netplan sauvegardée puis remplacée et validée avec `netplan generate`.
- Redémarrage des trois VM sur le réseau interne avant les tests.
- Lecture des interfaces et routes dans chaque VM ; absence de route IPv4 par
  défaut sur métier et données.
- Comparaison des trois fichiers Netplan installés avec les fichiers livrés : identiques.
- Lecture finale des adaptateurs et redirections dans VirtualBox : réseau interne
  sur les trois VM, NAT uniquement sur le proxy, aucune redirection sur les VM privées.
- Administration des VM privées depuis l'hôte par un relais SSH sur le proxy,
  sans copier la clé privée d'administration dans une VM.
- Retrait des accès SSH temporaires et arrêt propre des trois machines après les tests.

## Livrables

- [Plan, procédure et choix d'installation des paquets](../reseau/README.md).
- [Plan source JSON](../reseau/plan.json).
- Fichiers Netplan : [proxy](../reseau/vm-proxy.yaml),
  [métier](../reseau/vm-metier.yaml), [données](../reseau/vm-donnees.yaml).
- [Interfaces réellement observées](interfaces-etape8.json).
- [Sorties réelles des commandes et topologie finale](preuves-etape8.txt).
- [Script de configuration et de vérification](../scripts/reseau_etape8.py).

## État final et suite

Les trois VM sont éteintes. Leur configuration réseau est persistante ; seule
la redirection HTTP du proxy reste déclarée dans VirtualBox. Pour rouvrir un accès
d'administration temporaire, suivre la procédure réseau.

Le choix pour les futurs paquets est **isoler puis ouvrir ponctuellement** : un
NAT temporaire pourra être ajouté sur métier ou données, puis retiré avant les
vérifications. Aucun serveur applicatif n'est installé à cette étape ; le succès
d'une requête HTTP et l'isolation des ports applicatifs restent à vérifier après
leur déploiement. Ces pings ne constituent pas les mesures de performance de
l'étape 10 et aucune approbation pédagogique n'est déduite des contrôles techniques.
