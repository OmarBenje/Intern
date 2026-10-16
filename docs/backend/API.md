# API candidat Intern

Les routes publiques `companies/<id>/` et `companies/<id>/offers/`, ainsi que le filtre privé `recommendations/?company=<id>`, sont documentés dans [Pages entreprise](../produit/COMPANY_PAGES.md).

Implémentation Django REST framework 3.18. Les routes conservent le contrat v1 ; [décisions et sources](DRF_MIGRATION_SPEC.md). Les corps de commande passent par des serializers stricts et les lectures par des serializers aux champs explicites.

Préfixe `/api/v1/`. JSON objet et cookie de session Django. Toutes les mutations requièrent `X-CSRFToken`, y compris inscription et connexion. Récupérer le token via `GET auth/csrf/` et utiliser le nouveau token retourné après authentification. Pas de CORS ouvert : le frontend est prévu sur la même origine. Réponses privées `Cache-Control: no-store`.

Les routes et objectifs figurent dans [BACKEND_SPEC.md](BACKEND_SPEC.md). Exemples de corps :

```json
{"username":"candidate","email":"candidate@example.com","password":"a-long-unique-password","full_name":"Ada Example"}
```

`auth/register/` POST répond `201` avec `status: pending` et crée un compte inactif, sans ouvrir de session. Le superviseur doit l'activer avant la connexion ; une tentative avec le bon mot de passe avant activation répond `403 account_inactive`. Connexion : `auth/login/` POST `{username,password}`. Déconnexion : POST `{}`. Identité : `auth/me/` GET. Mot de passe : `auth/password/` POST `{old_password,new_password}`. Reset : POST `{email}` sur `auth/password-reset/` puis `{uid,token,new_password}` sur `auth/password-reset-confirm/`. Le lien email cible la page frontend `/reset-password?uid=...&token=...` ; celle-ci appelle l'API de confirmation. Un jeton utilisé devient invalide.

## Profil et recherche

`profile/` PATCH accepte `full_name`, `first_name`, `last_name`, `phone`, `headline`, `presentation`, `location_text`, `location_id`, `available_from`, `linkedin_url`, `github_url`, `portfolio_url`, `skill_ids`. Les champs absents sont conservés ; les champs nullable acceptent null. Version et propriétaire ne sont jamais assignables.

Collections `/profile/experiences/`, `/profile/education/`, `/profile/projects/`, `/profile/work-authorizations/` : GET paginé, POST création, puis PATCH/DELETE sur `/<id>/`. Les champs exacts sont les listes explicites `CHILDREN` dans `jobboard/services/profiles.py`. Une autorisation de travail envoyée par le candidat reçoit une date de confirmation serveur.

`preferences/` PUT conserve les champs omis et remplace les listes fournies. Exemple :

```json
{"role_ids":[1],"location_ids":[1],"contracts":["internship"],"work_modes":["hybrid","remote"],"minimum_salary":"1200.00","salary_currency":"EUR","salary_period":"month","salary_gross_net":"gross","willing_to_relocate":true}
```

Pour supprimer le salaire minimum, envoyer `minimum_salary`, `salary_currency`, `salary_period` à null ensemble. Les listes vides sont conservées comme choix explicites.

`offers/` GET : `q`, `role` (ID), `location` (ID), `contract_type`, `work_mode`, `page`, `page_size`. `offers/<id>/` ajoute la description en texte. Les descriptions doivent être affichées comme du texte, jamais comme du HTML de confiance. `catalogue/?kind=roles|skills|locations` est paginé, avec recherche `q`. `saved-offers/<offer_id>/` PUT `{}` et DELETE sont idempotents ; `saved-offers/` retourne aussi les anciennes offres sauvegardées. `recommendations/` retourne `{offer,reasons}` ; aucun score de probabilité d'embauche. Les contrats et modes acceptés sont obligatoires ensemble ; sans préférences explicites, aucune recommandation. `include_unknown=true` conserve les données inconnues, `false` les exclut. Un salaire n'est comparé que si devise, période et brut/net correspondent ; `unknown_fields` et `salary_comparison` expliquent ce traitement.

## Documents

