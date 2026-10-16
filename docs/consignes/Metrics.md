# METRICS — Injection de charge avec JMeter

## Mode de lecture pour une IA

**Périmètre :** Étapes 15 à 18, après les étapes 1 à 14 de [Dev.md](Dev.md), [Deploy.md](Deploy.md) et [Docker.md](Docker.md).

**Prérequis résumés :** Deux déploiements opérationnels, mêmes données, comptes de test et mesures de référence disponibles. Les prérequis détaillés du corps du document restent applicables.

Les sections de contexte et de contraintes s’appliquent à toutes les étapes de ce document. Suivre les étapes dans leur ordre et lire, pour chacune, l’objectif, le travail demandé, les vérifications et les livrables, ainsi que le récapitulatif final. Les critères d’évaluation et les jalons de validation restent applicables.

Conserver la portée des formulations d’origine : une obligation reste une obligation ; un conseil, une suggestion, un exemple ou une perspective ne devient pas une exigence supplémentaire. Les commandes, schémas et tableaux illustratifs ne constituent pas des preuves d’exécution. Les valeurs « à relever » et les tableaux de recette sont à renseigner à partir du travail effectué.

Les remarques éditoriales ci-dessous signalent des ambiguïtés de la source ; elles ne les tranchent pas et n’ajoutent aucun livrable.

**Parcours complet :** [DEV, étapes 1–6](Dev.md) → [VM, étapes 7–10](Deploy.md) → [Docker, étapes 11–14](Docker.md) → [Mesures, étapes 15–18](Metrics.md).

## Sommaire

