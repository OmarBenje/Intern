# Logos des entreprises

Date : 2026-10-01. Statut : implémenté et validé localement.

## Problème observé

La base locale compte 1 476 entreprises, 204 logos en cache et seulement 8
domaines renseignés. Parmi les logos, 165 partagent le SHA-256
`037e67fd114b8f2a091d5973a2d89b5705614c3a1812192a51f9358fc73083aa` :
l'image inspectée est le favicon LinkedIn. Les pages génériques de plateformes
sont traitées comme des sites employeur. Les échecs d'extraction sont réessayés,
mais un logo incorrect déjà enregistré n'est jamais corrigé.

## Outils examinés et décision

| Outil | Usage et limites | Décision |
| --- | --- | --- |
| [Brandfetch Logo API](https://docs.brandfetch.com/logo-api/overview) | Identifiant client requis ; affichage direct dans une balise image ; téléchargement et cache exigent un accord spécifique. | Alternative possible, pas de téléchargement via notre worker. |
| [Logo.dev](https://www.logo.dev/docs/logo-images/get) | Domaine + clé publiable ; PNG et fallback HTTP 404. [Auto-hébergement](https://www.logo.dev/docs/platform/self-hosting) réservé aux plans Pro/Enterprise. [Attribution](https://www.logo.dev/docs/platform/attribution) requise pour un usage commercial gratuit. | Fallback CDN facultatif, activé par configuration frontend ; aucun téléchargement ni abonnement automatique. |
| [Clearbit](https://clearbit.com/changelog) | API publique fermée le 8 décembre 2025. | Exclu. |
| Site officiel / page ATS propre à l'employeur | Logo explicite ou `Organization.logo` / `JobPosting.hiringOrganization.logo` en JSON-LD ; icône officielle comme repli. | Source par défaut, sans clé tierce. |

[Schema.org Organization](https://schema.org/Organization) définit le logo et
l'URL de l'organisation. [Google Search Central](https://developers.google.com/search/docs/appearance/favicon-in-search)
documente les icônes déclarées dans la page d'accueil. Une icône est un repli,
elle ne garantit pas un logo haute résolution. Le nom seul ne permet pas une
association fiable : aucun domaine n'est inventé ni sélectionné par popularité.

## Extraction et identité

1. Logo employeur explicitement associé au nom par une source JobSpy/WTTJ,
   puis site/domaine employeur existant, pages ATS spécifiques et au plus
   deux fiches d'offres actives, dédupliquées ; cinq pages et 45 secondes au total.
   Pour les anciennes sources WTTJ, réutiliser le slug exact déjà enregistré pour
   lire `organization.logo.url` dans l'index public. Vérifier le slug et le nom
   renvoyés avant de télécharger l'image. Ce chemin appartient au site public,
   pas à une API contractuelle documentée ; sa disponibilité reste variable.
2. Exclure les pages génériques des agrégateurs et les icônes de toutes les
   plateformes, y compris leurs sous-domaines et ATS hébergés par locataire.
   Une fiche employeur peut fournir un logo explicitement associé à l'organisation.
3. JSON-LD : accepter seulement l'organisation dont le nom correspond à celui
   de l'entreprise. Parcourir des graphes bornés et ignorer le JSON invalide.
   Liens de logo ATS vers un site externe : utiliser seulement des destinations
   HTTPS hors plateformes ; un lien de pied de page n'établit pas l'identité.
4. Chercher le logo structuré, le logo explicite, puis apple-touch-icon / favicon
   du site officiel. Ignorer logos clients, sociaux, fournisseurs et pieds de page.
5. Conserver les formats raster déjà supportés ; pas d'exécution SVG. HTTPS,
   contrôle DNS public à chaque redirection, connexion TLS épinglée, 2 Mio et
   4 millions de pixels maximum ; PNG normalisé de 256 pixels maximum.
6. Rejeter également le digest du favicon LinkedIn confirmé. Conserver pour chaque
   succès l'URL finale de l'image, le type de source et la date d'acquisition.
   Enregistrer l'identité indépendamment du téléchargement du logo : site déjà
   connu, `company_website` associé au même employeur, organisation structurée
   explicitement correspondante ou lecture réussie du site employeur. Les
   métadonnées contradictoires restent indéterminées ; conserver les identités
   valides existantes. `enrich_company_domains` complète aussi les entreprises
   dont le logo est déjà en cache, avec un traitement borné et reprenable par ID.

## Cache et réparation

Une migration retire uniquement les références au digest LinkedIn confirmé et
remet ces entreprises dans la file. Les objets existants restent en stockage.
Les autres logos existants restent utilisables ; leur provenance historique est
inconnue. La commande d'extraction propose une limite, une file d'entreprises
sans logo et un rafraîchissement ciblé. Un échec de rafraîchissement conserve
le logo précédent. Le worker conserve sa réservation et son backoff existants.

Un audit sans réseau expose couverture, domaines, provenance, erreurs et
digests partagés pour diagnostiquer les manques sans confondre des filiales
partageant une marque avec des logos incorrects.
Son option `--repair` retire les références aux seuls digests rejetés connus.
L'API refuse également ces images pour empêcher un ancien worker encore actif
de les afficher à nouveau ; redémarrer les workers après une mise à jour.

## Affichage

L'objet API `company` ajoute `domain` (domaine employeur validé ou `null`) et
conserve `logo_url` (route locale versionnée ou `null`). Les champs internes
`logo_source_url`, `logo_source_kind` et `logo_fetched_at` enregistrent la
provenance sans exposer de liens distants au navigateur ; l'admin les affiche
en lecture seule. Les logos historiques sans provenance restent identifiables
dans l'audit.

Composant commun aux offres, dashboard et candidatures : logo local → Logo.dev
si une clé publiable et un domaine employeur valide sont disponibles → initiale.
Un échec de chargement passe au candidat suivant et une nouvelle URL peut être
réessayée. Taille stable, `object-fit: contain`, fond blanc, image décorative,
nom toujours visible. Aucune requête CDN sans clé ni domaine. Un crédit visible
est affiché dans l'espace candidat lorsque Logo.dev est configuré.
Le crédit est aussi présent sur la page publique de connexion, afin de permettre
l'attribution publique exigée pour un usage commercial sur le plan gratuit.

## Exploitation

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py audit_company_logos
.venv/bin/python manage.py audit_company_logos --repair
.venv/bin/python manage.py extract_company_logos --provider wttj --limit 500
.venv/bin/python manage.py extract_company_logos --company-id 26 --page-url https://www.airbus.com/en/careers
.venv/bin/python manage.py run_company_logo_worker
```

`extract_company_logos` traite 25 entreprises par défaut, au plus 500 par passe,
en priorisant celles qui ont le plus d'offres ; `--refresh` permet de remplacer
un ancien logo et garde le précédent si l'acquisition échoue. Le worker normal
consomme déjà la file et ajoute les logos aux nouvelles entreprises.

Pour le fallback Logo.dev, copier `frontend/.env.example` vers `frontend/.env.local`,
renseigner `VITE_LOGO_DEV_PUBLISHABLE_KEY=pk_…` avec une clé obtenue dans son propre
compte, puis relancer Vite/recompiler. L'intégration CDN est testée avec des images
simulées ; aucun compte, achat ou appel Logo.dev authentifié n'a été effectué.

## Validation et critères d'acceptation

- Une page LinkedIn/WTTJ générique ne peut jamais attribuer son favicon à un employeur.
- Le digest LinkedIn est retiré en base et rejeté lors de toute nouvelle acquisition.
- JSON-LD homonyme rejeté ; graphe et URLs malformés n'arrêtent pas la file.
- URL privée, HTML/SVG et images surdimensionnées refusés ; aucune requête distante
  lors de la lecture API d'un logo.
- Les pages d'offres enrichissent les entreprises sans domaine ; l'extraction
  reste bornée et conserve la provenance.
- Tests backend ciblés, migration vérifiée et extraction réelle bornée ; frontend
  compilé et fallbacks vérifiés dans le navigateur.
- Les logos introuvables restent des initiales. La couverture des 1 476 entreprises
  n'est pas promise sans sites identifiés ou fournisseur configuré.

## Bilan local vérifié

Le snapshot de couverture (`company-logos-2026-10-01.json`, export historique supprimé ; voir la [note sur les exports](../research/README.md)) du 1er octobre
2026 contient 1 500 entreprises (les collecteurs ont continué à importer pendant
l'intervention), 901 logos en cache, dont 862 avec provenance, et 599 entreprises
sans image. Aucun digest LinkedIn rejeté ne reste référencé. Les 39 autres logos
historiques n'ont pas de provenance et n'ont pas été tous contrôlés visuellement.

Les trois passes WTTJ ont récupéré 300/300, 499/500 et 40/41 logos. Le dernier
échec, Cure51, n'expose plus de logo dans l'index consulté et sa page renvoie une
erreur publique. Les autres sources et les passes ciblées ont notamment récupéré
Picnic, Canonical, Airbus, Adyen et HubSpot. Le worker local a été redémarré pour
charger le correctif ; les objets rejetés restent en stockage mais ne sont plus
servis ni annoncés par l'API.

Validation : 44 tests backend (logos, WTTJ, JobSpy), 3 tests navigateur avec CDN
simulé et 1 sans configuration CDN ; compilation frontend, lint des fichiers
concernés et absence de migration manquante confirmés. Un échantillon de 24 logos
WTTJ a été inspecté visuellement ; la lecture authentifiée du PNG réel Framatome
renvoie 200, `image/png`, 10 535 octets. L'admin local renvoie également 200.

Les téléchargements réels ont utilisé les sources du catalogue et les sites
officiels, sans clé Logo.dev. La présence de 901 images ne signifie pas que la
couverture est complète : les sites bloqués, les entreprises sans identité
vérifiée ou sans asset raster gardent une initiale. L'index public WTTJ n'est
pas un contrat de disponibilité ; les échecs restent dans la file avec backoff.
