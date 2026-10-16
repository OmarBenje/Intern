# Lot 37 — Déduplication par contenu et lieux

## Problème vérifié
Joko « Campaign & CRM Intern » apparaissait quatre fois : Ashby 1/37 (description
identique) et WTTJ 16163/16303 (résumés presque identiques). Les publications ont
des identifiants distincts. Les lieux « Paris » et « Paris, FR » étaient comparés
littéralement. Le rapprochement résumé/description complète ne possède pas de
lien commun confirmé : la lecture publique WTTJ a échoué.

## Recommandations et choix
[Google JobPosting](https://developers.google.com/search/docs/appearance/structured-data/job-posting)
recommande une URL canonique pour plusieurs copies et décrit l'identifiant de
l'offre, l'employeur et les lieux. Cela ne prescrit pas d'algorithme de fusion.
Nos seuils ci-dessous sont des choix locaux, à surveiller sur les faux positifs.

Conserver les rapprochements existants par lien. Ajouter une passe automatique
sur le catalogue publiable, groupée par entreprise et titre normalisé :
- même entreprise en base, titre et ensemble de villes/pays ;
- suffixe ISO de pays ignoré uniquement s'il correspond au pays structuré ;
- contrats, modalités, échéances et références de recrutement compatibles ;
- descriptions d'au moins 80 mots, longueurs à moins de 5 %, nombres identiques ;
- contenu normalisé identique ou similarité SequenceMatcher ≥ 98 %.

Ne jamais fusionner automatiquement un résumé avec un texte complet. Pour le cas
signalé, les responsabilités et lieux ont été comparés manuellement ; les trois
copies rejoignent l'offre 1 par décisions réversibles, avec note de vérification.
« Ads Creative Intern » reste distinct.

## Exécution et sécurité
Passe dans le worker maintenance (maximum 100 fusions par passage). Pas de
requête réseau ni de similarité globale quadratique : comparaison par groupe.
La source ATS et le texte complet sont prioritaires. Chaque décision porte les
empreintes des deux offres, revérifiées sous verrou lors de la fusion.
Les sources sont conservées, les anciennes offres masquées, jamais supprimées.
Une candidature ou rémunération liée empêche la fusion ; les historiques ne sont
pas réécrits. Une décision annulée ne doit pas être réappliquée automatiquement.
Les nouvelles publications seront traitées au prochain passage maintenance.
Une source déjà déplacée continue à mettre à jour son offre canonique à l'import.

## Validation
Régressions : identifiants de publication distincts, réversibilité/idempotence,
pays différents, dates/chiffres différents, références contradictoires, résumé,
titre différent et empreinte modifiée. Vérification en base du cas Joko : quatre
sources sur une seule offre Campaign & CRM, Ads Creative conservée.

La comparaison tient également compte des external_id Workday : sur un même
board, deux références de recrutement différentes restent distinctes même avec
un texte identique (cas Sanofi observé pendant l'audit).
Validation exécutée : suite backend 545 tests passée ; dernier garde-fou Workday
validé avec les suites ciblées de déduplication et de runtime.
