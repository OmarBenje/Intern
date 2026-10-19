# Audit de l’arrêt du comparatif VM du 19 octobre 2026

Campagne : `worker-vm-20261019-121536-124124`. Incident INC-17.
Les preuves d’origine restent inchangées et le statut reste `failed`.
[Résultats et rapport initial](resultats/worker-vm-20261019-121536-124124/rapport-workers.md).
[Rejeu et inventaire de l’audit](audits/worker-vm-20261019-121536-124124.json).

## Cause confirmée

L’étalonnage statique à 180 utilisateurs, seconde série avec 4 workers, a
produit 100 948 requêtes dans la fenêtre stable, 1 682,47 requêtes réussies/s,
aucune erreur et un p95 de 116 ms. Le débit minimum demandé était 360 req/s.
L’arrêt ne démontre donc pas une insuffisance du débit Nginx.

Le vérificateur évaluait l’activité de chaque utilisateur uniquement à partir
des requêtes entièrement contenues dans la fenêtre. Quatre requêtes commencées
avant sa fin se terminaient après cette borne : leurs durées sont 5 488,
5 386, 5 513 et 5 550 ms. Les dernières réponses entièrement contenues étaient
respectivement à 5 291, 5 294, 5 218 et 5 148 ms de la borne. Le seuil de
présence étant de 5 s, ces utilisateurs étaient déclarés partis trop tôt.
Les requêtes traversant la borne prouvent qu’ils étaient encore actifs.
C’est un faux diagnostic de départ ; les requêtes lentes sont réelles.
Leur cause n’est pas établie par les fichiers disponibles.

Le message `Static injector/proxy headroom insufficient` regroupait plateau
invalide, erreurs et débit insuffisant sans distinguer ces motifs. De plus,
`calibration.log` était écrasé à chaque étalonnage, réduisant le diagnostic
console aux dernières opérations. Ces deux défauts sont corrigés.

## Recherche d’autres erreurs

- 11 journaux Java JMeter, 54 journaux de collecteurs et 3 journaux de
  conteneurs archivés inspectés : aucun niveau WARN/ERROR/CRITICAL/FATAL.
  La ligne INFO `Thread will stop on error` décrit une configuration, pas un échec.
- Les 5 essais applicatifs et les 6 étalonnages ont zéro erreur JMeter.
- 738 relevés serveur lisibles, aucune ligne JSON invalide et aucun relevé
  avec événement OOM positif. Aucun fichier `arret-securite.json`.
- Une seule erreur de commande archivée : timeout SSH de 10 s sur vm-proxy
  au démarrage, suivi d’une connexion réussie. Ce diagnostic ancien apparaît
  dans `last-error.txt` ; il n’est pas la cause de l’arrêt d’étalonnage.
- Les journaux VirtualBox des trois VM ne montrent pas de crash ou d’erreur
  disque dans la session inspectée. Les compteurs `VERR_TIMEOUT` sont à zéro ;
  les messages de terminaison correspondent à l’arrêt. Le proxy signale un
  repli DNS libslirp au démarrage, sans preuve de lien avec cet incident.
- Le journal confirme la restauration des trois politiques de mises à jour,
  puis `reference_restored`. L’état courant des services est vérifié séparément
  avant une nouvelle campagne.

Limite de cet audit : les journaux systemd invités n’avaient pas été archivés
par cette campagne et les VM sont arrêtées. Les journaux de conteneurs archivés
couvrent la préparation Docker, pas le processus Django invité. Il n’est donc
pas possible d’exclure tout événement interne aux invités à partir de ces seules
traces. Leur archivage avant restauration est ajouté pour les nouveaux tests.

Les dépassements applicatifs à 180 utilisateurs restent des résultats réels :
p95 1 307 ms avec 2 workers et 1 008 ms avec 4 workers dans la première série.
Ils justifient l’annulation des paliers à 200 selon le seuil choisi de 1 s.
La correction ne les transforme pas en paliers acceptables.

## Comportement corrigé

1. Vérifier la présence avec les requêtes chevauchant les bornes. Conserver
   le maximum brut des durées et le nombre de requêtes de bord ; le p95 reste
   celui des requêtes entièrement contenues dans la fenêtre.
2. Versionner cette règle dans `configuration.json`. Les anciennes synthèses
   sont encore vérifiées avec l’ancienne règle ; aucune preuve n’est réécrite.
3. Afficher les motifs précis de rejet et archiver `rejet.json` ainsi qu’un
   journal console privé par tentative.
4. Dans le comparatif de workers, réessayer un étalonnage terminé mais refusé
   une seule fois après retour vérifié au repos. Après deux refus, annuler le
   palier et les charges supérieures de ce bloc, puis continuer les autres blocs.
   Les tentatives refusées et les charges annulées restent dans le manifeste,
   le journal, le statut et le rapport ; les mesures manquantes restent non concluantes.
5. Garder les arrêts mémoire/OOM, disponibilité, collecteurs, lancement et repos
   non validé. Les erreurs de sécurité ne sont pas absorbées par les nouvelles tentatives.
6. Archiver les journaux systemd invités dans le runtime privé avant nettoyage,
   si SSH est disponible. Un défaut d’archivage est signalé sans empêcher la restauration.

## Vérification

Le rejeu local du CSV original avec la règle corrigée reconnaît le plateau comme
valide, avec les mêmes 100 948 requêtes, le même débit et le même p95. Il conserve
un maximum brut de 5 550 ms et compte 357 requêtes chevauchant une des bornes
(incluant les requêtes rapides de bord). Ce rejeu ne constitue pas une nouvelle
mesure et ne complète pas les répétitions manquantes.

Tests : requête traversant la borne, vrai départ malgré un retour après la
fenêtre, requête traversant le début, nouvelle tentative après repos, conservation
des deux chemins, épuisement après deux refus, poursuite des autres blocs,
propagation des erreurs de sécurité et restauration malgré un défaut d’archivage.
