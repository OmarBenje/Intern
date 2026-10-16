# Couverture V7 — Welcome to the Jungle

## Périmètre
Collecte de l'index public WTTJ, contrat internship, tous métiers, pays européen
prouvé dans les bureaux rattachés à l'annonce. La qualification textuelle reste
obligatoire : alternance, emploi permanent et pays inconnu ne sont pas publiés.
Pas d'installation du paquet ats-scrapers, aucune dépendance ni migration.

## Contenu affiché
L'accès aux fiches HTML a échoué pendant l'étude. L'index fournit le résumé, les
missions et parfois le profil : seuls ces textes publiés par la source sont
repris, avec le préfixe visible « Résumé publié par Welcome to the Jungle ».
Une annonce sans contenu suffisant est exclue ; aucune description n'est inventée.
Le lien canonique renvoie vers la fiche publique WTTJ.

## Collecte bornée et reprise
- Index français trié par date, filtre contrat et pays ; 50 résultats par page.
- Un intervalle contenant plus de 1 000 résultats est divisé par date. Après sa
  partie récente, la collecte revient aux dates antérieures : pas de simple arrêt
  aux 1 000 premières annonces. Les bornes sont inclusives et disjointes.
- Curseur persistant lo:hi:page (<80 caractères). Maximum 12 recherches par passage,
  5 Mio/réponse, timeout HTTP 20 secondes et contrôle de budget 30 secondes/réponse.
- Une seconde contenant à elle seule plus de 1 000 annonces produit une erreur
  explicite ; elle n'est pas sautée silencieusement. Les compteurs approximatifs
  ou schémas inattendus sont refusés.
- Worker dédié, lease 10 minutes, reprise 1 minute entre pages, cycle suivant 12h,
  backoff et Retry-After sur erreurs. Pas d'avancement du curseur sur échec.
- Flux partiels : aucune fermeture par absence. Fraîcheur et qualification communes.
- Source par employeur, identifiant WTTJ stable, imports idempotents. Pas de fusion
  floue des doublons entre plateformes. Une annonce requalifiée hors périmètre
  rend son ancienne source inactive pour la publication.

Le stock n'est pas figé : des republications peuvent déplacer une annonce entre
pages. Les cycles repartent de zéro ; aucune garantie d'exhaustivité n'est annoncée.
L'index français peut ne pas représenter toutes les annonces internationales.
La configuration Algolia utilisée est celle du moteur de recherche public : si elle
change, le worker échoue explicitement au lieu d'utiliser des identifiants privés.

## Exploitation
```sh
uv run python manage.py run_wttj_worker --seed-countries FR BE DE ES NL --once --limit 5
uv run python manage.py run_wttj_worker --poll-interval 30 --limit 1
```

## Référence de protocole
https://github.com/kalil0321/ats-scrapers/blob/6b44a1badc9bfbf5cf176f75265cc5729e520e99/src/ats_scrapers/scrapers/welcometothejungle.py

L'implémentation locale ne reprend pas son assimilation apprenticeship/internship,
ni son utilisation du seul premier bureau comme localisation.

## Recette du 1er octobre 2026 (heure de Paris)
320 tests backend passent ; Ruff, Compose et absence de migration vérifiés.
Pilote de 208 annonces : 111 importées et visibles, 27 hors périmètre, 70 incertaines.
Répartition publiée : FR 38, BE 20, DE 14, ES 21, NL 18. La reprise française
après découpage a été exécutée réellement ; son curseur poursuit la partition.
`source_total` dans le rapport est le total de la fenêtre courante, pas un total
cumulé mondial. Rapport : `research/2026-10-01-wttj-pilot.json`.

47 pays du périmètre Europe configurés pour interrogation, sans affirmation que
WTTJ dispose d'annonces dans chacun. Worker local lancé et service Compose ajouté.
Le catalogue global comptait 1 571 offres au contrôle ; les autres collecteurs
fonctionnent simultanément, ce chiffre n'est pas attribuable au seul lot V7.
Sauvegarde : `~/.codex/backups/intern-coverage-v7-20261001/before-wttj.dump`.
