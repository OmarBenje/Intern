# Lot 29 — Facettes Workday personnalisées et collecte de secours

## Diagnostic et périmètre
Retester les 11 probes du lot 27 en erreur country_facets_unavailable.
Le diagnostic public du 1 octobre distingue paramètres pays personnalisés,
absence de filtre pays, portails hors Europe et réponse vide. Les URLs répondent
en HTTP 200 : une erreur de facette ne signifie pas que le portail est inaccessible.
Le portail cswg appartient à C&S Wholesale Grocers, pas à l'employeur CS du
catalogue français ; arrêter cette piste plutôt que l'activer sur un homonyme.

## Connecteur
Reconnaître les paramètres traditionnels ou les paramètres sûrs explicitement
étiquetés Country, Country/Region, Location Country, Location Country / Territory.
Les IDs sont lus dans la réponse propre à chaque employeur, jamais inventés.
Les pays restent vérifiés dans chaque fiche détaillée ; aucune inférence depuis
la facette ou depuis une ville seule.

Sans partition européenne exploitable, parcourir la liste globale avec un maximum
de 2000 annonces listées. Lire seulement les détails aux titres candidats.
Conserver les limites existantes : 600 secondes, 1800 requêtes, 80 Mio au total,
20 annonces par page, contrôle des chemins, doublons et changements de pagination.
Les critères stage/Europe rules-17 restent appliqués aux détails.

Le secours est toujours partiel (diagnostic country_facets_fallback), même si
la liste paraît entièrement parcourue. Il peut ajouter des fiches mais ne peut
déduire la disparition d'anciennes offres. Liste vide ou plafond atteint ne
prouve pas absence de stages. HTTP 429 interrompt le passage, Retry-After conservé
y compris après une page ou une fiche déjà lue ; aucun contournement ou authentification.

## Pilote
Vérifier les échéances et baux des 11 probes. Ne pas devancer un Retry-After :
les erreurs locales country_facets_unavailable sont replanifiées une seule fois
après correction du parseur, sans modifier les autres erreurs ni les baux. Les sources
vides restent planifiées, les erreurs gardent leur backoff. Rapport par source :
état, diagnostic, complétude, nouveaux IDs encore publiables, pays et exclusions.
Aucun gain d'offres promis avant contrôle ; doublons interplateformes possibles.

## Résultat réel — 1 octobre 2026
Les 11 pistes sont traitées : sept portails actifs, trois en attente de
revérification (DLA Piper, Mars, RSM), un arrêté pour conflit d'identité (CS).
Plus aucune des onze pistes n'est en erreur country_facets_unavailable.

68 nouvelles fiches encore publiables : Barclays 28, HP 20, Murex 6, Roquette 5,
Expanscience 4, Salesforce 3, Pfizer 2. Répartition : GB 40, FR 13, DE 3,
BE/ES/IE/NL 2 chacun, AT/BG/DK/IT 1 chacun, soit 11 pays.
Catalogue observé de 7941 à 8009 au moment du bilan. Aucune unicité entre
plateformes démontrée. Les deux offres HP de même titre restent distinctes
lorsque leurs références employeur diffèrent.

Salesforce, HP, Pfizer et Roquette utilisent des facettes pays personnalisées
et leurs snapshots sont complets au sens du collecteur. Barclays, Murex et
Expanscience sont productifs via le secours, leurs snapshots restent partiels.
DLA Piper et RSM n'apportent aucun stage européen confirmé dans ce passage ;
Mars répond vide sur le portail du registre. Aucun de ces résultats ne prouve
l'absence de stages chez l'employeur ni l'exhaustivité des portails.

Les titres et pays des 68 fiches ont été contrôlés dans le rapport, sans nouvelle
exclusion nécessaire après les règles existantes. Réponses originales des facettes,
états avant reprise et résultats par source conservés dans research :
- 2026-10-01-workday-facets-diagnostic.json
- 2026-10-01-workday-recovery-before.json
- 2026-10-01-workday-recovery-pilot*.jsonl
- 2026-10-01-workday-recovery-results.json

Validation : 38 tests ciblés passent, couvrant facettes personnalisées, pagination
globale, exclusion des détails hors Europe, plafond, doublons, 429/Retry-After,
sources partielles, imports et file ATS. Pas de migration ni changement frontend.