`documents/` POST multipart : un `file` PDF et un `kind` (`resume` ou `cover_letter`). Réponse : ID, statut, SHA-256, taille, nom. `profile/resume/` PUT `{ "document_id": 1 }` sélectionne le CV courant. GET `documents/` paginé ; GET `documents/<id>/download/` télécharge le PDF en pièce jointe. DELETE `documents/<id>/` retourne 204 ; 409 si une révision, un CV courant, une preuve ou un upload actif empêche la suppression.

## Dossiers, approbation et suivi

`applications/` POST `{offer_id,source_id}` crée ou retrouve le dossier existant. GET paginé, filtre `status` facultatif. `applications/<id>/` retourne le dossier, `latest_revision` et `latest_run`. Les historiques indépendants sont paginés avec GET `/revisions/`, `/runs/` et `/events/`.

POST `/prepare/` `{}` prend un nouveau snapshot du profil, de l'offre et du formulaire. Chaque correction POST `/revisions/` crée une nouvelle révision :

```json
{"answers":[{"field_key":"first_name","value":"Ada"},{"field_key":"last_name","value":"Example"},{"field_key":"email","value":"candidate@example.com"}],"document_ids":[1]}
```

Envoyer la liste complète des réponses voulues ; les réponses omises ne sont pas reprises. `field_key` doit exister dans `form_snapshot.fields` ; les fichiers sont représentés dans `document_ids`, jamais comme des réponses textuelles. Les sources et dates de confirmation des corrections sont fixées serveur. Les révisions retournent `content_hash`, `missing_fields`, les snapshots et pièces réellement prévues.

POST `/approve/` :

```json
{"revision_id":1,"content_hash":"64-caracteres-hexadecimaux-retournes-par-la-revision","idempotency_key":"0aaf3ac0-32c4-4e84-8b67-b4486bac9536"}
```

Réutiliser **la même clé pour le même clic**, même après coupure réseau. Retour : run queued ou run précédemment créé. Une autre clé ne contourne pas un run actif/incertain. Le frontend doit afficher exactement le dossier correspondant au hash approuvé. Accord limité à 24 h. Toute modification impose une nouvelle révision et approbation.

POST `/revoke/` `{}` annule avant effet externe ; après début d'envoi, 409. POST `/resolve/` `{outcome:"submitted"|"not_submitted",evidence:"référence ou vérification effectuée"}` est réservé à la résolution humaine d'un run incertain après fin de lease. Cette action n'envoie rien. L'origine `user` est conservée dans l'historique.

POST `/status/` `{status,reason}` enregistre une correction de suivi ; elle est bloquée pendant un run actif/incertain. Statuts : draft, submitted, screening, interview, offer_received, accepted, rejected, withdrawn. Une candidature envoyée ne revient pas à draft.

`/tasks/` GET/POST puis `/<id>/` PATCH/DELETE : title, due_at, completed_at. `/interviews/` mêmes méthodes : title, starts_at, ends_at, display_timezone (IANA), meeting_url, location_text, status, notes. Pas d'événement envoyé par email/calendrier : ces objets sont le suivi interne.

## Export et suppression

GET `account/export/` : ZIP privé, `data.json` versionné et `documents/<id>.pdf`, maximum 100 Mio. POST `account/delete/` `{password}` : désactivation immédiate, déconnexion, reçu de demande. La commande `purge_accounts` effectue ensuite la purge reprise sur erreur.

## Erreurs et pagination

```json
{"error":{"code":"missing_answers","message":"Complete required application fields.","details":{"fields":["first_name"]}}}
```

Listes : `{results,count,page,page_size}`. Pages commencent à 1, taille par défaut 20, maximum 100. Une page inexistante renvoie 404. Les IDs étrangers retournent la même erreur 404 qu'une ressource absente. 400 validation, 401 session, 403 CSRF, 409 conflit, 413 taille, 415 mauvais Content-Type, 429 limite d'authentification, 503 source/stockage indisponible.

## Comportements DRF

- Réponses JSON uniquement ; demander exclusivement un format non proposé donne 406
  (`not_acceptable`). Les téléchargements autorisés restent des réponses fichier.
- `OPTIONS` est disponible sur les routes, sous les mêmes permissions de session.
- Les réponses 401 portent `WWW-Authenticate: Session` ; le frontend doit utiliser
  le parcours de connexion et les cookies Django.
