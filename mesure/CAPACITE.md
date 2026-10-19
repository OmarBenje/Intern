# Recherche de capacité

Le [registre des incidents](INCIDENTS.md) décrit les erreurs observées, leurs
causes, les protections et les tests de non-régression. Chaque nouvel arrêt
intercepté conserve également un résumé `incident.json` dans ses résultats.

Depuis Intern, `bash outils/executer_etape.sh 17 capacite` prépare puis lance
une campagne réelle en arrière-plan. Elle utilise les prérequis Docker Engine,
VirtualBox, SSH et JMeter de l’étape 17 et réutilise son isolation/restauration.
Les bases de mesure sont dédiées ; les bases de référence sont conservées.
Pendant la préparation du snapshot, seuls PostgreSQL et l’API Docker démarrent.
Le conteneur proxy est créé à l’arrêt pour copier les fichiers : il ne réserve
pas le port 8081 encore utilisé par la VM. Le proxy Docker démarre seulement
pour les essais Docker, après l’arrêt des VM.
La recherche peut durer plusieurs heures. Elle n’a pas été exécutée lors de
l’ajout de ce code : aucune nouvelle capacité n’est encore démontrée.

```bash
bash outils/executer_etape.sh 17 capacite
bash outils/executer_etape.sh 17 statut
# Pour demander l’arrêt avec restauration :
bash outils/executer_etape.sh 17 arreter
# Une fois les deux séries terminées et les services restaurés :
bash outils/executer_etape.sh 18 capacite
```

Chaque lancement utilise de nouveaux dossiers `mesure/resultats/capacite-DATE-PID`
et `../.execution-campagnes/capacite-DATE-PID`. `CAPACITE_OUTPUT`,
`CAPACITE_RUNTIME` et `CAPACITE_PROTOCOL` permettent de choisir des chemins neufs
et un protocole différent. Le protocole est copié dans les résultats avant
les essais et vérifié par SHA-256. Une campagne interrompue ne reprend pas :
conserver ses preuves, corriger la cause et lancer une campagne neuve.
En fin de campagne, les conteneurs et réseaux Docker dédiés sont supprimés
avec `compose down`, sans suppression des volumes. Les bases sur volumes,
snapshots privés, JTL et relevés restent conservés. Cela évite que les réseaux
des campagnes successives épuisent les plages d’adresses Docker.
Les sorties des conteneurs sont archivées avant leur suppression sous
`container-logs/` du runtime. Les journaux Java ont un chemin distinct sous
`jmeter/` pour chaque essai, indiqué par `private_java_log` dans la configuration
du palier. Ils ne partagent plus un nom temporaire basé sur la seule charge.
Un échec d’archivage est signalé sans empêcher le nettoyage des services.
`CAPACITE_SOURCE` permet d’analyser une campagne autre que celle sélectionnée.
Les preuves canoniques `etape16`, `etape17`, `etape18` sont conservées.

Le protocole par défaut explore 1, 5, 10, 20, 40, 80, 160 et 320 utilisateurs.
La base initiale commune contient autant de candidats distincts que le palier
maximal, chacun avec sa candidature. Le CSV effectivement produit par Django,
avec les vrais identifiants de candidatures, accompagne les résultats.
La base est restaurée avant chaque passage d’un déploiement.
Le scénario et les assertions de session/contenu restent actifs, avec 1 s de
réflexion, 30 s de montée, 15 s de stabilisation et 120 s de plateau.
Tous les utilisateurs doivent couvrir la fenêtre stable ; un plateau incomplet
est refusé et ses raisons sont enregistrées.

