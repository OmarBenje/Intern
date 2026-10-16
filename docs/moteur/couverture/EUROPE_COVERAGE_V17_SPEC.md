# Lot 24 — Découverte guidée par les stages publiés

## Objectif
Vérifier 50 pistes ATS chez des employeurs déjà présents dans les stages européens
publiables. Augmenter la pertinence de l'échantillon plutôt que parcourir le
registre uniquement dans l'ordre des IDs.

## Preuves et sélection
`discover_ats_from_offers --limit 50 --registry --report fichier.json`
considère uniquement les sources fraîches d'offres publiables (limite 20 000).
D'abord : liens origine, candidature, direct_url et liens ATS des descriptions.
Ensuite, si demandé : nom d'employeur exact (casse et espaces externes ignorés)
dans l'inventaire public ats-scrapers épinglé. Pas de recherche floue ni d'URL
fabriquée à partir du nom. Une correspondance nominale est une piste, pas une
preuve d'identité d'entreprise ; les liens de description restent aussi des pistes.

Le premier pilote a produit 3 pistes par lien et 47 par nom dans le registre.
Les pages WTTJ interrogées ont refusé la lecture HTML et leur index public
consulté n'expose pas de lien employeur : aucune extraction fictive revendiquée.

## Déduplication et persistance
Normalisation des URL d'annonces vers les boards reconnus. Vérification du schéma,
des credentials et du port avant suppression des paramètres. Les URL de boards
connus (y compris variantes de casse de clé) sont exclues. Les probes existants
conservent état, arrêt opérateur et backoff. Pas de réactivation forcée.
DiscoveryResult conserve offre, source, URL observée, méthode et provenance/hash
CSV pour chaque piste. AtsProbe assure l'exécution durable du lot 23.
`run_ats_probe_worker --probe-ids … --once --limit 50` cible un lot sans consommer
les entrées d'un autre. Cette sélection conserve les baux transactionnels.

## Publication et contrôle
Un stage européen confirmé reste requis avant activation. Les budgets réseau,
qualification, attente à sept jours et backoff restent ceux du lot 23. Le nom
du registre n'est pas présenté comme une validation indépendante de l'identité.
Tout conflit d'identité observé est mis à l'écart avant le bilan final.
Les fiches ajoutées peuvent doubler des annonces présentes sur les agrégateurs ;
les compteurs ne représentent pas des stages uniques.

## Validation
29 tests ciblés passent : URL sûres, chemins d'annonces, exclusion des sources
connues et non publiables, correspondance exacte et provenance, idempotence,
arrêt opérateur pendant la vérification, ciblage d'un batch et suite du lot 23.
Aucun changement d'interface requis : rendement présent dans /engine.

## Résultat réel — 1 octobre 2026
50 pistes testées : 20 actives, 27 en attente, 2 erreurs HTTP (iBanFirst, Lifen),
1 arrêt pour identité contradictoire. 262 nouvelles fiches encore visibles après
contrôle, dont 153 sur le portail Richemont. Le libellé employeur de ce portail
a été corrigé en « Richemont (groupe) » : le lien venait d'une annonce Lange,
mais le portail contient les stages du groupe. Les descriptions Workday confirment
le groupe ; ne pas attribuer l'ensemble des annonces à cette seule filiale.

Le board artefactjobs affiche « Welcome to the Jungle » dans sa métadonnée name
mais décrit Artefact dans son contenu public : désactivé, 11 fiches exclues du
bilan. Les réponses et IDs initiaux sont conservés dans les rapports ; le bilan
après vérification fait foi (`2026-10-01-offer-led-results.json`).

La fiche 11284 est proposée à Londres et Chicago : elle est éligible via Londres,
les deux lieux restent conservés. Les totaux pays se recouvrent. Le scan de
rapprochement conservateur par liens n'a proposé aucune fusion certaine ; cela
ne démontre pas l'absence de doublons. Pas de gain « unique » revendiqué.
29 tests ciblés passent ; 9 tests de la file repassés après correction finale.
Worker de vérification relancé avec le respect de l'arrêt opérateur pendant
une tentative. Aucun rebuild Compose effectué.