- L’enveloppe d’erreur reste `{error:{code,message,details}}`. Les erreurs de champs
  produites par les serializers utilisent `validation_error` et une liste de messages
  par champ dans `details`. Les champs inconnus/manquants conservent `invalid_fields`.
- Le compteur PostgreSQL d’authentification est conservé ; aucun throttle de cache
  non atomique ne le remplace. Aucune session n’est invalidée par cette migration.

## Moteur de stages européen

`GET offers/`, `GET offers/<id>/` et `GET coverage/` sont publics. Le catalogue, les recommandations, les suggestions du tableau de bord et les compteurs partagent une frontière serveur obligatoire : stage `confirmed`, Europe `in_scope`, offre ouverte/non expirée et publication active fraîche. Aucun paramètre client ne peut élargir ce périmètre. Les annonces non classées, hors stage, hors Europe ou de localisation inconnue restent dans la base de collecte sans être publiées. Les autres routes ci-dessous exigent une session ; toute mutation exige aussi le token CSRF. Les champs propriétaire, statut interne, version et identifiants de preuve ne sont pas assignables par les commandes candidat. Les listes privées suivent la pagination standard `{results,count,page,page_size}`.

### Catalogue et qualité

Les filtres existants restent disponibles. Les nouveaux paramètres sont :

| Paramètre | Valeurs / règle |
|---|---|
| `country` | Un code pays majuscule, par exemple `FR` |
| `country_codes` | Plusieurs codes séparés par des virgules, par exemple `FR,DE` |
| `domain` | Domaine normalisé, valeur exacte |
| `classification` | `confirmed`, `uncertain`, `not_internship` ; filtre **exact** dans le périmètre publié ; les deux dernières valeurs retournent une liste vide |
| `europe_scope` | `in_scope`, `out_of_scope`, `unknown` ; les deux dernières valeurs retournent une liste vide |
| `unknown_policy` | `include` par défaut, ou `exclude` |
| `include_unknown` | `true` ou `false` ; si présent, prioritaire sur `unknown_policy` |
| `start_from`, `start_to` | Dates ISO `YYYY-MM-DD`, bornes inclusives dans l'ordre |
| `duration_min`, `duration_max` | Entiers positifs ≤ 3650, bornes dans l'ordre ; au moins une borne suffit |
| `duration_unit` | `days`, `weeks`, `months` ; obligatoire avec une borne de durée |
| `required_language` | Code langue minuscule, par exemple `fr` ; vise une langue exigée dans les preuves |
| `freshness` | `fresh`, `stale`, `all` |

La durée filtre le chevauchement de l'intervalle annoncé avec l'intervalle recherché. Jours et semaines sont comparés exactement avec des seuils entiers. Les mois ne sont pas convertis en jours : une unité incomparable suit la politique des inconnues. La langue du texte de l'annonce ne devient jamais une exigence de langue. Une contrainte de candidature absente (durée, langue, etc.) est conservée par défaut. Cela ne relâche jamais la classification stage ni la présence confirmée en Europe. Ainsi, `classification=confirmed` n'inclut pas les postes non classés ou incertains, même avec `unknown_policy=include`.

Exemple de parcours, sans profil privé :

```http
GET /api/v1/offers/?classification=confirmed&europe_scope=in_scope&country=FR&duration_max=6&duration_unit=months&include_unknown=true
```

Chaque offre ajoute `quality` lorsqu'une extraction existe : `{classification,europe_status,country_codes,domain,content_version}`. `last_verified_at` est la dernière vérification d'une publication active ; `stale` vaut vrai si aucune publication active n'a été vérifiée dans sa fenêtre `max(24 h, 2 × cadence)`. Le détail ajoute `facts`, un objet de faits avec valeur, extrait justificatif et référence à la révision source. Le client rend les extraits et descriptions comme du texte. Les snapshots bruts, secrets de connecteur et données candidat ne sont pas exposés.

Chaque entrée de `sources` ajoute `capabilities:{collect,submit,manual_external}`. `submit` vérifie l'adaptateur réellement configuré et l'ouverture de l'offre ; un catalogue public ne donne aucun droit d'envoi. En son absence, `submission_mode` vaut `manual_external`.

Une offre fermée reste consultable par son ID seulement si elle reste un stage confirmé en Europe. Un détail hors de ce périmètre retourne 404. Les favoris et dossiers privés conservent leur historique, sans republier leurs offres. Une offre masquée reste inaccessible ; seule une décision de fusion active vers une offre visible autorise un alias, retournant le détail canonique et `redirected_from_offer_id`.