Avant chaque charge nouvelle et pour chaque déploiement, un contrôle statique
Nginx à la même concurrence mesure la marge injecteur/réseau/proxy à l’étape 16.
Il doit réussir sans erreur, avec un débit au moins deux fois supérieur au
plafond applicatif de N consultations/s. Les CPU JMeter (100 % = un cœur) et
hôte, RSS, mémoire disponible, swap, pression mémoire et compteurs réseau sont
conservés dans `ressources.csv`. Les deux séries applicatives servent de
contrôles de répétabilité aux charges retenues. Si le CPU injecteur atteint
80 % d’un cœur ou le CPU hôte 90 % **en moyenne pondérée sur une fenêtre
continue de 10 s** du plateau applicatif, la recherche s’arrête sans conclure à une limite du déploiement. Ces seuils conservateurs
et la marge statique sont configurables avant la campagne. La durée est fixée
par `cpu_soutenu_s` ; les pics ponctuels restent enregistrés et ne déclenchent
pas seuls l’arrêt. Les relevés doivent couvrir toute la fenêtre sans trou de
plus de 5 s. Les protocoles archivés sans cette clé conservent leur règle
historique sur le maximum : leurs résultats et décisions ne sont pas modifiés.
Après un arrêt sous l’ancien protocole, utiliser `17 capacite` pour démarrer
une campagne neuve avec la nouvelle règle, sans reprendre les preuves partielles.
Le contrôle statique, sans réflexion, peut charger davantage l’hôte ; son CPU
est enregistré et n’est pas confondu avec celui des essais applicatifs.

La première série explore VM puis Docker, avec un seul déploiement actif.
Au premier refus (p95 > 1 s, erreurs stables > 1 %, ou plateau incomplet),
la montée s’arrête pour ce déploiement. Des points médians affinent ensuite
l’intervalle entre dernier palier acceptable et premier refusé jusqu’à un écart
d’au plus 10 utilisateurs (configurable). Chaque déploiement reçoit également
les points introduits par l’autre lorsqu’ils restent sous sa borne de refus.
Les charges comparables sont identiques ; les charges supérieures à une borne
refusée ne sont pas rejouées sur le déploiement déjà dégradé.
Les observations exploratoires au-delà de la borne affinée restent archivées.
La seconde série confirme les points jusqu’à cette borne dans l’ordre Docker
puis VM. Un refus plus précoce arrête la campagne et impose une nouvelle mesure.