- [1. Contexte et objectif](#section-1)
- [2. Le protocole de mesure](#section-2)
- [3. Déroulement du travail](#section-3)
  - [Étape 15 — Construire le plan de test](#etape-15)
  - [Étape 16 — Étalonner le protocole](#etape-16)
  - [Étape 17 — Exécuter les campagnes](#etape-17)
  - [Étape 18 — Analyser et comparer](#etape-18)
- [4. Ce qui vient après](#section-4)
- [5. Livrables et organisation](#section-5)
- [6. Conduite des séances](#section-6)

---

## Présentation

* **En-tête** : DEV — APPLICATION TROIS-TIERS

* **Titre principal** : Consultation de notes

* **Sous-titre** : Injection de charge avec JMeter

* **Section** : Quatrième partie — mesure et comparaison

* **Description** : Les deux déploiements sont soumis au même scénario de charge, dans les mêmes conditions. L'objectif n'est pas de désigner un gagnant, mais d'établir un écart chiffré et d'en expliquer la cause technique.

---

<a id="section-1"></a>

## 1. Contexte et objectif

Vous disposez de la même application déployée de deux façons : sur trois machines virtuelles, puis sur trois conteneurs. Cette dernière partie les soumet au même scénario de charge, dans les mêmes conditions, et en tire une comparaison chiffrée.

L'objectif n'est pas de désigner un gagnant. Les deux déploiements hébergent le même code et interrogent la même base : à faible charge, ils se comportent de la même façon. Ce que la mesure révèle, c'est à quelle charge chacun décroche, et pourquoi.

### 1.1 Ce que mesurer veut dire

Trois grandeurs sont indissociables, et aucune n'a de sens seule :

* **Le débit** : Le nombre de requêtes servies par seconde. Un débit élevé ne vaut rien si la moitié des requêtes échouent.

* **La latence** : Le temps de réponse. Ce n'est pas un nombre mais une distribution : la moyenne masque précisément ce qui gêne les utilisateurs.

* **Le taux d'erreur** : La proportion de requêtes qui n'aboutissent pas. Au-delà de quelques pour cent, les deux grandeurs précédentes ne décrivent plus le service rendu.

#### Pourquoi la moyenne ne suffit pas

Une latence moyenne de 200 millisecondes peut recouvrir deux situations opposées : toutes les requêtes autour de 200 millisecondes, ou bien quatre-vingt-quinze pour cent à 50 millisecondes et cinq pour cent à 3 secondes. Le second cas est celui d'un service que les utilisateurs jugeront mauvais, et la moyenne ne le dit pas.

On relève donc des centiles : la médiane, puis le 90e, le 95e et le 99e. Le 95e centile signifie que quatre-vingt-quinze pour cent des requêtes ont été servies au moins aussi vite. C'est la grandeur de référence dans l'industrie.

> **À RETENIR**
> La question à laquelle cette partie répond n'est donc pas « lequel est le plus rapide », mais « jusqu'à quelle charge chacun tient, et qu'est-ce qui cède en premier ». Une réponse correcte nomme le goulot d'étranglement.

### 1.2 Prérequis

Cette partie suppose les quatorze étapes précédentes achevées. Quatre éléments seront mis à l'épreuve dès la première séance :

* **Les deux déploiements opérationnels** : Chacun doit pouvoir être démarré et arrêté à la demande, sans reconfuguration.

* **Un jeu de données identique** : Les mêmes scripts de peuplement, donc le même volume et le même contenu des deux côtés.

* **Assez de comptes de test** : Une vingtaine au minimum. Avec un seul compte, toutes les requêtes frappent la même ligne, les caches font leur travail et les chiffres devienneent flatteurs.

---

* **Les mesures de référence** : Les relevés des étapes 10 et 14 servent de point de départ et de contrôle de cohérence.

### 1.3 Contraintes techniques

| Élément | Imposé | Laissé libre |
|---|---|---|
| **Outil d'injection** | Apache JMeter | Version, tant qu'elle est récente |
| **Exécution des campagnes** | En ligne de commande, sans interface graphique | — |
| **Emplacement de l'injecteur** | Sur l'hôte, hors du système mesuré | — |
| **Résultats bruts** | Fichier de résultats conservé et versionné | Format de sortie |
| **Durée d'un palier** | Au moins soixante secondes hors montée | Nombre de paliers |

> **ERREUR FRÉQUENTE**
> L'interface graphique de JMeter sert à construire et à déboguer un plan de test, jamais à exécuter une campagne. Elle consomme du processeur et de la mémoire sur la machine même qui injecte, et fausse donc les mesures. Toute campagne se lance en ligne de commande.

---

<a id="section-2"></a>

## 2. Le protocole de mesure

#### [DESCRIPTION DU SCHÉMA : Figure 12 — La chaîne de mesure]

* **Injecteur (sur l'hôte, hors du système mesuré)** : Contient `JMeter`. Il envoie des requêtes HTTP vers le système sous test.

* **SYSTÈME SOUS TEST (un seul déploiement à la fois)** : Encadré en pointillés comprenant :

* `proxy` (point d'entrée)

* `metier` (Python)

* `donnees` (PostgreSQL)

* Note : machines virtuelles puis conteneurs — jamais les deux en marche ensemble.

* **Mesures relevées** :
* **Côté client** : débit, latence, erreurs.

* **Côté serveur** : processeur, mémoire, entrées-sorties, connexions.

* *Légende* : Figure 12 — La chaîne de mesure : l'injecteur, le système sous test, et ce que l'on relève de chaque côté.

L'injecteur s'exécute sur l'hôte, en dehors du système mesuré. Il envoie des requêtes et relève ce qu'un utilisateur perçoit. En parallèle, vous relevez sur le système lui-même ce qu'il consomme : ce sont ces deux séries qui, mises face à face, permettent d'expliquer un écart plutôt que de le constater.

### 2.1 Le scénario de charge

Un utilisateur virtuel reproduit le parcours étudiant de la première partie : il se connecte, puis consulte ses notes. C'est le parcours le plus représentatif, et le seul qui traverse les trois couches.

| Ordre | Requête | Ce qui doit être vérifié |
|---|---|---|
| **1** | Ouverture de session avec un compte tiré du fichier de comptes | Le code de retour et la présence du jeton ou du cookie |
| **2** | Consultation des notes de l'utilisateur connecté | Le code de retour et la présence d'au moins une note |

#### Les éléments du plan de test

Six éléments suffisent, et chacun répond à un besoin précis du scénario :

* **Le groupe d'unités** : Il porte le nombre d'utilisateurs simultanés, la durée de montée et la durée totale. C'est lui que vous ferez varier d'un palier à l'autre.

* **Le jeu de données** : Un fichier de comptes, lu ligne par ligne, pour que les utilisateurs virtuels ne soient pas tous la même personne.

* **Le gestionnaire de cookies** : Sans lui, chaque requête repart sans session et la seconde requête échoue systématiquement.

* **L'extracteur** : Il récupère le jeton renvoyé par la connexion pour le réinjecter dans la requête suivante, si votre mécanisme de session repose sur un jeton plutôt qu'un cookie.

* **Les assertions** : Elles vérifient que la réponse est bien celle attendue, et non une page d'erreur renvoyée avec un code de succès.

---

* **La temporisation** : Un temps de réflexion entre deux requêtes, pour que le scénario ressemble à un usage réel et non à une attaque.

> **ERREUR FRÉQUENTE**
> Sans assertion, une application qui renvoie sa page de connexion à chaque requête affiche un taux d'erreur de zéro pour cent : le serveur a bien répondu. C'est l'erreur la plus coûteuse de cette partie, parce qu'elle produit des chiffres plausibles et entièrement faux.

### 2.2 Le profil de charge

#### [DESCRIPTION DU SCHÉMA : Figure 13 — Montée par paliers]

* **Axe Y** : utilisateurs simultanés.

* **Axe X** : temps.

* **Forme du graphique** : Une courbe en escalier représentant la montée progressive par paliers avec des phases de « montée » suivies de plateaux stables désignés comme « fenêtre de mesure » `|-------|`.

* *Légende* : Chaque palier dure assez longtemps pour être mesuré hors montée. On monte jusqu'à ce que le débit cesse de croître. Figure 13 — Montée par paliers, avec une fenêtre de mesure sur chaque plateau.

On n'applique pas une charge d'emblée : on monte par paliers, et l'on mesure sur chaque plateau, une fois la montée terminée. Inclure la période de montée dans le relevé sous-estime le débit et gonfle la latence.

On augmente tant que le débit croît. Lorsqu'il cesse de croître alors que la latence, elle, continue d'augmenter, le point de saturation est atteint : c'est la grandeur intéressante de toute cette partie, et elle sera différente pour les deux déploiements.

| Relevé côté client | Relevé côté serveur |
|---|---|
| Débit, en requêtes par seconde | Charge processeur, par service |
| Latence : médiane, 90e, 95e et 99e centiles | Mémoire consommée, par service |
| Taux d'erreur, par type de requête | Entrées-sorties disque sur la base |
| Nombre d'utilisateurs simultanés effectifs | Nombre de connexions ouvertes à la base |

### 2.3 La règle d'or de la mesure

On ne compare que ce qui a été mesuré dans les mêmes conditions. Cette règle paraît évidente et se viole sans y penser ; elle se décline ici en cinq exigences :

* Même jeu de données, même scénario, même plan de test, même fichier de comptes.

* Même poste, même session de travail, applications de fond identiques.

---

* Un seul déploiement en marche à la fois : deux déploiements allumés se partagent le processeur.

* L'injecteur ne doit jamais être le facteur limitant — c'est l'objet de l'étalonnage de l'étape 16.

* Chaque chiffre est consigné avec la configuration qui l'a produit.

> **À RETENIR**
> Un résultat non reproductible n'est pas un résultat. Si deux exécutions identiques donnent des chiffres qui diffèrent de plus de dix pour cent, ce n'est pas le déploiement que vous mesurez : c'est le bruit de votre poste.

---

<a id="section-3"></a>

## 3. Déroulement du travail

#### [DESCRIPTION DU SCHÉMA : Figure 14 — Les quatre étapes de la mesure]

Diagramme de flux linéaire :
`[Plan de test (Étape 15)]` ➔ `[Étalonnage du protocole (Étape 16)]` ➔ `[Campagnes de mesure (Étape 17)]` ➔ `[Analyse et comparaison (Étape 18)]`
*Note associée* : Les deux déploiements doivent être opérationnels et démarrables à la demande.
*Légende* : Figure 14 — Les quatre étapes de la mesure.

Quatre étapes. Les deux premières construisent et valident l'instrument ; les deux dernières s'en servent. Il est tentant de sauter l'étape 16 : c'est elle qui décide si vos chiffres vaudront dire quelque chose.

<a id="etape-15"></a>

### Étape 15 — Construire le plan de test

#### Objectif
> Obtenir un scénario qui reproduit fidèlement le parcours étudiant et qui détecte ses propres échecs.

#### Travail à faire

* Créer le plan de test avec un groupe d'unités, les deux requêtes du parcours, et le gestionnaire de cookies.

* Préparer un fichier de comptes de test et le brancher comme jeu de données du plan.

* Ajouter l'extraction du jeton de session si votre authentification en utilise un.

* Ajouter une assertion sur chacune des deux requêtes : code de retour attendu, et contenu attendu.

* Valider le plan avec un seul utilisateur et une seule itération, dans l'interface graphique, jusqu'à ce que le parcours réussisse.

* Vérifier qu'il échoue quand il doit échouer : avec un mot de passe erroné, l'assertion doit se déclencher.

> **CONSEIL**
> Ce dernier point est le test du test. Un plan qui ne sait pas détecter un échec produira des campagnes entières sans jamais signaler que l'application ne répond plus correctement. Prenez cinq minutes pour vérifier qu'il sait dire non.

#### Livrables attendus
> Le fichier du plan de test, le fichier de comptes, et la capture d'une exécution à un utilisateur montrant le parcours réussi puis le parcours en échec.

---

<a id="etape-16"></a>

### Étape 16 — Étalonner le protocole

#### Objectif
> S'assurer que l'instrument mesure le système, et non lui-même.

#### Travail à faire

* Mesurer ce que l'injecteur seul peut produire, en visant une ressource statique servie par le proxy : c'est son plafond.

* Vérifier que ce plafond est nettement supérieur au débit que vous attendez de l'application.

* Fixer la durée de montée et la durée de plateau, puis les geler pour toutes les campagnes.

* Choisir la suite des paliers, en progression large — par exemple 1, 5, 10, 25, 50, 100 utilisateurs.

* Exécuter deux fois la même campagne sur le même déploiement et comparer : l'écart doit rester faible.

#### Pourquoi cette étape existe

Si l'injecteur sature avant l'application, tous vos paliers suivants mesureront JMeter. Le symptôme est reconnaissable : le débit plafonne à la même valeur sur les deux déploiements, et la charge processeur de l'hôte est élevée alors que celle des services reste modeste.

Le contrôle de répétabilité joue le même rôle sur l'autre plan. Deux exécutions identiques qui diffèrent nettement indiquent que votre poste n'est pas dans un état stable : antivirus, indexation, mises à jour, ou simplement un navigateur resté ouvert.

#### Livrables attendus
> Un court rapport d'étalonnage : plafond de l'injecteur, paliers retenus, durées, et les deux exécutions de contrôle avec leur écart.
<a id="etape-17"></a>

### Étape 17 — Exécuter les campagnes

#### Objectif
> Produire deux séries de mesures comparables, une par déploiement.

#### Travail à faire

* Démarrer un seul déploiement, vérifier qu'il répond, et arrêter l'autre complètement.

* Réinitialiser la base à partir des scripts de peuplement, pour partir du même état à chaque campagne.

* Lancer la campagne en ligne de commande, palier par palier, en conservant le fichier de résultats brut.

* Relever en parallèle les métriques du système sous test, pendant chaque palier.

* Recommencer sur l'autre déploiement, dans les mêmes conditions et dans la même séance.

* Alterner l'ordre lors d'une seconde série, pour vérifier que l'ordre de passage n'influence pas le résultat.

---

La commande d'exécution prend cette forme : on désigne le plan, on nomme le fichier de résultats, et l'on passe le nombre d'utilisateurs en paramètre pour n'avoir qu'un seul plan à maintenir :

```bash
jmeter -n -t plan.jmx -l resultats/vm-50.csv -Jutilisateurs=50
```

> **ERREUR FRÉQUENTE**
> Ne laissez jamais les deux déploiements en marche pendant une campagne. Trois machines virtuelles et trois conteneurs actifs simultanément se partagent le processeur et la mémoire du poste : les deux séries seront dégradées, et la comparaison ne mesurera plus que la capacité de votre portable.

> **CONSEIL**
> Conservez les fichiers de résultats bruts dans le dépôt, même volumineux. Un tableau de synthèse sans les données qui l'ont produit n'est pas vérifiable, et c'est la première chose qu'un correcteur demande quand un chiffre surprend.

#### Livrables attendus
> Les fichiers de résultats bruts des deux séries, et le relevé des métriques serveur palier par palier.

<a id="etape-18"></a>

### Étape 18 — Analyser et comparer

#### Objectif
> Établir l'écart, l'expliquer, et dire ce que la mesure ne montre pas.

#### Travail à faire
* Tracer, pour les deux déploiements, le débit en fonction du nombre d'utilisateurs.
* Tracer de même la latence au 95e centile, et le taux d'erreur.
* Identifier sur chaque courbe le point de saturation, et le nommer.
* Rapprocher ce point des métriques serveur pour désigner le goulot d'étranglement.
* Remplir le tableau de synthèse et rédiger l'analyse.

#### Le tableau de synthèse

| Grandeur | Trois machines virtuelles | Trois conteneurs |
|---|---|---|
| **Débit maximal soutenu** | à relever | à relever |
| **Charge au point de saturation** | à relever | à relever |
| **Latence au 95e centile, à charge égale** | à relever | à relever |
| **Goulot d'étranglement identifié** | à nommer | à nommer |
| **Temps de démarrage complet** | étape 10 | étape 14 |
| **Mémoire consommée au repos** | étape 10 | étape 14 |

#### Ce que l'analyse doit établir

Un compte rendu réussi répond à quatre questions, dans cet ordre. De combien les deux déploiements diffèrent-ils, chiffres à l'appui. Quelle propriété technique explique cet écart. Quel composant cède en premier, dans chaque cas. Et enfin : que ne dit pas cette mesure.

La dernière question est celle qui distingue un rapport d'ingénieur d'un relevé d'élève. Vos mesures portent sur un poste de travail, avec un jeu de données de quelques centaines de lignes et un scénario à deux requêtes. Elles ne disent rien de la tenue en production, ni du comportement sur plusieurs machines physiques, ni de la résistance à une panne.

> **À RETENIR**
> Méfiez-vous d'une conclusion trop nette. Si vous trouvez que les conteneurs servent dix fois plus de requêtes, c'est probablement que quelque chose est mal réglé du côté des machines virtuelles — nombre de processus du serveur applicatif, mémoire allouée, ou base non réinitialisée. Un écart énorme est d'abord un signal de vérification, pas un résultat.

#### Livrables attendus
> Les courbes, le tableau de synthèse rempli, et un rapport de trois à quatre pages répondant aux quatre questions ci-dessus.

---

<a id="section-4"></a>

## 4. Ce qui vient après

La mesure clôt le parcours, mais elle ouvre aussi la suite du cours : une fois l'instrument construit et le protocole établi, toute modification de l'architecture devient évaluable.

| Prolongement | Ce qui serait mesuré | Ce que votre travail apporte |
|---|---|---|
| **Cache applicatif** | L'effet d'un cache devant les requêtes de consultation | Le même plan de test, rejoué à l'identique |
| **Répartition de charge** | Le gain obtenu en doublant la couche métier | Le point de saturation, qui donne le palier à viser |
| **Extensions open source** | Le coût d'un moteur de recherche ou d'un stockage de documents | Un protocole établi, applicable à toute brique ajoutée |

C'est la raison pour laquelle le plan de test et le protocole valent mieux que les chiffres : les chiffres décrivent une configuration, l'instrument sert à toutes les suivantes.

---
<a id="section-5"></a>

## 5. Livrables et organisation

### 5.1 Récapitulatif des livrables

| Étape | Livrable | Forme |
|---|---|---|
| **15** | Plan de test | Fichier du plan, fichier de comptes, captures de validation |
| **16** | Étalonnage | Rapport court : plafond, paliers, durées, répétabilité |
| **17** | Campagnes | Fichiers de résultats bruts et relevés serveur |
| **18** | Analyse | Courbes, tableau de synthèse, rapport de trois à quatre pages |

### 5.2 Organisation du dépôt
Un dossier dédié à la mesure, à côté de ceux des deux déploiements.
```text
charge/
    plan.jmx                 plan de test
    comptes.csv              comptes de test
    etalonnage.md            plafond de l'injecteur et répétabilité
    resultats/vm-*.csv       campagnes, machines virtuelles
    resultats/dk-*.csv       campagnes, conteneurs
    docs/rapport-charge.md   courbes, synthèse et analyse

```
Nommez les fichiers de résultats de façon à ce qu'on lise le déploiement et le palier dans le nom. Vous en produirez une vingtaine, et ils se ressemblent tous.

### 5.3 Critères d'évaluation

| Critère | Ce qui est regardé | Poids |
|---|---|---|
| **Plan de test** | Parcours complet, session gérée, assertions qui détectent l'échec | 20 % |
| **Protocole** | Étalonnage de l'injecteur, répétabilité, conditions identiques | 25 % |
| **Campagnes** | Paliers, métriques serveur, données brutes conservées | 15 % |
| **Analyse** | Courbes lisibles, point de saturation, goulot nommé | 25 % |
| **Honnêteté des conclusions** | Limites énoncées, écarts suspects vérifiés | 15 % |

Le protocole et l'analyse pèsent la moitié de la note. Des chiffres obtenus sans étalonnage, ou une conclusion qui ne nomme aucun goulot d'étranglement, ne remplissent pas l'objectif de cette partie — même si les campagnes ont bien été exécutées.
<a id="section-6"></a>

## 6. Conduite des séances
La mesure se mène en deux séances de quatre heures. La première construit l'instrument, la seconde s'en sert.

| Séance | Ce qui doit être atteint | Point de contrôle |
|---|---|---|
| **Première** | Étapes 15 et 16 : plan validé, protocole étalonné | Deux exécutions identiques donnent des chiffres proches |
| **Seconde** | Étapes 17 et 18 : campagnes et analyse | Le tableau de synthèse est rempli et commenté |

Ne commencez pas les campagnes si l'étalonnage n'est pas concluant. Une journée de mesures faites avec un injecteur saturé produit des fichiers volumineux dont rien ne pourra être tiré, et il faudra tout recommencer.
> **CONSEIL**
> Fermez tout ce qui tourne sur votre poste avant une campagne, et notez ce que vous avez fermé. Cette liste fait partie de la configuration : elle explique pourquoi les chiffres d'un binôme diffèrent de ceux d'un autre, et pourquoi les vôtres sont reproductibles.

---

## Remarques éditoriales sur la source

- **Section annoncée mais absente :** l’ancien sommaire annonçait « 7. Erreurs les plus fréquentes » (page 61), mais le fichier fourni s’arrête à la section 6. Les avertissements présents dans les autres sections sont conservés ; aucune section manquante n’est reconstituée.
