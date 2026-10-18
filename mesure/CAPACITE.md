# Recherche de capacité

Depuis Intern, `bash outils/executer_etape.sh 17 capacite` prépare puis lance
une campagne réelle en arrière-plan. Elle utilise les prérequis Docker Engine,
VirtualBox, SSH et JMeter de l’étape 17 et réutilise son isolation/restauration.
Les bases de mesure sont dédiées ; les bases de référence sont conservées.
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
80 % d’un cœur ou le CPU hôte 90 % sur le plateau applicatif, la recherche
s’arrête sans conclure à une limite du déploiement. Ces seuils conservateurs
et la marge statique sont configurables avant la campagne.
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
Un service indisponible sur trois contrôles successifs, un collecteur arrêté,
un événement OOM, du swap actif, moins de 10 % ou de 512 Mio de mémoire hôte
disponible, ou une pression mémoire supérieure à 10 % interrompt la montée.
Le palier partiel est conservé et le contrôleur tente la restauration des
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