Un repos vérifié après chaque étalonnage et essai exige le retour au repos
CPU/E/S/PostgreSQL et une réponse HTTP prête selon `repos_dynamique`.
Le contrôle HTTP de disponibilité attend jusqu’à 10 s par tentative, comme
les requêtes JMeter (`disponibilite_timeout_s`). Une réponse lente pendant
la montée ne suffit donc pas à déclarer le service indisponible après 2 s.
Cela ne modifie pas le seuil de service : le p95 doit toujours rester au plus
égal à 1 s sur les 120 s stables. Chaque contrôle conserve son statut HTTP,
sa durée et son éventuelle exception dans `disponibilite.jsonl` ; le dernier
échec accompagne `arret-securite.json`. Les protocoles archivés sans cette
clé conservent le délai historique de 2 s.
Un service indisponible sur trois contrôles successifs, un collecteur arrêté,
un événement OOM, moins de 10 % ou de 512 Mio de mémoire hôte
disponible, ou une pression mémoire supérieure à 10 % interrompt la montée.
Avec `swap_avec_pression_uniquement: true`, les échanges avec le swap sont
toujours enregistrés mais ne provoquent pas seuls un arrêt : ils accompagnent
un diagnostic de mémoire insuffisante, d’OOM ou de pression PSI excessive.
Cette règle s’applique à l’étalonnage, au pilote applicatif et à la vérification
des relevés. Sans cette clé, ou avec `false`, un protocole archivé conserve
sa règle stricte d’arrêt à la moindre activité swap. Le nouveau protocole doit
être figé dans une campagne neuve ; les anciens résultats restent inchangés.
Ce choix de protocole distingue l’activité swap de la contention :
[zram conserve des pages compressées en RAM](https://docs.kernel.org/admin-guide/blockdev/zram.html),
et [PSI mesure le temps perdu à attendre une ressource](https://docs.kernel.org/accounting/psi.html).
Les seuils de mémoire disponible et de PSI sont nos choix conservateurs,
pas des valeurs prescrites par la documentation du noyau. La présence de zram
ne suffit pas non plus à démontrer l’absence de contention.
Le palier partiel est conservé. Un collecteur qui perd le PID surveillé
arrête la campagne : un redémarrage de service ne doit pas être masqué par un
rattachement silencieux à un autre PID. Le fichier `collecteurs-echec.json`
identifie le service et le code de sortie ; ses diagnostics privés restent
séparés par palier et repos dans `collecteurs/` sous le runtime. `17 statut`
affiche ces diagnostics et indique si la restauration est confirmée.
Le contrôleur tente la restauration des
services de référence même si une étape de nettoyage des VM échoue.

L’étape 18 recalcule les JTL, vérifie les configurations, l’ordre, les bases,
l’étalonnage et les repos. Elle produit dans `analyse/` :

- `capacite.json` : bornes, répétabilité et relevés serveur aux signaux de saturation ;
- `erreurs-par-requete.csv` : erreurs totales et stables pour chaque requête ;
- `debit`, `p95`, `erreurs` en PNG/SVG, avec les deux séries séparées ;
- `rapport.md`, `rapport.pdf` et les empreintes `SHA256SUMS`.

Une divergence symétrique de plus de 10 % sur le débit réussi ou le p95
empêche de retenir une capacité. Le plus grand palier acceptable doit respecter
les seuils dans les deux séries. Sans refus, le rapport annonce seulement
« au moins N utilisateurs testés, limite non atteinte » et demande une nouvelle
exploration plus haute avec assez de comptes et un nouvel étalonnage.
Pour prolonger l’exploration, copier `protocole-capacite.json`, ajouter les
charges supérieures et définir `CAPACITE_PROTOCOL` avant un nouveau lancement.

Le signal de saturation est évalué séparément des seuils de service : variation
absolue de débit réussi d’au plus 5 % et hausse de p95 d’au moins 10 % entre deux
charges, reproduites dans les deux séries. Le rapport joint les CPU, mémoires,
E/S et connexions PostgreSQL correspondants. La cause reste à établir par
interprétation de ces relevés ; un CPU élevé seul ne démontre pas un goulot.
La capacité dépend du scénario, du temps de réflexion, des données et des
ressources allouées ; elle ne représente pas un nombre de comptes inscrits.

## Reprise d’une campagne interrompue au contrôle de l’injecteur

```bash
bash outils/executer_etape.sh 17 reprendre
bash outils/executer_etape.sh 17 statut
```

La reprise utilise la campagne sélectionnée, sans reconstruire les images ni
rejouer les paliers déjà enregistrés. Elle est limitée à un dernier palier
complet rejeté par le garde-fou de l’injecteur. Le contrôleur doit être arrêté,
les VM éteintes et le verrou mesure/maintenance disponible. Les empreintes du
snapshot SQL, des sources, du plan et des comptes sont vérifiées ; les images
Docker sont fixées à leurs identifiants initiaux et leurs allocations contrôlées.

Le dernier palier est rejoué après restauration de la même base initiale,
vérification du repos et nouvel étalonnage. La recherche adaptative reprend
ensuite ; les confirmations de seconde série restent nécessaires. Une panne
applicative ou une pression mémoire ne sont pas transformées en succès.

Le répertoire `reprises/<identifiant>/` conserve le manifeste, le journal, le
protocole initial et les mesures remplacées. Les anciens journaux Java sont
conservés dans le même sous-répertoire du runtime privé. Le journal principal
reste intégral et le manifeste contient `resumptions`. Il s’agit d’une campagne
interrompue puis reprise, à signaler dans l’analyse, avec un risque de variation
de l’état de l’hôte entre les deux sessions.

L’amendement enregistré à la reprise corrige l’unité du garde-fou CPU : la
mesure brute JMeter exprime 100 % pour un cœur, alors que le seuil de 80 % est
appliqué à la capacité CPU accessible au processus. Le nombre de cœurs tient
compte de l’affinité et des quotas cgroup des ancêtres. Les valeurs brutes ne
changent pas. Le seuil CPU hôte, les contrôles mémoire, le scénario, les durées,
les seuils p95/erreurs et la marge d’étalonnage restent identiques. Le vérificateur
n’accepte les empreintes historiques que si le protocole archivé diffère
uniquement par ce facteur de conversion CPU.
