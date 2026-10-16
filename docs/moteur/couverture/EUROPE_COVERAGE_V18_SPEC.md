# Lot 25 — Déduplication ciblée et réversible

## Périmètre
262 fiches du bilan après contrôle du lot 24, comparées au catalogue actuellement
publiable. Commande : `audit_offer_duplicates --input rapport-lot24.json --report audit.json`.
`--merge` applique seulement les décisions certaines encore valides.

## Preuves requises
Lien spécifique à une annonce commun aux deux fiches : ID de job dans le chemin,
UUID ATS, référence Workday dans le chemin ou gh_jid. Les paramètres inconnus et
identifiants restent conservés ; seuls les traceurs connus sont retirés. Un lien
vers une page carrière générique n'est pas une preuve. Les références employeur
contradictoires interdisent la fusion ; une référence seule sans lien commun ne
suffit pas dans ce lot, faute de namespace employeur vérifiable entre agrégateurs.

Employeur et titre égaux après normalisation légère de casse/espaces ; lieux
identiques ; pas de contradiction entre contrats, modalités ou expirations connus.
Les descriptions peuvent différer : cela permet un résumé d'agrégateur face à une
fiche employeur complète. La fiche conservée doit avoir une source ATS reconnue
et une description non vide. Les liens doivent encore disposer de sources fraîches.
Les correspondances de titre seules restent des groupes ambigus dans le rapport.

## Exécution et conservation
Empreintes des contenus, lieux et sources enregistrées lors de la proposition,
revérifiées sous verrou avant fusion. Les sources sont rattachées à la fiche
employeur, la fiche doublon est masquée (pas supprimée). Les historiques liés,
références contradictoires et chaînes de fusions bloquent l'opération. La route
historique vers le doublon utilise le mécanisme d'alias existant.
Annulation : `reconcile_offer_duplicates --reverse ID`, avec les protections
existantes contre le déplacement d'une source désormais liée à une candidature.

L'importeur peut actualiser le contenu depuis le board employeur conservé, malgré
la présence d'autres sources ; les résumés agrégateurs ne l'écrasent pas. L'API
ordonne les liens ATS avant les liens agrégateurs. Les autres sources restent
consultables. En cas d'annulation, l'autorité ajoutée par la fusion est retirée.

## Résultat réel
262 fiches examinées ; 26 groupes employeur/titre similaires, aucun lien commun
assez probant. Zéro fusion effectuée, zéro fiche supprimée du catalogue. Plusieurs
fausses correspondances par chemin URL étaient des annonces différentes chez
Burson, Symphony et Waymo : leur gh_jid distinct a été conservé. Le rapport
`research/2026-10-01-targeted-dedup-final.json` contient les IDs pour approfondir.
Aucun gain d'unicité ni absence de doublons revendiqué.

## Validation
35 tests ciblés passent : fusion avec descriptions et Company IDs différents,
conservation de la fiche employeur, annulation, actualisation après fusion,
priorité du lien ATS, modification des preuves, références contradictoires,
source périmée, lien générique et identifiants distincts. Import/collecte et
ancienne déduplication réversible couverts par la même suite.
