# DEV — APPLICATION TROIS-TIERS

## Mode de lecture pour une IA

**Périmètre :** Étapes 11 à 14, après les étapes 1 à 10 de [Dev.md](Dev.md) et [Deploy.md](Deploy.md).

**Prérequis résumés :** Application et déploiement VM achevés, procédure de déploiement et mesures de référence disponibles. Les prérequis détaillés du corps du document restent applicables.

Les sections de contexte et de contraintes s’appliquent à toutes les étapes de ce document. Suivre les étapes dans leur ordre et lire, pour chacune, l’objectif, le travail demandé, les vérifications et les livrables, ainsi que le récapitulatif final. Les critères d’évaluation et les jalons de validation restent applicables.

Conserver la portée des formulations d’origine : une obligation reste une obligation ; un conseil, une suggestion, un exemple ou une perspective ne devient pas une exigence supplémentaire. Les commandes, schémas et tableaux illustratifs ne constituent pas des preuves d’exécution. Les valeurs « à relever » et les tableaux de recette sont à renseigner à partir du travail effectué.

Les remarques éditoriales ci-dessous signalent des ambiguïtés de la source ; elles ne les tranchent pas et n’ajoutent aucun livrable.

**Parcours complet :** [DEV, étapes 1–6](Dev.md) → [VM, étapes 7–10](Deploy.md) → [Docker, étapes 11–14](Docker.md) → [Mesures, étapes 15–18](Metrics.md).

## Sommaire

