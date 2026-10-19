# Comparer 2 et 4 workers Gunicorn sur Docker ou les VM

## Choisir les paliers manuellement

Modifier `paliers_utilisateurs` dans `protocole-worker-vm.json` pour les VM,
ou dans `protocole-worker.json` pour Docker. Exemple :

```json
"paliers_utilisateurs": [80, 100, 130]
```

Choisir des entiers strictement positifs, distincts et dans l’ordre croissant.
Puis lancer `17 worker-vm` ou `17 worker`. Le nombre attendu de paliers et le
rapport utilisent cette liste : trois charges donnent au maximum douze essais
(trois charges × deux configurations × deux répétitions). La campagne copie le
protocole ; modifier le fichier source ne change pas une campagne déjà préparée.
Les résultats antérieurs conservent leur protocole et leurs mesures.

Depuis Intern :

```bash
bash outils/executer_etape.sh 17 worker
bash outils/executer_etape.sh 17 statut
```

Pour tester les VM à la place de Docker :

```bash
bash outils/executer_etape.sh 17 worker-vm
bash outils/executer_etape.sh 17 statut
```

Cette action crée des dossiers distincts `worker-vm-DATE`, démarre les trois VM,
prépare le service isolé `intern-mesure17` et compare 2 puis 4 workers, puis l’ordre
inverse, aux mêmes charges. Le service habituel `intern` conserve sa configuration.
La commande Gunicorn effective, le nombre de processus workers et les ressources
VM sont vérifiés avant chaque bloc. Les sources et la base proviennent du même
instantané. Les protections contre les mises à jour des VM et la restauration
des services sont celles de la campagne de capacité.

Sur VM, après un palier refusé, les charges supérieures de ce bloc sont annulées.
Le bloc suivant repart à 150 utilisateurs avec la base restaurée : cela permet
de comparer 4 workers même si 2 workers ne supportent pas les charges supérieures.
Le rapport signale les données manquantes et le statut affiche les charges
annulées. Les défauts de disponibilité, de collecte ou de ressources interrompent
la campagne avec restauration. Les VM sont arrêtées après cette restauration.

Le lancement crée une campagne distincte `mesure/resultats/worker-DATE/` et un
runtime privé dans `../.execution-campagnes/worker-DATE/`. Les résultats de capacité
existants sont conservés. Les VM doivent être arrêtées avant le lancement.

Avec `17 worker`, le contrôleur compare uniquement Docker : 2 puis 4 workers dans la première série,
4 puis 2 dans la seconde, à 150, 180 et 200 utilisateurs. Il conserve les mêmes
images et quotas, restaure la même base avant chaque bloc, vérifie le retour au
repos et étalonne le générateur pour chaque bloc et chaque charge. Chaque plateau
dure 120 s, après 30 s de montée et 15 s de stabilisation, avec 1 s de pause.
Prévoir environ une heure, davantage selon le temps de préparation et de repos.

La commande Gunicorn est remplacée uniquement dans le projet de mesure isolé.
La commande réellement configurée, les images et les quotas sont vérifiés et
archivés sans les variables d’environnement privées. Les services de référence
sont restaurés à la fin ou en cas d’échec. Un palier invalide, un dépassement de
seuil ou des erreurs annulent la suite ; les mesures déjà effectuées sont gardées.
Pour demander un arrêt propre : `bash outils/executer_etape.sh 17 arreter`.

Le rapport `rapport-workers.md` et le tableau `comparatif-workers.csv` sont produits
automatiquement dans le dossier de résultats, y compris après une interruption.
Les deux répétitions doivent respecter les seuils, ne pas contenir d’erreurs et
rester à moins de 10 % d’écart en débit et p95 pour être interprétées ensemble.
Un gain de débit répété avec 4 workers soutient l’hypothèse d’une limite liée aux
workers ; il faut aussi examiner le p95 et `serveurs.json` de chaque plateau.
L’absence de gain ne suffit pas à identifier une autre cause. Ce test ne remplace
pas une nouvelle campagne de capacité complète.

Les actions `18 capacite` et `17 reprendre` sont réservées aux campagnes de capacité,
pas à ce diagnostic. Un nouveau `17 worker` crée toujours une nouvelle campagne.

Un étalonnage terminé mais refusé est réessayé une seule fois après un repos
vérifié. Chaque tentative conserve ses données et son journal dans
`calibrations/BLOC/tentative-N/etalonnage/DEPLOIEMENT/CHARGE/` (journaux Java
et console dans le chemin correspondant du runtime privé). Après deux refus,
le palier courant et les charges supérieures du bloc sont annulés ; les autres
blocs continuent. Le rapport et `17 statut` affichent ces refus. Les arrêts
mémoire/OOM, les erreurs de collecteur, de lancement ou de disponibilité et
les repos non validés interrompent toujours la campagne avec restauration.

Le vérificateur version 2 reconnaît une requête chevauchant une borne comme
une preuve d’activité de l’utilisateur. Il conserve le maximum des temps de
réponse sur l’essai et le nombre de requêtes chevauchant les bornes. Le p95
reste calculé sur les requêtes entièrement contenues dans la fenêtre ; il
ne représente donc pas ces requêtes de bord. Un maximum d’étalonnage supérieur
à 5 s apparaît comme avertissement dans le rapport. Les anciennes synthèses
restent vérifiables selon la version d’origine, sans réécriture des preuves.
Les journaux systemd des VM sont archivés dans `vm-logs/` du runtime privé avant
restauration, quand SSH est disponible ; un échec d’archivage est signalé et
n’empêche pas la restauration.

Incident documenté : [audit du 19 octobre 2026](AUDIT-workers-vm-20261019.md).
