# Lot 18 — couverture observée et déduplication

## Objectif

Rendre visibles les lacunes de collecte et compter le catalogue effectivement
publiable, sans assimiler le nombre de résultats source au nombre de stages
uniques en Europe. Page `/engine`, accessible par « Moteur » dans la navigation.

## Contrat des métriques

`GET /api/v1/coverage/` conserve les champs précédents et ajoute :
`measured_at`, `published_offers`, `providers`, `deduplication`, `counting_note`.
Le total utilise exactement `open_offers()` : stage confirmé, Europe, statut
ouvert, expiration et fraîcheur. Il compte des identifiants canoniques distincts,
pas une estimation des stages de tout le marché. Des doublons résiduels restent
possibles. Par fournisseur, seules les sources fraîches contribuent ; une offre
multisource ou multipays peut contribuer à plusieurs lignes, donc pas de somme.

États des recherches : désactivée, en cours (lease actif), erreur, plafond atteint,
en retard (échéance dépassée de plus d’une heure), pages restantes, cycle terminé,
non démarrée. Un cycle terminé signifie seulement que la recherche configurée
n’a plus de curseur après un succès. Les compteurs de découverte sont distingués
par provider ; ils peuvent ne publier aucune offre directement.

Les schedules d’ATS exposent les suspensions, erreurs et retards. Les boards des
collecteurs par requête ne sont pas considérés en retard à cause de leur schedule
ATS inutilisé. `partial_snapshot` est une collecte partielle attendue, pas une
panne. Le tableau affiche les codes d’erreurs agrégés, sans contenu privé.

`audit_coverage` produit le même bilan plus les curseurs et dates par requête en
JSON pour l’exploitation. Aucun pourcentage d’exhaustivité n’est calculé.

## Déduplication conservatrice

`reconcile_offer_duplicates --links` parcourt les offres publiables et propose des
rapprochements interboards avec même entreprise, titre, description complète,
contrat, mode de travail, expiration et lieux. Les sources doivent partager un
lien de fiche ou candidature. Seuls les paramètres `utm_*`, `gclid`, `fbclid` sont
retirés ; les paramètres d’identité sont conservés. Les pages carrières génériques
ne prouvent pas une identité. Les descriptions de moins de 100 caractères et
les références de recrutement contradictoires ne produisent pas de proposition.

Fusion explicite avec la commande existante `--merge ID`, après inspection des
preuves. Les données sont revalidées sous verrou. Les dossiers de candidature
liés bloquent la fusion ; sources déplacées et ancien statut sont journalisés.
L’ancien identifiant reste résolvable via l’alias existant. `--reverse ID` conserve
la possibilité de revenir en arrière si aucune nouvelle histoire liée ne l’empêche.
Aucune fusion par titre seul, aucun effacement d’offre, aucune fusion forcée.

## Correction issue de l’audit

Deux requêtes Bundesagentur échouaient sur des références valides contenant un
point, par exemple `14551-k28417.429-S`. La validation autorise maintenant ce
caractère tout en gardant un identifiant commençant par un caractère alphanumérique,
sans slash ni encodage arbitraire. Les reprises conservent les pages bloquées.
Les autres erreurs de source et pauses manuelles ne sont pas annulées.

## Validation et limites

Tests du comptage (expiration/fraîcheur), des états, des liens avec suivi, conflits
de références et dates, revalidation et réversibilité. Tests navigateur sur desktop,
mobile et erreur API. Les tables mobiles gardent toutes leurs colonnes dans une
zone à défilement horizontal accessible au clavier.

Le scan réel n’a trouvé aucun rapprochement répondant à toutes les preuves :
aucune fusion n’a donc été effectuée. Ce résultat n’établit pas l’absence de
doublons. Il faudra collecter davantage de liens employeur canoniques et examiner
les variantes de contenu avant de pouvoir fusionner plus largement sans risque.

Les collectes ne sont pas toutes terminées : les plafonds LinkedIn/JobSpy, les
limitations de débit et certaines sources suspendues restent visibles. L’audit
est un instantané ; les workers continuent à parcourir les pages disponibles.

Résultats : 353 tests backend réussis, 7 tests ciblés revérifiés après durcissement
de la conservation des fragments et paramètres d’URL, build frontend réussi,
2 tests Playwright desktop/mobile/erreur réussis. Backend et frontend répondent.
Le rapport du 1er octobre à 00:44 heure de Paris compte 2 401 fiches publiables ;
ce volume évolue avec les workers. Il expose encore des erreurs JobSpy, LinkedIn,
SmartRecruiters et WTTJ. Les deux recherches Bundesagentur corrigées ont avancé
sans erreur. Le scan de déduplication ne démontre pas l’unicité de toutes les fiches.
