# Lot 30 — Découverte indépendante par pays

## Objectif
Découvrir des employeurs absents du catalogue sans partir des offres déjà en base.
Pilote sur FI, GR, CZ, BG et RO : respectivement 1, 1, 3, 3 et 5 fiches lors du
constat initial. Ce sont des marchés choisis parmi les moins couverts, pas un
classement exhaustif des pays européens (les pays à zéro existent aussi).

## Fonctionnement
Une recherche publique, en anglais et langues locales, produit un manifeste
revu par l'opérateur : employeur, pays témoin, URL d'annonce ATS, titre, court
extrait et date de revue. L'identité employeur est vérifiée dans la page source ;
le nom du registre seul ne suffit pas. La recherche web reste une étape éditoriale,
pas un crawler autonome ni une preuve de disponibilité actuelle.

La commande `discover_external_ats --input fichier.json --report nouveau.json`
prévisualise l'admission. `--apply` inscrit au maximum 100 portails dans AtsProbe.
Elle exige des preuves récentes (7 jours), un pays européen, un portail supporté,
et une preuve issue du même portail. Elle exclut employeurs et portails connus,
doublons du lot, identités contradictoires et probes existantes sans modifier
leurs délais, états ou arrêts. Validation complète du manifeste avant mutation.
Provenance persistée dans DiscoveryResult, requête désactivée. Pas de migration.

Les workers existants font la vérification actuelle stage/Europe, l'import et
la planification. Aucun assouplissement des critères. Les recherches peuvent
aboutir à moins de 100 pistes ; déclarer le déficit, les sources vides et erreurs.

## Validation et bilan
Tests : validation atomique, dry-run, idempotence, employeur connu, identité
contradictoire, preuve expirée, URL dangereuse, limite, conservation du backoff.
Pilote réel : capturer les IDs publiables avant admission ; rapporter uniquement
les nouveaux IDs visibles rattachés aux portails du lot, pays européens, états
et erreurs. Revue des titres et descriptions suspects ; pas de fusion sur titre
seul et aucune revendication d'unicité interplateformes.

## Résultat exécuté

Commande d'admission indépendante livrée, dry-run par défaut, tests de reprise et
identité inclus. 8 nouvelles pistes retenues (capacité 100), 5 actives et 3 en
attente. 114 nouvelles fiches visibles dans 11 pays ; cibles CZ +7, GR +5, RO +1,
FI/BG +0. Recherche web éditoriale, collecte récurrente via les workers existants.
24 tests ciblés passent, lint et vérification Django passent, backend readiness
HTTP 200. Rapports datés dans docs/research ; doublons possibles, aucune fusion
sur titre. Le rapport de recherche documente les limites de sélection du pilote.
