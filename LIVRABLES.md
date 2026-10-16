# Intern — dossier des livrables

Ce dossier suit les quatre cahiers des charges, étape par étape :
**DEV (1–6), déploiement VM (7–10), Docker (11–14), mesures (15–18)**.
Pour chaque étape, lire la consigne résumée, puis ouvrir les livrables à présenter.
Les procédures et preuves détaillées sont accessibles séparément.

Les commandes de chaque étape sont réunies dans [EXECUTION.md](EXECUTION.md).

Les consignes ci-dessous sont reformulées et adaptées à Intern. Les résultats
rapportés proviennent des vérifications archivées ; ils ne constituent pas une
approbation pédagogique ni un contrôle en direct des services.

## Sommaire

| Cahier des charges | Étapes, dans l'ordre |
| --- | --- |
| DEV | [1. Analyse](#etape-1) · [2. Figma](#etape-2) · [3. Données](#etape-3) · [4. Métier](#etape-4) · [5. Présentation](#etape-5) · [6. Recette](#etape-6) |
| Déploiement VM | [7. Machines](#etape-7) · [8. Réseau](#etape-8) · [9. Couches](#etape-9) · [10. Vérification et exports](#etape-10) |
| Docker | [11. Données](#etape-11) · [12. Image métier](#etape-12) · [13. Composition](#etape-13) · [14. Comparaison](#etape-14) |
| Mesures | [15. Plan JMeter](#etape-15) · [16. Étalonnage](#etape-16) · [17. Campagnes](#etape-17) · [18. Analyse](#etape-18) |

## DEV — concevoir et développer

<a id="etape-1"></a>
### Étape 1 — Analyse

**Consigne.** Décrire les acteurs, les cas d'usage (déclencheur, parcours nominal,
erreurs) et la matrice des règles de gestion dans un document PDF.

**À présenter : [analyse fonctionnelle PDF](analyse/cas_d_usage.pdf).**

**Réponse.** Trois acteurs (candidat, recruteur, administrateur), onze cas d'usage
UC01–UC11 et six règles R1–R6 ; les cas d'erreur et les listes vides sont décrits.
Document disponible, approbation pédagogique non attestée.

Détail : [source de l'analyse](analyse/cas_d_usage.md) · [génération du PDF](analyse/README.md).

<a id="etape-2"></a>
### Étape 2 — Prototype Figma

**Consigne.** Fournir un prototype cliquable en lecture et une capture de l'écran
zéro : parcours des trois acteurs, écrans terminaux, états dégradés et données
plausibles. L'approbation du prototype constitue le jalon avant développement.

**À présenter : [prototype interactif, écran zéro](https://www.figma.com/proto/2zB64zoXsnJQ24R1yysJ72/Intern?node-id=142-38134&scaling=contain&content-scaling=responsive&starting-point-node-id=142%3A38134)
· [capture de l'écran zéro](maquette/ecran_zero.jpg).**

**Réponse.** Les parcours candidat, recruteur et administrateur sont répertoriés.
Les liens et la capture sont disponibles ; l'accès lecture, la navigation
interactive et l'approbation du prototype restent à confirmer.

Détail : [parcours et liens](maquette/README.md) · [relevé des écrans et interactions](maquette/figma_manifest.json).

<a id="etape-3"></a>
### Étape 3 — Couche données

**Consigne.** Livrer le schéma SQL, le peuplement fictif avec cas limites et les
requêtes de consultation. Garantir les contraintes d'intégrité et d'unicité ;
stocker les mots de passe avec un hachage salé lent.

**À présenter : [schema.sql](donnees/schema.sql) · [data.sql](donnees/data.sql)
· [requêtes SQL](donnees/requetes.sql).**

**Réponse.** Le jeu contient huit comptes, trois entreprises, quatre stages et
deux candidatures, avec compte en attente et cas vides. Le modèle utilise scrypt
et un alias SQL `mot_de_passe_hash`. L'unicité candidat/offre est assurée par
une contrainte composée avec PK technique, plutôt que par une PK composée.
Le fichier de requêtes est nommé `requetes.sql` (équivalent de `queries.sql`
attendu au récapitulatif). **34 contrôles SQL et 43 tests ciblés réussis** sont consignés.

Détail : [modèle et choix de conception](donnees/MODELE.md) · [validation](donnees/VALIDATION.md)
· [lancement](donnees/README.md#lancement-guidé) · [schéma visuel PDF](donnees/schema_visuel.pdf).

<a id="etape-4"></a>
### Étape 4 — Couche métier

**Consigne.** Fournir l'API Python, ses dépendances et des exemples HTTP ; gérer
sessions, identité serveur, propriété des ressources, configuration externe et
codes de réponse adaptés.

**À présenter : [code de l'API](metier/app/) · [requirements.txt](metier/requirements.txt)
· [requêtes api.http](metier/api.http).**

**Réponse.** Django utilise les sessions et le CSRF ; l'inscription crée un
compte en attente. Les accès privés sont limités au propriétaire et la
configuration est externalisée. **41 tests ciblés réussis** sont archivés ;
la démonstration interactive du fichier HTTP reste à exécuter.

Détail : [validation](metier/VALIDATION.md) · [architecture et lancement](metier/README.md)
· [configuration exemple](metier/.env.example).

<a id="etape-5"></a>
### Étape 5 — Couche présentation

**Consigne.** Livrer le client web et une vidéo ou des captures des parcours ;
reproduire les maquettes, communiquer uniquement avec l'API et traiter attente,
erreurs et listes vides avec une URL d'API configurable.

**À présenter : [code du client](frontend/src/) · [captures de chaque écran principal](frontend/captures/README.md).**

**Réponse.** React/TypeScript centralise les appels REST et utilise
`VITE_API_ROOT`. Le build et le lint passent ; **104 tests navigateur réussis,
3 scénarios de logos externes ignorés** sont consignés. Les tests utilisent des réponses API contrôlées ; la nouvelle série de captures
présente chaque écran principal sur React, Django et PostgreSQL réels.
La conformité visuelle au Figma reste à vérifier.

Détail : [validation et limites](frontend/VALIDATION.md) · [lancement](frontend/README.md).

<a id="etape-6"></a>
### Étape 6 — Intégration et tests

**Consigne.** Remettre le dépôt complet, l'installation pas à pas et le tableau
rempli (action, attendu, obtenu, statut). Tester les parcours nominaux, les
erreurs et les accès par modification d'identifiant sur une base réinitialisée.

**À présenter : [dépôt du projet](./) · [installation locale](README.md#démarrage-local)
· [cahier de recette PDF](tests/cahier_de_tests.pdf).**

**Réponse.** **15 parcours navigateur/API réels** sur PostgreSQL isolé et
**560 tests métier réussis** sont consignés. Le tableau distingue les tests
réussis des contrôles restants : installation locale sur une VM vierge et
comparaison interactive au prototype. Le déploiement VM des étapes 7–10
possède ses propres preuves.

Détail : [tableau consultable](tests/cahier_de_tests.html) · [reproduction de la recette](tests/README.md).

## Déploiement — trois machines virtuelles

<a id="etape-7"></a>
### Étape 7 — Préparer les machines

**Consigne.** Cloner un modèle en trois machines distinctes, régénérer MAC et
identités, fixer noms et ressources et prendre un snapshot initial « base propre ».
Fournir une capture de la liste VirtualBox.

**À présenter : [capture VirtualBox](deploiement/docs/virtualbox-machines.png).**

**Réponse.** `vm-proxy` : 1 vCPU / 1 Gio ; `vm-metier` et `vm-donnees` :
2 vCPU / 2 Gio chacune. Les identités distinctes et les trois snapshots initiaux
sont consignés dans les preuves. **Le modèle vient d’une OVA Ubuntu Server
officielle, plutôt que de la machine du TP 1 demandée.**

Détail : [rapport](deploiement/docs/etape7.md) · [identités et snapshots](deploiement/docs/identites-etape7.json)
· [commandes de préparation](deploiement/scripts/PROCEDURE.md).

<a id="etape-8"></a>
### Étape 8 — Réseau et adressage

**Consigne.** Livrer le plan d'adressage, les trois configurations réseau et
les sorties de vérification. Utiliser un réseau interne commun ; seul le proxy
possède un NAT et la redirection hôte 8080 vers port 80.

**À présenter : [plan d'adressage](deploiement/reseau/README.md)
· Netplan [proxy](deploiement/reseau/vm-proxy.yaml), [métier](deploiement/reseau/vm-metier.yaml),
[données](deploiement/reseau/vm-donnees.yaml) · [sorties des commandes](deploiement/docs/preuves-etape8.txt).**

**Réponse.** `intnet-app`, réseau `10.10.10.0/24` ; proxy `.10`, métier `.20`,
base `.30`. **Six pings réussis, sans perte** ; aucun NAT ni route IPv4 par défaut
sur métier et données après configuration.

Détail : [rapport de vérification](deploiement/docs/etape8.md).

<a id="etape-9"></a>
### Étape 9 — Déployer les couches

**Consigne.** Installer dans l'ordre base, métier, proxy, avec snapshot avant
chaque couche et configuration externe. Remettre les configurations réseau,
base, service applicatif et serveur web, ainsi que la procédure actualisée.

**À présenter : [configurations des trois machines et procédure](deploiement/DEPLOIEMENT.md#configurations-livrées).**

**Réponse.** PostgreSQL, Django/Gunicorn et Nginx sont installés sur leurs VM.
Après redémarrage, les services démarrent automatiquement ; **34 contrôles SQL
et 8 contrôles navigateur réussis** sont archivés. Le code applicatif est
conservé, les accès NAT temporaires ont été retirés.

Détail : [rapport](deploiement/docs/etape9.md) · [preuves VM](deploiement/docs/preuves-etape9.txt)
· [recette navigateur](deploiement/docs/recette-etape9.txt) · [capture réelle](deploiement/docs/etape9-tableau-de-bord.png).

<a id="etape-10"></a>
### Étape 10 — Vérifier, mesurer et exporter

**Consigne.** Fournir la matrice de joignabilité remplie et ses sorties de
commandes, les mesures de référence (trois essais, médiane, configuration) et
les trois machines exportées en OVA.

**À présenter : [matrice remplie](deploiement/docs/etape10.md#matrice-de-joignabilité-observée)
· [preuves réseau](deploiement/docs/preuves-etape10.txt)
· [tableau des mesures](deploiement/docs/mesures.md)
· [inventaire des trois OVA et empreintes](deploiement/docs/exports-etape10.json).**

**Réponse.** **Neuf liaisons conformes**, dont trois refus réellement testés.
Trois séries de démarrage, mémoire, disque et latence sont conservées.
Les exports `vm-proxy.ova`, `vm-metier.ova`, `vm-donnees.ova` sont annoncés et
contrôlés dans les preuves d'export, avec manifests et lecture VirtualBox.

**Remise séparée.** Les trois archives et `SHA256SUMS` sont hors dépôt dans
`$VM_WORK/exports-etape10` : les joindre au rendu selon la
[procédure de remise et réimportation](deploiement/VERIFICATION.md#exports-ova).
L'inventaire ne remplace pas les archives. Le démarrage après réimportation
n'a pas été testé.

Détail : [preuves d'export](deploiement/docs/preuves-exports-etape10.txt)
· [valeurs brutes](deploiement/docs/mesures-etape10.json).

## Docker — trois services conteneurisés

<a id="etape-11"></a>
### Étape 11 — Couche données

**Consigne.** Déclarer une base versionnée, son volume nommé, l'initialisation
SQL et sa sonde de santé, sans port publié sur le réseau interne. Fournir la
preuve du peuplement et vérifier la persistance après recréation.

**À présenter : [service donnees et volume pgdata](docker/compose.yaml)
· [résultats SQL sur Docker Engine](docker/docs/sql-etape14.txt)
· [preuve de persistance](docker/docs/verification-etape14.json).**

**Réponse.** PostgreSQL `16.15-bookworm`, volume `pgdata`, scripts SQL partagés
avec l'étape 3. **34 contrôles SQL réussis**, avant et après recréation,
sont consignés à l'étape 14 sur Docker Engine.

Détail : [initialisation et persistance](docker/PROCEDURE.md#déclaration-et-initialisation).

<a id="etape-12"></a>
### Étape 12 — Image métier

**Consigne.** Livrer le Dockerfile, le fichier d'exclusion et la taille obtenue ;
mettre les dépendances avant le code, utiliser le nom de service de la base et
raccorder le métier aux deux réseaux sans publier son port.

**À présenter : [Dockerfile métier](docker/metier.Dockerfile)
· [.dockerignore](docker/.dockerignore)
· [taille de l'image Docker Engine](docker/docs/etape14.md#moteur-et-protocole).**

**Réponse.** Construction en deux stages sur Python slim, cache des dépendances,
`POSTGRES_HOST=donnees`, écoute sur `0.0.0.0:8000` dans le conteneur.
Docker Engine annonce **372 903 397 octets** pour l'image métier ; cette taille
se distingue de l'empreinte disque cumulée des images et du volume.

Détail : [construction](docker/PROCEDURE.md#étape-12--construire-limage-métier)
· [mesures brutes Docker](docker/docs/mesures-etape14.json).

<a id="etape-13"></a>
### Étape 13 — Proxy et composition

**Consigne.** Livrer Compose, la configuration du proxy et une capture des trois
services en marche. Assembler trois services, deux réseaux et un volume ; publier
uniquement le proxy et conditionner les dépendances à la santé.

**À présenter : [compose.yaml](docker/compose.yaml) · [proxy.conf](docker/proxy.conf)
· [capture des trois services](docker/docs/etape13-services.png).**

**Réponse.** Le proxy relaie vers `metier:8000` ; seul `127.0.0.1:8080` est
publié. Le métier relie `frontal` et `interne` ; proxy et base ne partagent aucun
réseau. **La capture des services provient de Podman.** Les trois services
sains et la recette réelle sur Docker Engine sont attestés séparément à l'étape 14.

Détail : [Dockerfile proxy](docker/proxy.Dockerfile) · [commandes uniques](docker/PROCEDURE.md#une-commande-pour-chaque-opération)
· [preuve Docker Engine](docker/docs/verification-etape14.json).

<a id="etape-14"></a>
### Étape 14 — Vérifier et comparer

**Consigne.** Fournir la matrice remplie, le tableau VM/Docker chiffré et un compte
rendu de deux pages : écarts, explications techniques et contreparties des
conteneurs. Reprendre les mesures de l'étape 10 avec trois essais et médianes.

**À présenter : [matrice et tableau comparatif](docs/comparaison.md)
· [compte rendu PDF, deux pages](docs/compte_rendu_comparaison.pdf).**

**Réponse.** Sur Docker Engine rootless, **neuf liaisons conformes**, dont
quatre refus ; trois séries mesurées. Médianes VM/Docker : démarrage
**20,473 / 49,844 s**, RSS hôte **1,454 / 0,568 Gio**, disque (fichiers)
**10,783 / 0,809 Gio**, consultation **62,431 / 83,385 ms**.
Le temps de mise en place initiale est **non chronométré**.
Les versions, quotas et périmètres différents limitent l'attribution des écarts.

Détail : [rapport et limites](docker/docs/etape14.md) · [matrice brute](docker/docs/joignabilite-etape14.json)
· [mesures brutes](docker/docs/mesures-etape14.json).

## Mesures — injection de charge JMeter

<a id="etape-15"></a>
### Étape 15 — Plan de test

**Consigne.** Livrer le plan, les comptes de test et les captures GUI à un
utilisateur et une itération, en réussite puis en échec. Gérer cookies, jetons
nécessaires et assertions sur le code et le contenu des réponses.

**À présenter : [plan.jmx](mesure/plan.jmx) · [comptes.csv](mesure/comptes.csv)
· [réussite JMeter](mesure/resultats/etape15/reussite.png)
· [échec JMeter](mesure/resultats/etape15/echec.png).**

**Réponse.** Parcours candidat : préparation CSRF, connexion puis consultation
des candidatures personnelles. Les vingt comptes sont fictifs. Les essais
CLI et GUI sur Docker isolé attestent le succès et l'assertion déclenchée par
un mauvais mot de passe, avec arrêt avant consultation.

Détail : [rapport et résultats bruts](mesure/ETAPE15.md) · [procédure](mesure/PROCEDURE.md).

<a id="etape-16"></a>
### Étape 16 — Étalonnage

**Consigne.** Remettre un court rapport : plafond de l'injecteur vers une
ressource statique, paliers et durées figés, deux contrôles identiques et écarts.

**À présenter : [rapport d'étalonnage](mesure/ETAPE16.md).**

**Réponse.** Plafond observé du chemin injecteur/proxy : **3 250,15 req/s**.
Paliers **1, 5, 10, 20** ; montée **30 s**, stabilisation **15 s**, plateau
**120 s**, réflexion **1 s**. Deux contrôles à dix utilisateurs : zéro erreur,
écarts de débit **0,09 %** et de p95 **4,65 %**.

Détail : [protocole commun](mesure/protocole.json)
· [mesures et empreintes](mesure/resultats/etape16/etalonnage.json).
La préparation de la base commune, encore attendue à cette étape, est documentée à l'étape 17.

<a id="etape-17"></a>
### Étape 17 — Campagnes

Campagne courante : **16 paliers, 22 206 échantillons, zéro erreur, aucun incident**
([vérification](mesure/resultats/campagne/verification.json)). Les preuves ci-dessous
restent celles utilisées par le rapport de l’étape 18.

**Consigne.** Conserver les résultats bruts et les métriques serveur par palier.
N'activer qu'un déploiement, restaurer les mêmes données, mesurer en CLI et
inverser l'ordre VM/Docker dans une seconde série.

**À présenter : résultats bruts [série 1 VM](mesure/resultats/etape17/serie-1/vm/),
[série 1 Docker](mesure/resultats/etape17/serie-1/docker/),
[série 2 Docker](mesure/resultats/etape17/serie-2/docker/),
[série 2 VM](mesure/resultats/etape17/serie-2/vm/)
· [métriques serveur par palier](mesure/resultats/etape17/releve-serveurs.csv).**

**Réponse.** **16 paliers, 22 199 échantillons, zéro erreur** ; 48 lignes de
synthèse serveur, avec au moins 22 observations stables par service et palier.
L'export SQL commun est restauré avant chaque campagne dédiée. Une panne Docker
et sa reprise interrompent la continuité de la séance et limitent l'interprétation
de l'effet de l'ordre ; elles sont conservées dans le journal.

Détail : [rapport et incident](mesure/ETAPE17.md) · [synthèse des paliers](mesure/resultats/etape17/releve-paliers.csv)
· [vérification des résultats](mesure/resultats/etape17/verification.json).

<a id="etape-18"></a>
### Étape 18 — Analyse

**Consigne.** Remettre les courbes débit/p95/erreurs, le tableau rempli et un
rapport de trois à quatre pages : écarts chiffrés, explications techniques,
composant limitant et limites de la mesure. Rechercher saturation et goulot.

**À présenter : [courbes](mesure/docs/courbes/ensemble.png)
· [tableau de synthèse](mesure/docs/rapport-charge.md#le-tableau-de-synthèse)
· [rapport PDF, quatre pages](mesure/docs/rapport-charge.pdf).**

**Réponse.** À vingt utilisateurs : débit moyen VM/Docker
**19,479 / 19,642 consultations/s** ; p95 VM **44 / 29 ms** et Docker
**20,25 / 20 ms** (deux séries). Les quatre questions sont traitées dans l'ordre.
**Saturation non atteinte jusqu'à vingt utilisateurs ; aucun goulot démontré.**
La charge de saturation et le premier composant limitant restent indéterminés ;
les mesures ne permettent pas de conclure sur la capacité maximale. Le p95 VM
varie de **34,09 %** entre les deux séries au palier 20, au-delà du repère de
répétabilité de 10 % ; le rapport conserve et discute cet écart.

Détail : [source du rapport](mesure/docs/rapport-charge.md)
· [calculs vérifiables](mesure/resultats/etape18/analyse.json)
· [reproduction](mesure/ETAPE18.md).

## Points ouverts pour le rendu

| Étape | Point à compléter ou limite à présenter |
| --- | --- |
| 2, 5, 6 | Confirmer l'accès lecture, parcourir le Figma, vérifier la conformité visuelle et consigner l'approbation du jalon. |
| 6 | Vérifier l'installation locale du README sur une VM vierge. |
| 7 | Modèle issu d’une OVA officielle ; la consigne demandait la machine du TP 1. |
| 10 | Joindre séparément les trois OVA et `SHA256SUMS` ; le démarrage après réimportation reste non testé. |
| 13 | La capture des services est issue de Podman ; les preuves Docker Engine sont distinctes. |
| 14 | Temps humain initial non chronométré ; comparaison de configurations dont plusieurs paramètres diffèrent. |
| 17 | Campagnes complètes, mais interruption/reprise : continuité de séance et effet de l'ordre imparfaitement contrôlés. |
| 18 | Saturation et goulot non déterminés ; prolonger la charge après réétalonnage. Variation du p95 VM de 34,09 % au palier 20, à examiner pour la répétabilité. |
