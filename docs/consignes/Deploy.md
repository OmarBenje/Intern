# DEPLOY — Déploiement sur trois machines virtuelles

## Mode de lecture pour une IA

**Périmètre :** Étapes 7 à 10, après les étapes 1 à 6 de [Dev.md](Dev.md).

**Prérequis résumés :** Application locale achevée, couches séparables, configuration externalisée et procédure d’installation vérifiée. Les prérequis détaillés du corps du document restent applicables.

Les sections de contexte et de contraintes s’appliquent à toutes les étapes de ce document. Suivre les étapes dans leur ordre et lire, pour chacune, l’objectif, le travail demandé, les vérifications et les livrables, ainsi que le récapitulatif final. Les critères d’évaluation et les jalons de validation restent applicables.

Conserver la portée des formulations d’origine : une obligation reste une obligation ; un conseil, une suggestion, un exemple ou une perspective ne devient pas une exigence supplémentaire. Les commandes, schémas et tableaux illustratifs ne constituent pas des preuves d’exécution. Les valeurs « à relever » et les tableaux de recette sont à renseigner à partir du travail effectué.

Les remarques éditoriales ci-dessous signalent des ambiguïtés de la source ; elles ne les tranchent pas et n’ajoutent aucun livrable.

**Parcours complet :** [DEV, étapes 1–6](Dev.md) → [VM, étapes 7–10](Deploy.md) → [Docker, étapes 11–14](Docker.md) → [Mesures, étapes 15–18](Metrics.md).

## Sommaire

