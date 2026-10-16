# Lot 19 — reprises des collecteurs

## Objectif

Débloquer WTTJ, fiabiliser les snapshots SmartRecruiters, distinguer les erreurs
Indeed des vrais résultats vides et ralentir les recherches LinkedIn lorsqu’elles
rencontrent une limitation. La qualification stage/Europe reste inchangée.

## Changements

### WTTJ

Le slug public `backbone.consulting` était refusé par une expression régulière
limitée aux lettres, chiffres, tirets et underscores. Le point est désormais
accepté à l’intérieur des slugs. Slash, query string, encodage `%` et segments
commençant par un point restent refusés. L’hôte et le chemin sont toujours
construits par le connecteur. Le curseur existant est conservé pour reprise.

### SmartRecruiters

Une variation de `totalFound` entre deux pages n’annule plus toutes les fiches
vérifiées : la pagination continue avec le nouveau total et le snapshot est
explicitement partiel. Un identifiant répété sur deux pages est traité une seule
fois, avec diagnostic et snapshot partiel. Les limites de temps, de volume et de
détails restent identiques. Identité du détail, contrat, pays et description
continuent d’être contrôlés. Les erreurs réseau restent des erreurs ; une liste
incomplète ne sert jamais à fermer les offres absentes. Le prochain cycle repart
au début : ce lot n’introduit pas de curseur durable pour les boards ATS.

### Indeed via JobSpy

Le processus isolé observe la réponse HTTP de l’adaptateur Indeed avant que la
bibliothèque puisse transformer une erreur en liste vide. Un statut autre que
200, une erreur GraphQL ou un schéma invalide produit un diagnostic explicite.
Une recherche vide n’est confirmée qu’après une réponse valide, sans résultat
et sans curseur suivant. Le parent reçoit une enveloppe contrôlée ; aucune réponse
amont ou coordonnée privée n’est ajoutée aux logs.

Une vraie fin vide termine le cycle. Une erreur conserve le curseur, le dernier
succès et les offres existantes. Une liste vide non confirmée reste une erreur.
Les délais Retry-After numériques sont transmis et respectés par la reprise.

### LinkedIn public

Un 429 applique un délai commun à toutes les requêtes `linkedin_public` actives,
au minimum une heure, avec backoff progressif et prise en compte du Retry-After
numérique. Les échéances déjà plus éloignées sont conservées. Les autres providers
ne sont pas décalés. Aucun proxy, changement d’identité ou contournement d’accès.
Cette pause réduit les nouvelles requêtes ; elle ne prétend pas lever une restriction.

## Vérification

360 tests backend passent, dont les nouvelles régressions : slug contenant un
point, chemin interdit, catalogue changeant, pagination répétée, réponse Indeed
vide/429/invalide et cooldown LinkedIn partagé. Ruff valide les fichiers concernés.

Pilote WTTJ : 50 résultats traités, 39 importés, curseur de page 9 à page 10 dans
la même partition. Il s’agit d’imports, pas nécessairement d’ajouts uniques.
Indeed : `jobspy_upstream_http_error`, et non un succès vide. SmartRecruiters :
nouvel essai interrompu par timeout réseau (`upstream_invalid_response`), reprise
planifiée conservée. Une reprise partielle avait déjà réussi avant ce pilote ;
elle n’est pas attribuée à cette modification.

Workers locaux WTTJ, catalogue et JobSpy relancés avec le nouveau code. LinkedIn
mis en cooldown collectif sans nouvelle tentative forcée. Les pages restantes
continuent à être parcourues ; aucune exhaustivité n’est annoncée.