`recommendations/` conserve ses champs historiques et ajoute `match:{compatibility,reasons,unknown_fields,versions}` par résultat. Les compatibilités sont `compatible_known`, `needs_verification`, `incompatible_explicit`. `onboarding_required` au premier niveau indique l'absence des préférences nécessaires. Le masquage d'une offre ou d'une entreprise ne modifie que les recommandations et alertes de son propriétaire.

### Recherches, feedback et alertes privées

| Route | Commande |
|---|---|
| `saved-searches/` | GET liste ; POST `{name,criteria,frequency,timezone}` → 201 |
| `saved-searches/<id>/` | GET ; PATCH champs modifiables ; DELETE → 204 |
| `offers/<id>/feedback/` | PUT `{reason}` ; DELETE pour rétablir l'offre |
| `company-preferences/<company_id>/` | PUT `{excluded:true|false}` ; DELETE |
| `companies/<company_id>/preference/` | Alias de la route précédente |
| `offers/<id>/reports/` | POST `{reason,details?}` → 201, sans fermeture automatique |
| `alerts/` | GET liste privée |
| `alerts/<id>/read/` | POST ou PUT `{}` ; lecture idempotente |

Une recherche contient `{id,name,criteria,frequency,timezone,version,created_at,updated_at,last_evaluated_at}`. `frequency` est `off` ou `daily` ; `timezone` est un nom IANA validé, par défaut `Europe/Paris`. Maximum 50 recherches par compte. `criteria` accepte les filtres du tableau ci-dessus, avec `country_codes` sous forme de liste JSON, ainsi que `q`, `contract_type`, `work_mode`, `duration_max_months` (1–36), `available_from`, `available_until`, `languages` (liste de codes confirmés) et `needs_sponsorship` (booléen). Les dates de disponibilité doivent être dans l'ordre. Une modification effective incrémente la version et établit une nouvelle référence temporelle.

```json
{"name":"Stages en France","criteria":{"classification":"confirmed","europe_scope":"in_scope","country_codes":["FR"],"duration_max":6,"duration_unit":"months","unknown_policy":"include"},"frequency":"daily","timezone":"Europe/Paris"}
```

Le feedback accepte `not_interested`, `wrong_role`, `wrong_location`, `wrong_contract`, `other`. Le signalement accepte `closed`, `duplicate`, `wrong_location`, `wrong_contract`, `not_internship`, `other`, avec au maximum 2000 caractères de détails.

Les alertes sont internes à l'application, évaluées lorsque 24 heures se sont écoulées depuis la dernière évaluation ; le fuseau est conservé mais aucun horaire local fixe d'envoi n'est promis. Le premier enregistrement n'envoie pas l'historique. Les événements sont dédupliqués par candidat et version de contenu de l'offre, y compris entre plusieurs recherches. Les nouveautés, changements significatifs et réouvertures peuvent produire un événement si l'offre correspond encore aux critères ; les sources périmées ne produisent pas d'alerte. Chaque alerte expose `{id,offer_id,payload,created_at,read_at}` ; `payload` contient notamment titre, recherche, version de recherche et compatibilité.

### Liens externes privés

`external-opportunities/` GET liste ou POST `{url,title?,company_name?,description?}` retourne **202**, avec `{id,url,title,company_name,description,status,error_code,offer_id,created_at,updated_at}`. `external-opportunities/<id>/` permet GET, PATCH des mêmes champs de saisie, et DELETE. Changer l'URL remet l'extraction en attente. L'URL doit être HTTPS, sans identifiants intégrés ; titre ≤ 300 caractères, entreprise ≤ 240, description ≤ 20000.

Le worker traite `pending` vers `ready` ou `failed`. Pour les URLs d'offres Greenhouse, Ashby et Lever reconnues, il utilise les connecteurs aux hôtes API fixes et un identifiant de tableau strict ; il ne suit pas de redirection et ne télécharge jamais une URL arbitraire fournie par le candidat. Une annonce extraite reste privée et n'est pas publiée au catalogue. Les liens non pris en charge restent enregistrés avec `unsupported_source` et peuvent être complétés manuellement ; un échec conserve également les champs saisis. Un succès d'extraction ne signifie jamais candidature envoyée.