- [1. Contexte et objectif](#section-1)
- [2. La topologie cible](#section-2)
- [3. Déroulement du travail](#section-3)
  - [Étape 7 — Préparer les trois machines](#etape-7)
  - [Étape 8 — Réseau et adressage](#etape-8)
  - [Étape 9 — Déployer les trois couches](#etape-9)
  - [Étape 10 — Vérifier et mesurer](#etape-10)
- [4. Ce qui vient après](#section-4)
- [5. Livrables et organisation](#section-5)
- [6. Conduite des séances](#section-6)
- [7. Erreurs les plus fréquentes](#section-7)

---

## Consultation de notes

**Déploiement sur trois machines virtuelles**

**Seconde partie — déploiement**

L'application réalisée en première partie est maintenant répartie sur trois machines virtuelles VirtualBox, une par couche, reliées par un réseau que vous construisez. Le code ne change pas : seules changent les adresses et la configuration.

---

<a id="section-1"></a>

## 1. Contexte et objectif

Jusqu'ici, les trois couches s'exécutent sur votre poste, dans trois processus qui se parlent par `localhost`. Cette seconde partie les sépare pour de bon : une machine virtuelle par couche, reliées par un réseau que vous construisez, avec les contraintes d'accès d'une architecture réelle.

C'est l'objet de la partie 1 du cours. Le code ne change pas — et si vous devez le modifier, c'est que l'étape 4 n'a pas été faite correctement. Ce qui change, ce sont trois adresses, quelques fichiers de configuration et une topologie réseau.

### 1.1 Ce que le déploiement révèle

Répartir une application déjà fonctionnelle paraît anodin et ne l'est jamais. Trois hypothèses tacites du développement local tombent d'un coup :

| Hypothèse implicite sur un poste unique | Ce qui en advient une fois réparti |
| --- | --- |
| **Tout est joignable sur localhost** | Chaque service a une adresse distincte, et certaines liaisons sont volontairement impossibles.  |
| **Un service qui écoute, écoute pour tout le monde** | Un service lié à `127.0.0.1` devient injoignable depuis une autre machine.  |
| **Le réseau est instantané et infaillible** | Latence, délais d'attente et pannes partielles apparaissent.  |

> *Note* : La troisième ne se manifestera vraiment qu'en partie 3 du cours, sous charge. Les deux premières vous occuperont dès la première séance.

### 1.2 Prérequis

Cette partie suppose achevées les six étapes de la première. Trois points en particulier seront mis à l'épreuve immédiatement :

* **Trois processus réellement séparables** : Chaque couche doit pouvoir démarrer seule, sur une machine où les deux autres sont absentes.

* **Configuration externalisée** : Adresses, identifiants et ports viennent de variables d'environnement, jamais du code.

* **Procédure d'installation vérifiée** : Vous allez l'exécuter trois fois, sur trois machines nues. Toute étape implicite se paiera trois fois.

### 1.3 Contraintes techniques

| Élément | Imposé | Laissé libre |
| --- | --- | --- |
| **Hyperviseur** | VirtualBox  | Version, tant qu'elle est récente  |
| **Système invité** | Distribution Linux serveur, sans interface graphique  | Distribution au choix du binôme  |
| **Nombre de machines** | Trois, une par couche  | — |
| **Réseau applicatif** | Réseau interne VirtualBox, adressage statique  | Plan d'adressage  |
| **Accès extérieur** | Sur la machine du proxy uniquement  | NAT avec redirection, ou NAT Network |

> **ERREUR FRÉQUENTE**
> Aucune extension de l'application n'est demandée ici : ni service supplémentaire, ni conteneur. Le but est de déplacer ce qui existe, sans rien y ajouter. Les briques complémentaires seront introduites en partie 2 du cours, avec Docker.

---

<a id="section-2"></a>

## 2. La topologie cible

### Schéma de la topologie réseau cible

```text
+---------------------------------------------------------------------------------------------------------+

| POSTE DE TRAVAIL — hôte VirtualBox                                                                      |
|                                                                                                         |
|  +-------------------+        8080 -> 80        +-----------------------------------+                   |
|  | Navigateur        |------------------------->| VM 1 — proxy                      |                   |
|  | http://localhost:8080                        | Nginx                             |                   |
|  +-------------------+                          | eth0 : NAT | eth1 : 10.10.10.10    |                   |
|                                                 +-----------------------------------+                   |
|                                                                   | (seule VM joignable depuis l'hôte)  |
|                                                                   | 10.10.10.0/24                       |
|                                                 =====================================                   |
|                                                 Réseau Interne « intnet-app »                           |
|                                                 =====================================                   |
|                                                                   |                                     |
|                                                 +-----------------------------------+                   |
|                                                 | VM 2 — métier                     |                   |
|                                                 | Python (Gunicorn)                 |                   |
|                                                 | eth0 : 10.10.10.20                |                   |
|                                                 +-----------------------------------+                   |
|                                                                   |                                     |
|                                                 +-----------------------------------+                   |
|                                                 | VM 3 — données                    |                   |
|                                                 | PostgreSQL                        | (isolée de l'hôte |
|                                                 | eth0 : 10.10.10.30                |  et d'Internet)   |
|                                                 +-----------------------------------+                   |
|                                                                                                         |
|  . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  |
|  Redirection de ports NAT sur la VM proxy.                                                              |
|  Le trafic entre par un seul point, et la base n'est accessible que depuis la VM métier.                |

+---------------------------------------------------------------------------------------------------------+

```

*Figure 7 — Les trois machines virtuelles, leur adressage et les deux réseaux.*

Trois machines, deux réseaux. Un réseau interne porte tout le trafic applicatif entre les trois couches ; il est fermé, ni l'hôte ni Internet n'y accèdent. La machine portant le proxy dispose en plus d'un adaptateur en NAT, avec une redirection de ports qui permet à votre navigateur de l'atteindre.

Ce découpage reproduit à l'échelle du poste de travail une architecture de production courante : une façade exposée, un segment applicatif privé, et une base de données que rien n'atteint depuis l'extérieur.

### 2.1 Pourquoi le réseau interne

VirtualBox propose cinq modes réseau, dont trois auraient pu convenir techniquement. Le réseau interne est retenu pour une raison précise : il est le seul à interdire aussi l'accès depuis l'hôte.

| Mode | VM ↔ VM | Hôte → VM | Pourquoi il est écarté, ou retenu |
| --- | --- | --- | --- |
| **NAT** | non | redirection | Les machines ne se voient pas : inutile ici.  |
| **Accès par pont** | oui | oui | Les trois machines seraient exposées au réseau local.  |
| **Réseau privé hôte** | oui | oui | L'hôte joint la base : l'isolation n'est pas démontrable.  |
| **Réseau interne** | **oui** | **non** | **Retenu — segment strictement privé entre machines**.  |

> **À RETENIR**
> C'est ce choix qui rend possible la vérification négative de l'étape 10 : si votre poste arrive à joindre la base, la topologie est fausse. Avec un réseau privé hôte, ce test n'aurait aucun sens.

---

### 2.2 Plan d'adressage

| Machine | Rôle | vCPU / RAM | Adaptateur 1 | Adaptateur 2 |
| --- | --- | --- | --- | --- |
| **vm-proxy** | Nginx, sert le client | 1 / 1 Go  | NAT (8080 → 80)  | interne 10.10.10.10  |
| **vm-metier** | API Python | 2 / 2 Go  | interne 10.10.10.20  | — |
| **vm-donnees** | PostgreSQL | 2 / 2 Go  | interne 10.10.10.30  | — |

Le sous-réseau `10.10.10.0/24` et le nom de réseau `intnet-app` sont des suggestions : tout autre plan convient, pourvu qu'il soit écrit avant d'être mis en œuvre et qu'il figure au compte rendu.

### 2.3 La règle d'or du déploiement

Un seul point d'entrée. Le trafic venu de l'extérieur n'atteint que la machine du proxy ; tout le reste se passe à l'intérieur du réseau interne. Cette règle a trois conséquences immédiates, qui seront vérifiées une à une à l'étape 10 :

* Le navigateur n'adresse jamais la couche métier directement : il passe par le proxy.

* La couche métier est la seule à ouvrir une connexion à la base.

* Aucun service, hormis le proxy, n'est joignable depuis votre poste.

> La règle d'or du chapitre 2 de la première partie — *le client ne parle jamais à la base* — trouve ici sa traduction matérielle : ce n'est plus une convention de programmation, c'est une impossibilité de réseau.

---

<a id="section-3"></a>

## 3. Déroulement du travail

```text
+-----------------+      +---------------------+      +------------------------+      +-----------------------+

| Trois machines  |----->| Réseau et adressage |----->| Déploiement des couches|----->| Vérification et mesure|

+-----------------+      +---------------------+      +------------------------+      +-----------------------+
     Étape 7                    Étape 8                        Étape 9                         Étape 10

```

*Les étapes 1 à 6 sont celles de la première partie : elles doivent être achevées.*

*Figure 8 — Les quatre étapes du déploiement.*

Quatre étapes, dans cet ordre : chacune se vérifie avant que la suivante ne commence. Prenez un snapshot au début de chaque étape ; c'est ce qui vous permettra d'essayer plutôt que d'éviter.

---

<a id="etape-7"></a>

### Étape 7 — Préparer les trois machines

#### Objectif
> Obtenir trois machines virtuelles distinctes, à partir d'une seule installation.

#### Travail à faire

* Partir de la machine du TP 1, à jour et sans données de projet, et en faire un modèle : c'est le socle commun.

* La cloner trois fois en clone intégral, en cochant la réinitialisation des adresses MAC de toutes les cartes réseau.

* Sur chaque clone, fixer le nom de machine dans `/etc/hostname` et `/etc/hosts`, puis régénérer l'identifiant de machine.

* Ajuster les ressources de chaque machine conformément au plan d'adressage : inutile de donner deux processeurs au proxy.

* Prendre sur chacune un snapshot nommé « base propre », avant toute configuration.

#### Deux détails qui coûtent une séance si on les ignore

Un clone conserve l'adresse MAC de son modèle. Deux machines ayant la même adresse sur le même réseau produisent un comportement erratique, difficile à diagnostiquer parce qu'il ressemble à une panne intermittente. L'option de réinitialisation, au moment du clonage, évite tout cela.

De même, l'identifiant de machine est copié. Sur les distributions récentes, c'est lui qui sert d'identifiant au client DHCP : trois machines clonées demandent alors la même adresse. La régénération tient en deux commandes :

```bash
sudo truncate -s 0 /etc/machine-id
sudo systemd-machine-id-setup && sudo reboot
```

> **CONSEIL**
> Le snapshot « base propre » est votre filet. Chaque étape suivante modifie la configuration réseau ou système ; pouvoir revenir en trente secondes à une machine saine change complètement le rapport au risque, et vous fera essayer des choses plutôt que les éviter.

#### Livrables attendus
> Trois machines nommées, dimensionnées, chacune avec son snapshot initial. Une capture de la liste des machines dans VirtualBox suffit à l'attester.

---

<a id="etape-8"></a>

### Étape 8 — Réseau et adressage

#### Objectif
> Construire le réseau interne, fixer les adresses, et vérifier la connectivité avant tout déploiement.

#### Travail à faire
* Sur les trois machines, placer l'adaptateur applicatif en réseau interne, avec le même nom de réseau — par exemple `intnet-app`.
* Sur la machine du proxy uniquement, activer un second adaptateur en NAT et y déclarer une redirection du port 8080 de l'hôte vers le port 80 de la machine.
* Attribuer une adresse statique à chaque machine sur le réseau interne, selon le plan retenu.
* Vérifier, avant d'aller plus loin, que chaque machine en joint les deux autres.

#### Adressage statique
Un réseau interne ne comporte aucun serveur DHCP : sans configuration, les machines n'obtiennent aucune adresse. Sur une distribution récente utilisant Netplan, le fichier tient en quelques lignes :

```yaml
network:
  version: 2
  ethernets:
    enp0s3:
      dhcp4: false
      addresses: [10.10.10.20/24]
```

*Le nom de l'interface varie d'une machine à l'autre : relevez-le avec `ip a` avant d'écrire le fichier, ne le devinez pas.*

#### Le problème de l'installation des paquets
Les machines métier et données n'ont aucun accès à Internet, ce qui est précisément l'objectif — mais vous devez y installer PostgreSQL et des bibliothèques Python. Deux façons de procéder, et le choix mérite d'être assumé dans le compte rendu :

* **Installer avant d'isoler** : Poser tous les paquets pendant que la machine a encore un adaptateur NAT, puis le désactiver. Simple, et c'est ce que fait une image de base en production.
* **Isoler puis ouvrir ponctuellement** : Garder un adaptateur NAT désactivé, l'activer le temps d'une installation, le désactiver ensuite. Plus proche d'une pratique d'exploitation réelle.

> **ERREUR FRÉQUENTE**
> Ce qu'il ne faut pas faire : laisser l'adaptateur NAT actif sur les trois machines « pour la commodité ». La topologie n'est alors plus celle qui est demandée, la vérification négative de l'étape 10 réussira à tort, et le déploiement en conteneurs de la partie 2 du cours n'aura plus rien à quoi se comparer.

#### Vérification (Étape 8)

```bash
ip a                      # l'adresse est-elle bien posée ?
ping -c2 10.10.10.30      # depuis vm-metier vers vm-donnees
ping -c2 10.10.10.20      # depuis vm-proxy vers vm-metier
```

#### Livrables attendus
> Le plan d'adressage, les trois fichiers de configuration réseau, et la sortie des commandes de vérification.

---

<a id="etape-9"></a>

### Étape 9 — Déployer les trois couches

#### Objectif
> Installer chaque couche sur sa machine, en ne changeant que la configuration.

L'ordre est imposé par les dépendances : la base d'abord, le métier ensuite, le proxy en dernier. Prenez un snapshot avant chaque couche.

#### 1. `vm-donnees` — la base
* Installer le SGBD, créer la base, l'utilisateur applicatif et ses droits, puis exécuter vos deux scripts SQL.
* Faire écouter le serveur sur l'adresse du réseau interne et non sur la seule boucle locale.
* N'autoriser les connexions que depuis l'adresse de la machine métier, et en exigeant un mot de passe.

*Sous PostgreSQL, cela revient à deux fichiers. Dans `postgresql.conf` :*
```text
listen_addresses = '10.10.10.30'
```
*et dans `pg_hba.conf`, une ligne qui n'ouvre l'accès qu'à la machine métier :*
```text
host  notes  app  10.10.10.20/32  scram-sha-256
```

#### 2. `vm-metier` — l'application
* Installer Python et les dépendances, déployer le code, créer l'environnement virtuel.
* Renseigner les variables d'environnement — adresse et identifiants de la base — hors du code.
* Lancer le serveur applicatif en écoutant sur l'adresse du réseau interne, et non sur la boucle locale.
* Déclarer le tout comme un service géré par le système, de sorte qu'il redémarre avec la machine.

```bash
gunicorn --bind 10.10.10.20:8000 app:application
```

> Le passage par un service système n'est pas un raffinement : une application lancée à la main dans un terminal disparaît à la fermeture de la session, et vous perdrez du temps à comprendre pourquoi tout s'arrête après un redémarrage.

#### 3. `vm-proxy` — la façade
* Installer le serveur web, y déposer les fichiers du client.
* Configurer le renvoi des appels de l'interface applicative vers la machine métier.
* Vérifier que le client, côté navigateur, s'adresse bien au proxy et jamais directement au métier.

```nginx
location /api/ { proxy_pass http://10.10.10.20:8000/api/; }
```

---

> **À RETENIR**
> C'est ici que l'externalisation de la configuration, demandée à l'étape 4, se rentabilise. Si vous n'avez aucune ligne de code à modifier pour ce déploiement, l'étape 4 a été bien faite. Sinon, notez dans votre compte rendu ce qu'il a fallu changer : c'est un résultat d'expérience, pas un aveu.

#### Livrables attendus
> Les fichiers de configuration des trois machines — réseau, base, service applicatif, serveur web — rassemblés dans le dépôt, et la procédure de déploiement mise à jour.

---

<a id="etape-10"></a>

### Étape 10 — Vérifier et mesurer

#### Objectif
> Établir que la topologie est celle qui était demandée, et relever les mesures de référence.

#### La matrice de joignabilité
La vérification positive ne suffit pas : une application qui fonctionne peut être mal isolée. Il faut donc vérifier aussi ce qui doit échouer. Le tableau ci-dessous est à reproduire et à remplir :

| Depuis | vers proxy :80 | vers métier :8000 | vers base :5432 |
| :--- | :---: | :---: | :---: |
| **L'hôte** | oui, via 8080 | doit échouer | doit échouer |
| **vm-proxy** | — | oui | doit échouer |
| **vm-metier** | oui | — | oui |
| **vm-donnees** | oui | oui | — |

Les trois cases « doit échouer » sont les plus instructives. Si l'une réussit, la cause est presque toujours l'une des trois suivantes : un adaptateur NAT resté actif, un service qui écoute sur toutes les interfaces alors qu'il ne le devrait pas, ou une règle de filtrage absente.

#### Les commandes utiles

```bash
ss -tlnp                            # sur quelles adresses ce service écoute-t-il ?
curl -s -o /dev/null -w '%{http_code}' http://10.10.10.20:8000/api/...
psql -h 10.10.10.30 -U app notes -c 'select 1'
nc -zv -w2 10.10.10.30 5432          # depuis l'hôte : doit échouer
```

> **ERREUR FRÉQUENTE**
> Un service qui écoute sur `0.0.0.0` écoute sur toutes les interfaces de la machine, y compris celles que la topologie destinait à rester privées. La configuration réseau de l'hyperviseur ne compense pas une écoute trop large côté service : c'est `ss -tlnp`, et non le succès de l'application, qui vous dira la vérité.

#### Les mesures de référence
Ces relevés seront rejoués à l'identique sur les conteneurs, en partie 2 du cours. Leur valeur tient entièrement à la rigueur du protocole : trois exécutions, médiane retenue, configuration exacte consignée à côté de chaque chiffre.

| Grandeur | Comment la relever | Pourquoi elle compte |
| --- | --- | --- |
| **Temps de démarrage** | Des trois machines éteintes au service qui répond | C'est l'écart le plus spectaculaire avec les conteneurs |
| **Mémoire consommée** | Côté hôte, les trois machines en marche au repos | Mesure le coût des trois systèmes d'exploitation |
| **Empreinte disque** | Taille cumulée des fichiers de disque | Même raison, sur l'autre ressource |
| **Latence applicative** | Dix appels à une route de consultation | Point de comparaison sous charge en partie 3 |

> **CONSEIL**
> Relevez aussi le temps qu'il vous a fallu pour passer de zéro aux trois machines opérationnelles. Ce n'est pas une mesure technique, mais c'est celle qui frappera le plus quand vous ferez la même chose en conteneurs, en quelques minutes.

#### Livrables attendus
> La matrice de joignabilité remplie, les sorties de commandes qui l'attestent, le tableau des mesures de référence, et les trois machines exportées au format OVA.

---

<a id="section-4"></a>

## 4. Ce qui vient après

Le déploiement réparti clôt la partie 1 du cours. L'application que vous venez de séparer sera reprise deux fois, et il est utile de savoir dès maintenant ce que ces reprises exigeront.

| Suite | Ce qui sera fait | Ce que cela exige dès maintenant |
| --- | --- | --- |
| **Partie 2 du cours** | Le même découpage, repris en trois conteneurs Docker | Une procédure de déploiement exacte, suivie trois fois et vérifiée |
| **Partie 2 (extension)** | Intégration de briques open source non écrites par vous | Des interfaces stables entre vos trois couches |
| **Partie 3 du cours** | Injection de charge avec JMeter, comparaison des deux déploiements | Les mesures de référence de l'étape 10, et un jeu de données suffisant |

> **À RETENIR**
> La comparaison de la partie 3 n'a de sens que si les deux déploiements hébergent la même application, avec le même jeu de données et le même protocole de mesure. C'est pourquoi les relevés de l'étape 10 doivent être consignés avec leur configuration, et non seulement leurs chiffres.

---

<a id="section-5"></a>

## 5. Livrables et organisation

### 5.1 Récapitulatif des livrables

| Étape | Livrable | Forme |
| --- | --- | --- |
| **7** | Trois machines préparées | Capture VirtualBox + snapshots nommés |
| **8** | Réseau interne et adressage | Plan d'adressage + trois fichiers réseau |
| **9** | Déploiement réparti | Fichiers de configuration des trois machines |
| **10** | Vérification et mesures | Matrice de joignabilité, mesures, trois OVA |

### 5.2 Organisation du dépôt

Le dépôt de la première partie est complété d'un dossier dédié au déploiement. Rien n'est déplacé : le code reste où il est.

```text
deploiement/
├── reseau/         netplan des trois machines
├── donnees/        postgresql.conf, pg_hba.conf
├── metier/         unité systemd, fichier d'environnement
├── proxy/          configuration Nginx
├── PROCEDURE.md    déploiement pas à pas, dans l'ordre
└── docs/
    └── mesures.md  relevés de l'étape 10 et leur configuration

```

Le fichier de procédure est le livrable le plus utile de cette partie : c'est lui que vous relirez en partie 2 du cours pour écrire les fichiers Docker, et lui qui révélera les étapes que vous faisiez « de mémoire ».

### 5.3 Critères d'évaluation

| Critère | Ce qui est regardé | Poids |
| --- | --- | --- |
| **Préparation des machines** | Clones propres, nommage, dimensionnement, snapshots | **15 %** |
| **Topologie et adressage** | Conformité au plan, réseau interne correctement fermé | **25 %** |
| **Déploiement des trois couches** | Écoute sur les bonnes adresses, services système, aucun code modifié | **30 %** |
| **Vérification de l'isolation** | Matrice remplie, cas négatifs réellement testés | **20 %** |
| **Mesures et compte rendu** | Protocole respecté, configuration consignée | **10 %** |

*Les deux parties du document sont évaluées séparément ; leur pondération respective est annoncée en séance. Notez le poids du critère d'isolation : un déploiement qui fonctionne mais dont l'hôte joint la base ne remplit pas l'objectif de cette partie.*

---

<a id="section-6"></a>

## 6. Conduite des séances

Le déploiement se mène en deux séances de quatre heures. La répartition ci-dessous est indicative, mais l'ordre ne l'est pas.

| Séance | Ce qui doit être atteint | Point de contrôle |
| --- | --- | --- |
| **Première** | Étapes 7 et 8 : trois machines, réseau interne, adressage | Chaque machine en joint les deux autres |
| **Seconde** | Étapes 9 et 10 : déploiement, vérification, mesures | La matrice de joignabilité est remplie |

Ne commencez pas l'étape 9 si l'étape 8 n'est pas vérifiée. Déployer trois services sur un réseau qui ne fonctionne pas produit un enchevêtrement de symptômes où l'on ne sait plus si la panne vient du réseau, de la configuration ou de l'application.

> **CONSEIL**
> Consignez au fil de l'eau, pas à la fin. Les commandes exactes, les messages d'erreur rencontrés et ce qui les a résolus constituent la matière du fichier de procédure. Reconstitués de mémoire trois jours plus tard, ils seront faux.

---

<a id="section-7"></a>

## 7. Erreurs les plus fréquentes

Ces sept situations concentrent l'essentiel du temps perdu sur cette partie. Le symptôme est plus utile que la cause : c'est par lui que vous entrerez dans le diagnostic.

| Symptôme observé | Cause la plus probable |
| --- | --- |
| **Connectivité erratique entre deux machines** | Clonage sans réinitialisation des adresses MAC |
| **Deux machines obtiennent la même adresse** | Identifiant de machine identique (hérité du clone) |
| **Aucune adresse sur le réseau interne** | Attente d'un DHCP qui n'existe pas sur ce mode |
| **Le métier ne joint pas la base, sans message clair** | `listen_addresses` resté sur la boucle locale |
| **Connexion refusée avec un message d'authentification** | Ligne manquante dans `pg_hba.conf` |
| **Le proxy renvoie une erreur 502** | Service métier arrêté, ou lié à `127.0.0.1` |
| **Tout marche, mais l'hôte joint aussi la base** | Adaptateur NAT resté actif sur `vm-donnees` |

> **À RETENIR**
> Diagnostiquez de bas en haut : l'adresse est-elle posée, la machine répond-elle au ping, le port est-il ouvert, le service écoute-t-il sur la bonne adresse, l'application répond-elle. Remonter cette chaîne dans l'ordre prend cinq minutes ; la parcourir au hasard peut prendre une séance.

---

## Remarques éditoriales sur la source

- **Repérage des parties :** la source parle à la fois de « seconde partie » du document et de « partie 1 du cours ». Le repère de travail de ce fichier est la suite des étapes 7 à 10.
