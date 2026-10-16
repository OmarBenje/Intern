# Lot 31 — Rappel des trois portails en attente

## Diagnostic du 1 octobre 2026
- Plum : widget public HTTP 200, 29 lignes, aucun titre de stage. Le stage Wealth
  Ops repéré dans l'index n'est plus dans ce flux. Aucune perte démontrée ; ne pas
  republier une annonce sur la seule foi du moteur de recherche.
- Gen Digital : API publique HTTP 200, 121 annonces ; deux stages à Kuala Lumpur.
  La référence marketing à Prague n'est plus listée. Le rejet Europe est correct.
- Civitta : API publique HTTP 200, 74 annonces ; Internship toujours listé, lieu
  générique « All Civitta locations », pays structuré nul. La description dit
  explicitement que ce poste est ouvert dans une liste de pays. Perte démontrée.

## Correction bornée
Dans l'adaptateur Lever seulement, quand l'unique lieu est « All … locations »,
reconnaître une ligne entière « This position/role is open across [même lieu]: »
suivie d'une liste de noms de pays connus. Correspondance exacte de chaque pays,
aucun bureau inféré depuis la présentation de l'entreprise. Si un élément est
inconnu, plusieurs phrases contradictoires ou lieu structuré différent : ne pas
compléter. Conserver tous les pays de la liste, y compris hors Europe, et une
preuve littérale dans le payload source. Une seule annonce multi-pays, pas une
copie par pays. Une offre disponible en Europe et ailleurs reste admissible selon
la politique existante ; les lieux hors Europe ne doivent pas être cachés.

Préserver le signal Lever workplaceType=remote : les offres à distance restent
non publiables sans preuve de résidence selon la politique actuelle. Pas de
changement des règles de classification du stage, de pagination, ni de migration.

## Vérification
Fixture publique Civitta réduite aux champs utiles ; tests des cas entreprise,
négation, pays inconnus, lieu différent, pays hors Europe, remote et idempotence
d'import. Régressions Plum/Gen sur leur instantané public. Rapports SHA256 des
réponses et diagnostics avant/après. Reprise anticipée de Civitta uniquement si
la probe est en attente et sans bail actif ; délais des deux autres inchangés.

## Bilan exécuté

48 tests ciblés passent, lint/Django/diff vérifiés. Civitta réactivé après reprise
ciblée : une fiche nouvelle (16033), 23 lieux explicitement annoncés dont 19 pays
européens. Aucun doublon certain proposé ; aucune fusion. Les pays hors Europe
restent dans les lieux source, sans démultiplier la fiche. Le pays structuré Lever,
s'il est renseigné, bloque ce fallback textuel.

Plum et Gen restent en attente avec leurs dates de reprise inchangées. Absence du
flux actuel n'est pas une preuve de clôture définitive : conserver la surveillance.
Rapports `2026-10-01-recall-three-{diagnostic,pilot,results}.json` dans research.
Deux workers locaux rechargés ; les baux antérieurs sont conservés pour reprise
à expiration. Readiness HTTP 200. Pas de changement de modèle ni d'interface.
