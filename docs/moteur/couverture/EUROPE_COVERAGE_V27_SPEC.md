# Couverture V27 — Reprise des collectes Eightfold interrompues

## Constat
Microsoft a retourné une fiche belge puis HTTP429 sur le stage de Bucarest
1970393557007677. Les collectes suivantes recommençaient à la première page.
Une erreur de recherche après plusieurs pages pouvait aussi faire perdre les
résultats déjà récupérés pendant le passage.

## Contrat
- Point de reprise JSON sur BoardSchedule, limité à Eightfold dans ce lot.
- Version, portail, date de début, index de recherche/page, identifiants déjà
  examinés et jusqu'à dix détails en attente. Aucun URL fourni par ce point.
- Reprendre les détails de la page sauvegardée, puis les pages restantes.
- Sauvegarder les offres et la progression dans la même transaction, protégée
  par le bail existant ; un échec de transaction ne consomme pas la progression.
- Préserver les lignes déjà valides lors d'une erreur de recherche ou d'un délai
  dépassé. Le détail interrompu reste en tête de file sur erreur transitoire.
- Respecter Retry-After même sur résultat partiel. Conserver le rythme normal
  lorsqu'il impose un délai plus long ; aucune boucle de réessais immédiate.
- Repartir du début après un parcours terminé, une structure invalide, un autre
  portail ou 24 heures. Les résultats restent toujours partiels : aucune clôture
  d'offre sur absence. Pagination mobile : doublons ignorés entre pages ; un
  prochain parcours complet de recherche réduit les omissions dues aux décalages.
- Maintenir les critères stage/Europe, les budgets et les hôtes autorisés.

## Validation
Tester interruption en détail et en recherche, progression persistée, absence de
fermeture, bail perdu, Retry-After, expiration/identité du checkpoint et
idempotence. Comparer avant/après les fiches publiables pour Microsoft, NVIDIA
et Dolby. N'exécuter que les sources dues et sans bail ; documenter les blocages
restants. Exports dans docs/research/generated/, ignoré par Git.
