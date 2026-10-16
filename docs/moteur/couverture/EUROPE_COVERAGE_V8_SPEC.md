# Couverture V8 — Eightfold PCSX

## Périmètre
Connecter les portails publics PCSX identifiés, avec une liste explicite des
hôtes API, domaines tenant et hôtes des fiches. Pilotes : NVIDIA, Dolby, Microsoft.
Bayer est reconnu mais son accès PCSX observé est refusé. La variante SmartApply
n'est pas implémentée ; aucune collecte authentifiée ou contournement de blocage.
Le registre général n'active pas automatiquement tous les tenants Eightfold.

## Contrats
- Recherche publique /api/pcsx/search par intern, Praktikum, stage et tirocinio.
- 10 annonces par page ; compte total et absence de doublons contrôlés par requête.
- Détails publics /api/pcsx/position_details : identité numérique vérifiée et
  description réelle requise. L'identifiant interne Eightfold reste la clé source ;
  displayJobId/atsJobId sont conservés comme preuves, pas utilisés comme URL.
- Toutes les standardizedLocations conservées. Pays provenant du dernier champ
  structuré de la localisation, jamais du siège ou du pays recherché. Les stages
  avec pays inconnu restent exclus. Les détails manifestement hors Europe ne sont
  pas téléchargés.
- Qualification textuelle commune, exclusions apprentissage et emplois étudiants,
  traitement conservateur du remote. Pas de conversion automatique trainee→stage.
- URLs de fiche reconstruites sur les hôtes inspectés. Aucun lien arbitraire de la
  réponse n'est suivi. Redirections HTTP désactivées.
- Snapshots toujours partiels : aucune fermeture par absence. Fraîcheur commune.

## Budgets
20 pages par terme, 120 détails, 300 secondes, 30 Mio au total. Les plafonds sont
signalés dans les diagnostics. HTTP 429 interrompt les détails ; une erreur de
recherche ne devient pas une liste vide. Les recherches se recoupent et sont
dédupliquées par identifiant. Les variantes linguistiques et le plafond de pages
limitent la couverture ; il ne s'agit pas de tout le stock mondial du tenant.

## Intégration
Reconnaissance des URL, importeur commun, ordonnanceur catalogue existant. Aucune
migration, dépendance supplémentaire ou worker dédié. La bibliothèque ats-scrapers
n'est pas installée. La déduplication entre Eightfold et les ATS sous-jacents n'est
pas automatique sur le seul numéro de réquisition : les copies restent possibles.

```sh
uv run python manage.py register_source https://nvidia.eightfold.ai/careers --company NVIDIA --enable
uv run python manage.py register_source https://dolby.eightfold.ai/careers --company Dolby --enable
uv run python manage.py register_source https://apply.careers.microsoft.com/careers --company Microsoft --enable
```

## Recette
Tester les identifiants, l'absence de description, les pays hors Europe/inconnus,
le remote, les hôtes usurpés, le recouvrement des termes, les limites de débit et
l'idempotence de l'import. Les gains live sont mesurés uniquement sur les sources
Eightfold, séparément des autres workers en cours.
Sauvegarde : `~/.codex/backups/intern-coverage-v8-20261001/before-eightfold.dump`.

## Référence de protocole
https://github.com/kalil0321/ats-scrapers/blob/6b44a1badc9bfbf5cf176f75265cc5729e520e99/src/ats_scrapers/scrapers/eightfold.py

## Recette du 1er octobre 2026
326 tests backend passent, Ruff passe, aucune migration. Pilotes : NVIDIA 3 stages
publiables, Dolby 3 (Allemagne, Pologne, Suisse et Espagne). Microsoft a échoué
sur upstream_rate_limited ; sa planification est suspendue, aucun import annoncé.
Bayer n'a pas été activé. Les autres variantes et hôtes ne sont pas validés.
Les collectes NVIDIA/Dolby utilisent le worker catalogue existant, relancé avec le
nouveau code. Aucun nouveau worker ni nouveau service Docker n'est nécessaire.
Rapports : `research/2026-10-01-eightfold-pilot.json` et
`research/2026-10-01-eightfold-results.json`.
