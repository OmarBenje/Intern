# Connecteur SmartRecruiters public

Contrat public : https://developers.smartrecruiters.com/docs/endpoints et
https://developers.smartrecruiters.com/reference/findpostings. Le 30 septembre
2026, les endpoints de liste et détail BoschGroup ont répondu HTTP 200 sans
identifiants. Le payload fournit `totalFound`, `offset`, `content`, les identifiants
numériques, `typeOfEmployment.id`, `location.country`, `remote`, `hybrid`,
`jobAd.sections`, `postingUrl`, `applyUrl` et `releasedDate`.

## Enregistrer une entreprise

```sh
uv run python manage.py register_source https://careers.smartrecruiters.com/BoschGroup --company 'Bosch Group' --enable
```

Une URL de fiche `https://jobs.smartrecruiters.com/BoschGroup/123-titre` est
normalisée vers la même source entreprise. Répéter l'enregistrement conserve le
même candidat et le même board. `--enable` effectue une collecte pilote avant
validation ; une erreur suspend le planning.

## Périmètre et garanties

Ce nouveau provider a un périmètre fixe
`europe-confirmed-internships-onsite-hybrid-v2` : pays ISO présent dans le périmètre
européen courant et `remote=false`, puis stage confirmé par le moteur de qualité.
Les candidats sont sélectionnés par contrat ATS `intern` ou titre explicite de
stage (sans intitulé négatif/alternance). Pour les titres explicites avec contrat
générique permanent/Full-time, la description complète est analysée par
`extract_facts` ; seuls les stages confirmés sont conservés et le contrat normalisé
reste `unknown` afin de garder la preuve textuelle réelle. Pays ambigus et offres
remote ne sont pas importés par ce connecteur. Cela ne
prétend pas couvrir tous les stages publiés par l'entreprise. Le filtrage de
qualité commun s'applique encore après import. Aucun paramètre de filtrage serveur
non vérifié n'est utilisé.

La liste entière est parcourue (100 résumés/requête), puis seuls les détails en
périmètre sont lus. Une collecte complète désigne donc le snapshot de ce périmètre,
pas tous les emplois de l'entreprise. La version 2 élargit la version 1 aux stages confirmés par le texte : les annonces
confirmées précédemment restent couvertes. Une future réduction de périmètre exige
une migration explicite pour éviter de fausses fermetures.

Bornes : 200 pages, 1 000 détails, 80 Mio cumulés de JSON décodé, 20 Mio par réponse,
600 secondes avec vérification entre requêtes et chunks. Les requêtes utilisent
uniquement `api.smartrecruiters.com`, HTTPS, sans redirection ni proxy implicite.
L'URL `ref` du payload n'est jamais suivie. Seules les URLs HTTPS de candidature
et de publication sont conservées ; aucun envoi de candidature n'est effectué.

Total changeant, doublon d'identifiant, page incomplète, détail disparu/modifié
hors périmètre, identité différente ou limite atteinte font échouer tout le
snapshot, sans confirmer d'absence ni fermer d'offre. Le backoff et Retry-After
réutilisent le mécanisme commun. Une chute suspecte reste en quarantaine.
La section optionnelle `videos` ne contient pas de texte et est ignorée.
Les descriptions complètes et la date de publication d'origine sont conservées
dans les données sources ; `published_at` est également rendu par le normaliseur.

Vérification : `uv run python manage.py test jobboard.tests.test_smartrecruiters
jobboard.tests.test_engine_collection --noinput` (16 tests réussis en v1 ; les 6 tests du connecteur repassent en v2).
