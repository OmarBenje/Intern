# Lot 26 — Résolution des liens publics et preuves persistantes

## Objectif
Examiner les 26 groupes ambigus du lot 25, conserver les liens et références
attribuables aux annonces, puis réévaluer les fusions avec les protections du lot 25.

## Collecte bornée
La commande resolve_duplicate_links lit les title_only_groups du rapport :
1 à 200 offres, uniquement leurs sources fraîches. Les sources ATS reconnues
conservent leur identité déjà stockée sans nouvelle requête. Les autres sources
sont lues séquentiellement via le transport HTTPS public existant : validation
DNS et des redirections, adresses publiques, connexion épinglée, limite de taille
et délai total de 15 secondes par page. Une erreur d'accès suspend les autres
lectures du même hôte pour ce passage. Aucun contournement ni authentification.

Un seul JobPosting JSON-LD doit correspondre exactement au titre et à l'employeur
après normalisation de casse et espaces. Seuls ses champs url/applicationUrl/
application_url peuvent fournir un lien spécifique ; les ancres arbitraires et
offres recommandées sont exclues. Les titres reformulés ou entreprises aliasées
restent donc non résolus dans ce lot. Une référence identifier est conservée
avec son namespace mais ne permet jamais à elle seule une fusion.

## Persistance et consommation
DiscoveryResult, provider job_link_evidence, contient le dernier état de chaque
source, son empreinte, liens, références, méthode, URL finale, hash de page et
horodatage. La DiscoveryQuery associée est désactivée ; aucun worker récurrent
n'est ajouté. Le rapport JSONL est écrit au fil du passage ; un chemin déjà
existant est refusé pour préserver les rapports précédents. Pas de HTML intégral.

Les preuves resolved de moins de sept jours sont ajoutées à l'identité utilisée
par propose_targeted et rechargées par validate_pair avant la fusion sous verrou.
Un changement d'URL, apply_url, content_hash, titre ou employeur invalide la preuve.
Les liens participent à l'empreinte de décision : remplacement ou expiration
entre proposition et fusion bloque celle-ci. Les contrôles de contrat, lieu,
employeur, références contradictoires, fraîcheur et historique restent applicables.
Les imports futurs qui changent le contenu exigent donc une nouvelle résolution
explicite ; aucune preuve périmée n'est réutilisée silencieusement.

## Résultat observé le 1 octobre 2026
61 sources dans 26 groupes :
- 31 identités ATS déjà stockées, consignées sans récupération réseau nouvelle ;
- 20 sources WTTJ bloquées : premier échec public_http_error, puis hôte suspendu ;
- 10 pages sans JobPosting attribuable avec cette méthode (9 JobSpy/LinkedIn, 1 NAV).
Zéro nouveau lien employeur confirmé. Après réaudit des 262 fiches : zéro décision
de fusion, zéro fusion exécutée, 26 groupes toujours ambigus. Cela ne démontre ni
leur unicité ni l'absence de doublons. La limite principale reste l'accès aux pages
agrégateurs et l'attribution stricte des données publiques.

Rapports :
- research/2026-10-01-link-resolution.jsonl
- research/2026-10-01-link-resolution-dedup.json

## Validation
42 tests ciblés : nouvelle preuve ouvrant une fusion auparavant impossible et
annulation, rechargement sans prefetch, expiration, changement de contenu ou de
preuve, attribution ambiguë, ancres hors annonce, référence seule et suspension
d'hôte. Régression de la déduplication, collecte, couverture et imports incluse.
