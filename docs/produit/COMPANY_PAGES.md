# Pages entreprise

La route frontend `/companies/<id>` est accessible depuis le nom de l’employeur dans le détail d’une offre. Elle affiche présentation, chiffres clés, informations employeur, tous les stages publiés et recommandations propres à cette entreprise. Le retour depuis un stage conserve la recherche, la vue et la page de l’entreprise.

## API

- `GET /api/v1/companies/<id>/` : identité, site/logo, description historique, `profile.facts`, `profile.sections`, rubriques manquantes, `offers_count` et lieux des stages publiés. Accessible sans session, comme le catalogue public.
- `GET /api/v1/companies/<id>/offers/` : même publication et mêmes filtres que `/offers/`, imposés à cette entreprise, avec pagination v1. Aucun accès aux préférences privées.
- `GET /api/v1/recommendations/?company=<id>` : recommandations privées filtrées sur cette entreprise. Le paramètre doit être un entier positif. Contrat existant conservé : chaque résultat contient `offer`, `match`, `ranking`, `reasons`.

Les états frontend couvrent chargement, erreurs/réessai, entreprise absente, données manquantes, liste vide, recherche et pagination. Les valeurs sont rendues comme texte et les liens externes sont limités à HTTP(S).

## Enrichissement

Le modèle `CompanyProfile` contient deux listes bornées. Chaque entrée doit avoir `key`, `value`, `source_url`, `observed_at` ISO avec fuseau et `source_kind` (`employer`, `job_posting`, `editorial`). `scope` précise pays/programme/population concernée ; `offer_id` peut conserver la référence d’origine. L’admin entreprise propose un profil en ligne et valide ces champs. Les données invalides écrites hors admin sont écartées à la lecture.

`facts` supporte secteur, effectif, siège, création, stade, financement, investisseurs, CA, direction, international, âge et parité. `sections` supporte présentation, culture, avantages, recrutement, jeunes talents, technologies, engagements, actualités et médias.

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py enrich_company_profiles
.venv/bin/python manage.py enrich_company_profiles --company-id 2
.venv/bin/python manage.py enrich_company_profiles --import-file docs/research/company-profiles-reviewed-2026-10-01.json
```

La commande par défaut travaille hors réseau sur les annonces stockées et leur dernière révision. Elle sélectionne des présentations explicitement balisées « About us », « About <nom entreprise> » ou `companyDescription` dans une révision correspondant au texte actuel. Elle ne transforme pas les missions, le profil candidat ou les conditions d’une annonce en faits généraux sur l’employeur. Elle ne remplace pas une présentation existante. Relancer après les imports ajoute les fiches jusque-là manquantes.

L’import d’un JSON relu fusionne les entrées par clé, dans une transaction, et préserve les autres rubriques. Il vérifie l’entreprise par ID et, si fourni, son nom. Le fichier relu inclus concerne **Stripe, ID local 2** ; vérifier ce couple avant de l’utiliser sur une autre base. Une deuxième exécution remplace les mêmes clés sans dupliquer les entrées.

Les présentations ne sont pas complètes pour toute la base. Les autres champs ne sont pas devinés depuis une offre. Le [benchmark](../research/company-pages-2026-10-01.md) détaille les observations et la suite proposée.