### Couverture et données personnelles

`coverage/` expose `countries:[{locations__country_code,offers}]` calculé depuis les pays extraits, `domains:[{enrichment__domain,offers}]`, `active_sources`, `verified_sources`, `latest_verification`, `limitations`. Le champ `scope` vaut `confirmed_europe_internships` : les compteurs pays/domaines portent uniquement sur les stages confirmés, ouverts, non expirés, frais et classés en Europe ; les compteurs sources décrivent le registre surveillé, sans dénominateur permettant une promesse d'exhaustivité. Une offre multi-pays peut contribuer à plusieurs compteurs.

L'export du compte inclut recherches, feedback, exclusions d'entreprises, signalements, alertes et opportunités externes. Ces objets sont supprimés avec leur propriétaire. Les IDs appartenant à un autre compte répondent 404.

### Recherche du catalogue — complément

`GET /api/v1/offers/` accepte `sort=relevance|newest` (pertinence par défaut avec
`q`, nouveautés sinon) et `published_within=1|7|30` (jours glissants selon la date
de publication connue, hors dates futures). Les critères peuvent être conservés
via `saved-searches/`. `q` recherche également l'entreprise, avec un dictionnaire
borné d'alias multilingues ; phrases entre guillemets, `OR` et exclusions sont
respectés sans expansion. `work_mode` respecte `include_unknown` comme les
recherches enregistrées. Le périmètre obligatoire stage + Europe ne peut être
élargi par ces options. `duration_min`, `duration_max` nécessitent `duration_unit` ;
les bornes inversées retournent 400.

Depuis V2, le document pondéré indexé réunit titre, entreprise et description.
Accents et casse sont normalisés des deux côtés ; `C++`/`cpp`, `C#`/`csharp`
et `.NET`/`dotnet` restent des tokens distincts. Le renommage d'entreprise et les
imports bulk mettent à jour ce document via les triggers PostgreSQL.

`GET /api/v1/offers/suggestions/?q=pythonn&country_codes=FR` est public et retourne
`{"suggestions":[{"query":"Python Internship"}]}` (au plus trois titres).
Les autres filtres du catalogue sont acceptés et la frontière de publication
reste obligatoire. Les requêtes de moins de trois caractères alphanumériques,
de plus de 100 caractères, de plus de huit mots, ou contenant des opérateurs
explicites retournent une liste vide. Le frontend appelle cette route seulement
après un résultat vide et attend un clic pour changer la recherche.

`recommendations/` ajoute `ranking:{score,version:"preferences-1"}`. Le classement
SQL précède la pagination : métier +12, lieu +8, compétences +4 chacune (trois
maximum), contrat connu accepté +2, mode connu accepté +2. Les inconnues ne
donnent pas de bonus. Ce score ne prouve pas l'éligibilité ; le champ `match`
conserve son sens. `sort=newest` permet de choisir l'ordre chronologique.
Les préférences d'un autre utilisateur ne participent jamais à ce score.

Spec, mesures et commande reproductible : [SEARCH_ENGINE_SPEC.md](../moteur/SEARCH_ENGINE_SPEC.md).

### Couverture observée (lot 18)

`GET /api/v1/coverage/` ajoute `published_offers`, `measured_at`, `providers`,
`deduplication` et `counting_note` aux champs existants. Chaque provider retourne
`offers` (offres distinctes ayant une source fraîche), `queries` (comptages par
état), `boards` (enabled/paused/error/overdue) et `errors` (code/count agrégés).
Les états et périmètres sont définis dans `../moteur/couverture/EUROPE_COVERAGE_V11_SPEC.md`. Aucun
identifiant privé ou curseur détaillé n’est exposé par cette réponse publique.
Les totaux des pays/providers ne sont pas additifs ; les doublons non résolus
restent possibles. Les détails d’exploitation sont dans la commande locale
`audit_coverage`, pas dans l’API publique.


## Espace recruteur

L’inscription accepte désormais le champ optionnel `role` (`candidate` par défaut, ou `recruiter`). Les réponses d’identité exposent ce rôle. Voir le [contrat recruteur](../produit/RECRUITER_WORKSPACE.md) pour les routes `/api/v1/recruiter/`, les contrôles d’accès, le cycle de vérification et les limites des intégrations externes.