- [1. Contexte et objectif](#section-1)
- [2. La topologie cible](#section-2)
- [3. Déroulement du travail](#section-3)
  - [Étape 11 — La couche données](#etape-11)
  - [Étape 12 — La couche métier](#etape-12)
  - [Étape 13 — Le proxy et la composition](#etape-13)
  - [Étape 14 — Vérifier et comparer](#etape-14)
- [4. Ce qui vient après](#section-4)
- [5. Livrables et organisation](#section-5)
- [6. Conduite des séances](#section-6)
- [7. Erreurs les plus fréquentes](#section-7)

---

## Consultation de notes

**Déploiement sur trois conteneurs Docker**

**Troisième partie — déploiement en conteneurs**

La même application, le même découpage, la même topologie — mais en conteneurs. Cette partie prépare la comparaison chiffrée entre les deux déploiements, qui fait l'objet de la quatrième.

---

<a id="section-1"></a>

## 1. Contexte et objectif

L'application est maintenant répartie sur trois machines virtuelles, et vous disposez de mesures de référence. Cette troisième partie refait le même déploiement avec des conteneurs Docker : même application, même découpage en trois couches, même topologie réseau.

L'intérêt n'est pas d'obtenir un résultat différent — l'application se comportera de la même façon — mais de mesurer ce que coûtent deux techniques d'isolation pour un service rendu identique. C'est l'objet de la partie 2 du cours, et la matière de la comparaison qui viendra en partie 3.

### 1.1 Ce que le conteneur change

#### Schéma : Figure 9 — Les deux piles, pour le même déploiement à trois couches

```text
+-------------------------------------------------------+-------------------------------------------------------+

|               Trois machines virtuelles               |                    Trois conteneurs                   |

+-------------------------------------------------------+-------------------------------------------------------+

| [ Couche OS invité ] [ Couche OS invité ] [ Couche OS invité ] | [ Couche Dépendances ] [ Couche Dépendances ] [ Couche Dépendances ] |
|                       Hyperviseur                     |  <---> (un système d'exploitation en moins)           |
|                Système d'exploitation hôte            |                 Moteur de conteneurs                  |
|                    Matériel physique                  |              Noyau partagé · système hôte             |
|                                                       |                   Matériel physique                   |

+-------------------------------------------------------+-------------------------------------------------------+
```

La différence tient en une ligne : un conteneur n'embarque pas de système d'exploitation. Il utilise le noyau de l'hôte et n'en obtient qu'une vue restreinte, délimitée par des mécanismes du noyau — espaces de nommage pour cloisonner ce que le processus voit, groupes de contrôle pour limiter ce qu'il consomme.

Le tableau ci-dessous reprend les opérations que vous avez menées à la main en seconde partie, et ce qu'elles deviennent ici.

#### Tableau comparatif des opérations

| En machine virtuelle, vous avez... | En conteneur, cela devient... |
|---|---|
| Installé des paquets sur un système | Des instructions `RUN` dans un fichier de construction d'image |
| Fixé une adresse IP statique | Un nom de service, résolu par le moteur lui-même |
| Écrit une unité de service système | La commande de démarrage et la politique de redémarrage |
| Ouvert un port vers une autre machine | Un réseau partagé entre deux services, et rien d'autre |
| Sauvegardé un répertoire de données | Un volume nommé, distinct du conteneur |
| Pris un snapshot avant de modifier | Une reconstruction de l'image depuis son fichier de construction |

---

> **À RETENIR**
> Le renversement principal est là : en machine virtuelle, la configuration vit dans la machine et se modifie sur place. En conteneur, elle vit dans un fichier versionné, et le conteneur se jette. On ne corrige pas un conteneur : on corrige sa description, puis on le remplace.

### 1.2 Prérequis

Cette partie suppose achevées les dix étapes précédentes. Trois éléments en particulier vont être mis à l'épreuve.

* **La procédure de déploiement.** Le fichier rédigé à l'étape 9 est la matière première des images : chaque commande que vous y avez consignée devient une instruction. Toute étape laissée implicite mequera ici.
* **La configuration externalisée.** Les variables d'environnement de l'étape 4 sont réemployées telles quelles, avec de nouvelles valeurs. Aucun code ne doit changer.
* **Les mesures de référence.** Les relevés de l'étape 10 sont le point de comparaison. Sans eux, cette partie produit des chiffres qui ne se rapportent à rien.

### 1.3 Contraintes techniques

| Élément | Imposé | Laissé libre |
|---|---|---|
| **Moteur** | Docker Engine et Docker Compose | Version, tant qu'elle est récente |
| **Images de base** | Officielles, avec une version explicite | Distribution et variante |
| **Nombre de conteneurs** | Trois, un par couche | — |
| **Réseaux** | Deux réseaux distincts, définis par le projet | Leurs noms |
| **Publication de port** | Le proxy seulement | Le port de l'hôte |
| **Orchestration** | Compose ; ni Swarm ni Kubernetes | — |

> **ERREUR FRÉQUENTE**
> N'utilisez jamais une image sans version explicite. Une image reconstruite trois mois plus tard ne contiendra pas le même logiciel, et vos mesures cesseront d'être comparables. C'est le premier réflexe de reproductibilité, et le plus souvent oublié.

---

<a id="section-2"></a>

## 2. La topologie cible

#### Schéma : Figure 10 — Les trois conteneurs, les deux réseaux et le volume de données

```text
POSTE DE TRAVAIL — moteur Docker (port publié 8080 -> 80)
+-----------------------------------------------------------------------------------+

|                                                                                   |
|  [ Navigateur http://localhost:8080 ]                                             |
|               |                                                                   |
|               v                                                                   |
|       [ proxy (nginx:1.27 - sert le client) ]                                     |
|               |                                                                   |
|     ==========|======================== (réseau frontal — proxy <-> metier)       |
|               |                                                                   |
|       [ metier (image construite · gunicorn) ]                                    |
|               |                                                                   |
|     ==========|======================== (réseau interne — metier <-> donnees)     |
|               |                                                                   |
|       [ donnees (postgres:16) ] <------> [ volume pgdata (données persistantes) ] |
|                                                                                   |

+-----------------------------------------------------------------------------------+
( Un seul port publié, celui du proxy.                                              )
( Le proxy et la base n'ont aucun réseau commun : la base est hors de portée,       )
( y compris depuis le proxy.                                                        )
```

La topologie est celle de la seconde partie, traduite dans le vocabulaire de Docker. Trois services, deux réseaux, un seul port publié, et un volume pour les données qui doivent survivre aux conteneurs.

### 2.1 Du réseau interne au réseau du projet

Un réseau Docker défini par le projet joue le rôle du réseau interne de VirtualBox : les conteneurs qui y sont raccordés se voient entre eux, et rien d'autre ne les atteint tant qu'aucun port n'est publié. Deux différences méritent d'être relevées, car elles changent la façon de travailler.

* **Les noms remplacent les adresses.** Le moteur fournit un serveur de noms interne : le service métier joint la base en l'appelant `donnees`, sans connaître son adresse. Le plan d'adressage statique de l'étape 8 disparaît.
* **Le réglage par défaut est inversé.** En machine virtuelle, tout était ouvert et il fallait fermer. Ici, rien n'est joignable depuis l'hôte et il faut publier explicitement ce que l'on veut exposer. L'isolation est acquise par défaut ; c'est l'ouverture qui se déclare.

#### Pourquoi deux réseaux et non un seul
Tous les conteneurs d'un même réseau se joignent mutuellement, sur tous leurs ports. Un réseau unique laisserait donc le proxy atteindre la base, ce que la topologie de la seconde partie interdisait.

La solution propre consiste à déclarer deux réseaux : le proxy et le métier partagent le premier, le métier et la base partagent le second. Le métier appartient aux deux, le proxy et la base n'ont aucun réseau commun — la base leur est mutuellement hors de portée.

---

> **À RETENIR**
> C'est un avantage réel du conteneur sur la machine virtuelle, et il vaut la peine de le mesurer en temps de travail : ajouter un second segment réseau coûte ici deux lignes de déclaration, contre un adaptateur, un sous-réseau et trois fichiers de configuration en machine virtuelle.

### 2.2 Plan des services

| Service | Image | Port interne | Publié | Réseaux |
|---|---|---|---|---|
| **proxy** | nginx, version épinglée | 80 | 8080 -> 80 | frontal |
| **metier** | construite, base python slim | 8000 | non | frontal, interne |
| **donnees** | postgres, version épinglée | 5432 | non | interne |

Le volume nommé attaché au service de données est le seul élément qui survit à la destruction des conteneurs. Tout le reste est reconstruit à partir des fichiers du dépôt : c'est la propriété que l'on cherche.

### 2.3 La règle d'or, en conteneurs

Un seul point d'entrée, comme en seconde partie. Elle se traduit ici par trois interdits, qui seront vérifiés à l'étape 14.

* Aucun port n'est publié en dehors de celui du proxy.
* Le proxy n'appartient pas au réseau de la base.
* Le client, dans le navigateur, ne s'adresse jamais au service métier directement.

> **ERREUR FRÉQUENTE**
> La tentation la plus commune est de publier le port de la base « pour pouvoir s'y connecter avec un outil graphique ». Cela rend la base joignable depuis tout le poste, et parfois depuis le réseau local : la topologie demandée n'existe plus. Pour inspecter la base, ouvrez un terminal dans le conteneur ou passez par le service métier.

---

<a id="section-3"></a>

## 3. Déroulement du travail

#### Schéma : Figure 11 — Les quatre étapes de la conteneurisation

```text
[ Service données ] ----> [ Image métier ] ----> [ Proxy et composition ] ----> [ Vérifier et comparer ]
    (Étape 11)                (Étape 12)                (Étape 13)                    (Étape 14)
```
*(Les étapes 1 à 10 doivent être achevées : c'est la même application qui est redéployée.)*

Quatre étapes, dans l'ordre des dépendances, comme en seconde partie. La différence est qu'ici, revenir en arrière ne coûte rien : détruire et reconstruire est l'opération normale, pas l'aveu d'un échec.

---

<a id="etape-11"></a>

### Étape 11 — La couche données

#### Objectif
> Obtenir une base peuplée, persistante, et joignable du seul service métier.

#### Travail à faire
* Déclarer le service à partir de l'image officielle du SGBD, avec une version explicite.
* Renseigner par variables d'environnement le nom de la base, l'utilisateur applicatif et son mot de passe.
* Attacher un volume nommé au répertoire de données, pour que celles-ci survivent au conteneur.
* Monter vos deux scripts SQL dans le répertoire d'initialisation prévu par l'image.
* Ne publier aucun port, et raccorder le service au seul réseau interne.
* Déclarer une sonde de santé, afin que les services dépendants attendent une base réellement prête.

> **ERREUR FRÉQUENTE**
> Les scripts d'initialisation ne sont exécutés qu'au tout premier démarrage, lorsque le volume est vide. Si vous modifiez ensuite votre schéma et relancez, il ne se passera rien, et vous chercherez longtemps pourquoi. Pour rejouer l'initialisation, il faut supprimer le volume — opération à connaître dès maintenant, car vous la referez souvent.

> **CONSEIL**
> Distinguez dès le départ deux commandes que les étudiants confondent : l'arrêt ordinaire conserve les volumes, tandis que la variante qui supprime aussi les volumes efface les données. Notez-les toutes deux dans votre procédure, avec leur effet, plutôt que de les redécouvrir dans l'urgence.

#### Livrables attendus
> L'extrait de déclaration du service, le volume, et la preuve que la base contient bien le jeu de données attendu.

---

<a id="etape-12"></a>

### Étape 12 — La couche métier

#### Objectif
> Construire une image de votre application et la faire dialoguer avec la base par son nom.

#### Travail à faire
* Écrire le fichier de construction de l'image : image de base légère, installation des dépendances, copie du code, commande de démarrage.
* Ordonner les instructions pour tirer parti du cache : les dépendances avant le code applicatif.
* Écrire un fichier d'exclusion, pour que l'environnement virtuel, les fichiers temporaires et l'historique du dépôt n'entrent pas dans l'image.
* Faire pointer la variable d'adresse de la base sur le nom du service de données, et non sur une adresse.
* Raccorder le service aux deux réseaux, et ne publier aucun port.

#### Sur l'adresse d'écoute
En seconde partie, faire écouter un service sur toutes les interfaces était une faute : la machine en avait plusieurs, dont certaines devaient rester privées. Dans un conteneur, c'est au contraire la bonne pratique.

La raison est que le conteneur n'a qu'une interface par réseau auquel il est raccordé, et qu'il n'est de toute façon joignable que depuis ces réseaux. L'isolation ne vient plus de l'adresse d'écoute mais de la non-publication du port. Un service qui n'écouterait que sur la boucle locale serait au contraire injoignable depuis les autres conteneurs.

> **À RETENIR**
> Ce renversement est un bon test de compréhension : la même configuration est une faute dans un cas et la règle dans l'autre, parce que la frontière d'isolation n'est pas au même endroit. Sachez l'expliquer, c'est une question d'examen naturelle.

#### Sur la taille de l'image
Une image construite sans précaution dépasse facilement le gigaoctet, alors qu'elle peut tenir en quelques centaines de mégaoctets. Trois causes reviennent : une image de base complète au lieu d'une variante réduite, l'absence de fichier d'exclusion, et des fichiers de cache d'installation conservés dans l'image.

Relevez la taille obtenue : elle entre dans la comparaison de l'étape 14, en face de l'empreinte disque des trois machines virtuelles.

#### Livrables attendus
> Le fichier de construction, le fichier d'exclusion, et la taille de l'image obtenue.

---

<a id="etape-13"></a>

### Étape 13 — Le proxy et la composition

#### Objectif
> Assembler les trois services en un ensemble qui démarre d'une seule commande.

#### Travail à faire
* Construire l'image du proxy : image officielle du serveur web, configuration et fichiers du client copiés dedans.
* Faire pointer le renvoi des appels applicatifs sur le nom du service métier, et non sur une adresse.
* Écrire le fichier de composition : les trois services, les deux réseaux, le volume, et la seule publication de port.
* Déclarer les dépendances de démarrage en les conditionnant à l'état de santé, et non au simple ordre de lancement.
* Vérifier que l'ensemble démarre, s'arrête et redémarre par une commande unique.

#### Sur les dépendances de démarrage
Déclarer qu'un service démarre après un autre ne dit rien de son état : un conteneur de base de données est « démarré » bien avant d'accepter des connexions. Le service métier tentera donc de se connecter trop tôt et s'arrêtera.

Deux réponses coexistent, et les deux sont acceptables pourvu qu'elles soient assumées : conditionner le démarrage à la sonde de santé déclarée à l'étape 11, ou rendre le service métier capable de réessayer sa connexion. La seconde est plus robuste en production, où rien ne garantit l'ordre.

> **CONSEIL**
> Votre fichier de composition remplace la procédure de déploiement manuelle de la seconde partie. Comparez les deux : le nombre de lignes, le temps de lecture, et surtout ce qu'il reste d'implicite dans chacune. C'est un élément intéressant du compte rendu.

#### Livrables attendus
> Le fichier de composition, la configuration du proxy, et une capture montrant les trois services en marche.

---

<a id="etape-14"></a>

### Étape 14 — Vérifier et comparer

#### Objectif
> Rejouer les vérifications de la seconde partie, puis mettre les deux déploiements face à face.

#### La matrice de joignabilité
Même exercice qu'à l'étape 10, avec les mêmes cases « doit échouer ». Notez que cette version est plus stricte que celle des machines virtuelles : le proxy n'atteint plus la base du tout.

| Depuis | vers proxy :80 | vers metier :8000 | vers donnees :5432 |
|---|---|---|---|
| **L'hôte** | oui, via 8080 | doit échouer | doit échouer |
| **conteneur proxy** | — | oui | doit échouer |
| **conteneur metier** | oui | — | oui |
| **conteneur donnees** | doit échouer | oui | — |

*Les vérifications se mènent depuis un terminal ouvert dans chaque conteneur. Une tentative qui échoue doit échouer parce qu'aucune route n'existe, et non parce qu'un service est arrêté : vérifiez que tout est en marche avant de conclure.*

#### Les mesures, dans les mêmes conditions
Reprenez les quatre grandeurs de l'étape 10, avec le même protocole : trois exécutions, médiane retenue, configuration consignée.

| Grandeur | Trois machines virtuelles | Trois conteneurs |
|---|---|---|
| **Temps de démarrage** | relevé à l'étape 10 | à relever |
| **Mémoire consommée** | relevé à l'étape 10 | à relever |
| **Empreinte disque** | fichiers de disque | images et volumes |
| **Latence applicative** | relevé à l'étape 10 | à relever |
| **Temps de mise en place** | depuis zéro, en séance | depuis zéro, en séance |

> **ERREUR FRÉQUENTE**
> Sur un poste sous Windows ou macOS, le moteur Docker s'exécute lui-même dans une machine virtuelle Linux. La mémoire consommée par cette machine doit être comptée dans le relevé, sans quoi la comparaison est faussée en faveur des conteneurs. Dites dans votre compte rendu comment vous l'avez mesurée, ou pourquoi vous ne pouviez pas.

#### Ce que la comparaison doit établir
L'objectif n'est pas de désigner un gagnant, mais d'énoncer un écart et de l'expliquer. Un compte rendu réussi répond à trois questions : de combien les chiffres diffèrent, quelle propriété technique explique chaque écart, et ce que le déploiement en conteneurs a perdu par rapport aux machines virtuelles.

La troisième question est celle qu'on oublie. Le noyau étant partagé, la frontière entre conteneurs est logicielle et non matérielle : plus fine, donc plus rapide, mais aussi plus fragile — et il devient impossible d'exécuter un système d'exploitation différent de celui de l'hôte.

#### Livrables attendus
> La matrice de joignabilité remplie, le tableau comparatif chiffré, et un compte rendu de deux pages répondant aux trois questions ci-dessus.

---

<a id="section-4"></a>

## 4. Ce qui vient après

Le déploiement en conteneurs clôt la partie 2 du cours. Deux prolongements sont prévus, et ils reposent tous deux sur ce que vous venez de construire.

| Suite | Ce qui sera fait | Ce que cela exige dès maintenant |
| --- | --- | --- |
| **Extensions** | Intégration de briques open source que vous n'écrivez pas — stockage de documents, moteur de recherche | Un fichier de composition lisible, où ajouter un service coûte quelques lignes |
| **Quatrième partie** | Injection de charge avec JMeter sur les deux déploiements | Les deux séries de mesures, relevées dans les mêmes conditions |

> **À RETENIR**
> Les extensions sont le véritable enjeu de la suite : vous y déploierez des composants professionnels que personne dans la salle n'a écrits. C'est une compétence distincte de celle du développement, et c'est celle que l'entreprise attend en premier.

---

<a id="section-5"></a>

## 5. Livrables et organisation

### 5.1 Récapitulatif des livrables

| Étape | Livrable | Forme |
| --- | --- | --- |
| **11** | Service de données conteneurisé | Déclaration du service, volume, preuve du peuplement |
| **12** | Image de la couche métier | Fichier de construction, fichier d'exclusion, taille |
| **13** | Ensemble composé | Fichier de composition, configuration du proxy |
| **14** | Vérification et comparaison | Matrice, tableau comparatif, compte rendu de deux pages |

### 5.2 Organisation du dépôt

Le dépôt est complété d'un dossier dédié aux conteneurs, à côté de celui du déploiement en machines virtuelles. Les deux coexistent : c'est ce qui rend la comparaison vérifiable.

```text
docker/
  metier.Dockerfile    construction de l'image applicative
  proxy.Dockerfile     configuration et fichiers du client
  compose.yaml         services, réseaux, volume, publication
  .dockerignore        ce qui n'entre pas dans les images
  PROCEDURE.md         construction et démarrage, pas à pas
docs/comparaison.md    tableau chiffré et analyse des écarts
```

Conservez le dossier de déploiement en machines virtuelles intact. Un correcteur doit pouvoir lire les deux procédures côte à côte : c'est la lecture la plus instructive de tout le projet.

### 5.3 Critères d'évaluation

| Critère | Ce qui est regardé | Poids |
|---|---|---|
| **Images construites** | Versions épinglées, ordre des instructions, taille maîtrisée | 20 % |
| **Composition** | Deux réseaux, volume, publication unique, dépendances de santé | 25 % |
| **Isolation vérifiée** | Matrice remplie, cas négatifs réellement testés | 20 % |
| **Comparaison chiffrée** | Protocole identique, moteur Docker comptabilisé | 20 % |
| **Analyse et compte rendu** | Écarts expliqués, contreparties identifiées | 15 % |

*La comparaison pèse autant que la réalisation : un déploiement en conteneurs qui fonctionne mais n'est pas mesuré ne remplit pas l'objectif de cette partie.*

---

<a id="section-6"></a>

## 6. Conduite des séances

Le déploiement en conteneurs se mène en deux séances de quatre heures, comme celui en machines virtuelles.

| Séance | Ce qui doit être atteint | Point de contrôle |
|---|---|---|
| **Première** | Étapes 11 et 12 : base conteneurisée, image métier construite | Le service métier joint la base par son nom |
| **Seconde** | Étapes 13 et 14 : composition, vérification, comparaison | Le tableau comparatif est rempli |

La première séance est la plus exposée aux pertes de temps : construction d'image, volumes à supprimer, scripts d'initialisation qui ne se rejouent pas. Prenez l'habitude de relire les journaux du conteneur avant de modifier quoi que ce soit — ils disent presque toujours ce qui ne va pas.

> **CONSEIL**
> Tenez à jour la procédure au fil des essais, comme en seconde partie. Elle sera plus courte que celle des machines virtuelles, et cette brièveté est elle-même un résultat à commenter dans le compte rendu.

---

<a id="section-7"></a>

## 7. Erreurs les plus fréquentes

Ces sept situations concentrent l'essentiel du temps perdu sur cette partie. Comme précédemment, le symptôme est la porte d'entrée du diagnostic.

| Symptôme observé | Cause la plus probable |
|---|---|
| **Le schéma modifié n'est pas pris en compte** | Le volume existe déjà : les scripts d'initialisation ne rejouent pas |
| **Le métier s'arrête juste après le démarrage** | Il se connecte avant que la base n'accepte les connexions |
| **Connexion refusée vers la boucle locale** | Adresse de base restée à localhost, qui désigne le conteneur lui-même |
| **Les données disparaissent à chaque relance** | Aucun volume : le système de fichiers du conteneur est éphémère |
| **L'image dépasse le gigaoctet** | Image de base complète, et fichier d'exclusion absent |
| **Toute modification du code relance l'installation** | Le code copié avant l'installation des dépendances |
| **L'hôte joint la base** | Port publié « pour un outil graphique » : la topologie est fausse |

> **À RETENIR**
> Le réflexe de diagnostic change par rapport aux machines virtuelles : lisez d'abord les journaux du conteneur, puis vérifiez son état, puis seulement le réseau. Un conteneur qui redémarre en boucle vous dit pourquoi à chaque tentative — encore faut-il regarder.

---

## Remarques éditoriales sur la source

- **Démarrage des services :** le travail de l’étape 13 demande des dépendances conditionnées à la santé ; son explication accepte aussi les nouvelles tentatives de connexion du métier. Ces deux formulations de la source sont conservées sans supprimer l’une au profit de l’autre.
