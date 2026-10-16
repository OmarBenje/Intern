# Couverture V28 — Exécution régulière et diagnostic des files

## Diagnostic du 1er octobre 2026
Le décompte initial de 1567 BoardSchedule échus était trompeur : les sources
synthétiques WTTJ/EURES/JobSpy/Jobtech/Bundesagentur/NAV sont alimentées par
DiscoveryQuery, pas par le worker ATS. Leurs échéances BoardSchedule ne mesurent
pas le retard réel de collecte. Seuls catalogue et probes tournaient localement.
Le catalogue exécutait un import par passage, attendait 30 secondes et partageait
sa boucle avec découverte, logos, alertes internes et liens privés.

## Livrables
- `collection_status` distingue imports ATS, requêtes par fournisseur, sondes,
  baux actifs, travaux prêts et âge du plus ancien travail prêt.
- Séparer les modes imports-only et maintenance-only du worker catalogue.
  Le mode par défaut reste compatible. Déployer les deux rôles séparément.
- En local, un superviseur unique par workspace démarre neuf rôles, journalise
  chaque processus, écrit un état et redémarre les sorties avec délai exponentiel
  de 5 à 300 secondes. Arrêt propagé seulement à ses propres groupes de processus.
- Imports ATS séquentiels par lots de 20, espace minimal de deux secondes entre
  imports, sommeil de deux secondes entre passages. Fournisseurs spécialisés
  séparés, chacun séquentiel avec ses baux, budgets et délais existants.
- Découverte et tâches annexes ne bloquent plus les imports ; l'ancienneté reste
  le critère de traitement pour ne pas affamer les nouvelles sources.
- Compose conserve ses workers spécialisés et son mécanisme de redémarrage ;
  ajouter un rôle maintenance séparé. Ne pas lancer le superviseur dans Compose.

## Limites et acceptation
Pas de multiplication de workers sur un même fournisseur, pas de réduction de
Retry-After, pas d'activation de requêtes désactivées. La reprise de pagination
reste celle de chaque connecteur ; le lot 34 couvre Eightfold. Ce lot ne crée pas
un limiteur de débit global partagé entre tous les processus.

Valider séparation des rôles, exclusion des sources synthétiques des compteurs
ATS, baux actifs, redémarrage d'un processus et verrou exclusif. Comparer les
vraies files avant/après exécution et conserver une synthèse courte. Ne pas
confondre une sortie de file sur erreur avec un import réussi. Vérifier les
processus et le backend en direct. La supervision locale dépend du processus
parent et ne constitue pas un démarrage automatique après redémarrage du PC.
