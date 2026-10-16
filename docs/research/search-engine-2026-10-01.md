# Recherche — pertinence et performance du moteur de stages

Date de consultation : **1 octobre 2026**. Sources : pages publiques des éditeurs et documentation officielle. Périmètre : catalogue européen multilingue existant, avec stages SWE comme cas de contrôle, sans réduire les autres domaines.

## 1. Comparaison des produits

Les fonctions ci-dessous sont **observées dans une page publique** ou **documentées par l'éditeur** ; leurs effets sur la pertinence et leur vitesse n'ont pas été mesurés. Aucun poids ou algorithme propriétaire n'est connu.

| Produit | Constat sourcé | Application proposée pour Intern |
|---|---|---|
| Welcome to the Jungle | Son aide documente une recherche personnalisée à partir du profil et des préférences : métier, contrat, plusieurs localisations, télétravail, expérience, secteur. La page précise que le panneau expliquant une correspondance est annoncé pour plus tard en 2026 : sa disponibilité effective n'est pas confirmée ici. [Filtres officiels](https://help.welcometothejungle.com/en/filter-your-job-search-on-welcome-to-the-jungle) | Conserver des filtres explicites et modifiables ; ne pas déduire l'éligibilité d'une simple préférence. |
| JobTeaser | Le catalogue public présente une entrée métier/entreprise/mot-clé, une entrée ville/région/pays, un filtre de contrat. Les cartes reçues affichent durée du stage, lieu et ancienneté de publication ; elles mélangent aussi d'autres contrats. [Catalogue observé](https://www.jobteaser.com/en/job-offers?locale=en) | Faire fonctionner les recherches combinées entreprise + métier et afficher fraîcheur/durée. Intern conserve sa règle plus stricte de publication des seuls stages européens confirmés. |
| Simplify | La documentation distingue le catalogue explorable de la sélection personnelle quotidienne. [Job Matches vs Job Board](https://help.simplify.jobs/en/help/articles/6542018-job-matches-vs-job-board) | La recherche catalogue reste accessible indépendamment du profil. Une recommandation personnelle ne supprime pas une offre du catalogue. |
| Simplify | Les préférences prennent en compte plusieurs métiers, lieux, intérêts et exclusions. Chaque match possède une explication ; les contrôles de feedback servent à améliorer les recommandations selon l'éditeur. [Préférences et explications](https://help.simplify.jobs/articles/7272801-setting-your-job-match-preferences) | Garder les raisons et inconnues du matcher, les masquages privés et un feedback explicite. Ce mécanisme ne justifie aucun pourcentage de chance d'embauche. |

**Limite Indeed :** la recherche a retrouvé [l'aide officielle sur l'amélioration des recherches](https://support.indeed.com/hc/en-gb/articles/204488950-Improving-your-Job-Searches-tips-and-help), mais la page complète échoue à l'ouverture/redirige vers une destination inaccessible à l'outil. Aucun détail de syntaxe ou de classement Indeed n'est retenu. Les produits ont été comparés par leurs fonctions publiques, sans requêtes comparatives chronométrées ni compte candidat.

## 2. Recommandations techniques officielles

1. **Mesurer avant et après.** Django recommande `QuerySet.explain()` et le profiling, ainsi que des indexes guidés par les requêtes réelles. Charger les relations utiles avec `select_related`/`prefetch_related`, éviter les colonnes inutiles et le travail Python pouvant être effectué dans la base. Les indexes ont aussi un coût à l'écriture. [Optimisation Django](https://docs.djangoproject.com/en/5.2/topics/db/optimization/)
2. **Faire correspondre le filtre de recherche à l'index.** Django recommande un GIN/GiST correspondant au vecteur recherché, ou un `SearchVectorField` maintenu lorsque le calcul devient trop cher. Les poids permettent de distinguer titre et corps. [Recherche PostgreSQL dans Django](https://docs.djangoproject.com/en/5.2/ref/contrib/postgres/search/) PostgreSQL préfère GIN pour la recherche plein texte. [Indexes FTS](https://www.postgresql.org/docs/current/textsearch-indexes.html)
3. **Conserver les opérateurs usuels.** `websearch_to_tsquery` reconnaît phrases entre guillemets, `OR` et exclusion avec `-`, sans erreur de syntaxe de la fonction. Les autres signes ne donnent pas les capacités de `to_tsquery`. Le ranking est spécifique au produit ; un score lexical n'est pas une probabilité. [Contrôle de la recherche PostgreSQL](https://www.postgresql.org/docs/current/textsearch-controls.html)
4. **Tolérance aux fautes, seulement si nécessaire.** `pg_trgm` fournit des indexes GIN/GiST pour similarité et `LIKE`/`ILIKE`. La recherche des plus proches voisins avec distance et `LIMIT` bénéficie de GiST, pas de GIN. Les motifs sans trigrammes exploitables peuvent dégénérer en scan complet de l'index. [Documentation pg_trgm](https://www.postgresql.org/docs/17/pgtrgm.html)
5. **Lire les plans avec prudence.** `EXPLAIN ANALYZE` mesure l'exécution ; les coûts estimés du planner ne sont pas des millisecondes. Un scan séquentiel peut être raisonnable sur un petit catalogue ou une recherche très large. Mesurer aussi l'API entière, car sérialisation et transfert ne sont pas couverts par les coûts du plan. [EXPLAIN PostgreSQL](https://www.postgresql.org/docs/current/using-explain.html)
6. **Normaliser les accents dans le document et dans la requête.** Le dictionnaire `unaccent` retire les diacritiques et développe certaines ligatures. [PostgreSQL unaccent](https://www.postgresql.org/docs/current/unaccent.html) Django précise qu'un simple lookup `unaccent` provoque généralement un scan complet : préférer une normalisation du document indexé. Le lookup `trigram_word_similar` compare le terme à une portion du champ, adapté à un mot mal saisi dans un titre long. [Lookups PostgreSQL Django](https://docs.djangoproject.com/en/5.2/ref/contrib/postgres/lookups/)

## 3. Diagnostic du code avant modification

Lecture locale de `jobboard/models/catalogue.py` et `jobboard/services/catalogue_search.py` le 1 octobre :

- `Offer.search_vector` est généré et persisté sur titre (A) + description (B), avec `offer_search_idx` GIN.
- `search_offers` filtre actuellement le vecteur **concaténé** avec un `SearchVector` calculé depuis `company__name`, puis calcule le classement titre/entreprise.
- Des alias métier multilingues et les opérateurs websearch existent déjà ; catalogue et recherches enregistrées partagent ce service.

**Inférence technique à confirmer par plan :** le GIN sur `search_vector` seul ne correspond pas à l'expression concaténée avec l'entreprise. Cela peut obliger la base à recalculer et filtrer un document pour chaque offre. Préserver le support des recherches mixtes comme `Bosch software` pendant toute réécriture. Un simple OR entre « document contient toute la requête » et « entreprise contient toute la requête » manquerait les termes distribués entre ces champs.

## 4. Priorités adaptées à ce dépôt

Ces décisions sont **nos recommandations**, pas des performances promises par les concurrents.

| Priorité | Travail | Preuve attendue |
|---|---|---|
| P0 | Réécrire le chemin FTS pour utiliser un document persisté/indexé intégrant l'entreprise, ou une présélection indexable conservant la sémantique du document complet. Prévoir changement de nom d'entreprise et toutes les voies d'import. | Plan avant/après sur corpus synthétique représentatif ; tests recherche métier, entreprise, mixte et renommage. |
| P0 | Garder un ordre déterministe : pertinence, publication, identifiant. Conserver phrases/OR/exclusions et alias avec expansion bornée. | Résultats attendus et pagination stable, y compris guillemets, `or`, termes négatifs et requêtes très longues. |
| P0 | Supprimer calculs redondants/N+1 dans cartes, détail et recommandations ; séparer requête de filtrage et coût du classement. | Nombre de requêtes borné par page, latence API froide/chaude et SQL, aucune offre hors périmètre. |
| P1 | Réduire les requêtes de frappe avec debounce, annulation et protection contre réponses obsolètes ; afficher clairement filtres et tri actifs. | Une requête utile après une frappe rapide, la dernière recherche reste affichée, clavier et mobile vérifiés. |
| P1 | Ajouter tolérance aux fautes ou suggestions explicites quand aucun résultat exact ne répond ; préserver les filtres d'éligibilité. | Cas `sofware`, requête courte, multi-mots, exclusion et zero-result ; benchmark du fallback. |
| P1 | Mesurer la qualité sur un jeu jugé manuellement de requêtes multilingues, entreprises, métiers, compétences et exclusions ; suivre pertinence des premiers résultats et rappels des offres attendues. | Jeu et résultats conservés dans le dépôt, aucune métrique assimilée à un taux d'embauche. |

**Choix de coût :** commencer par PostgreSQL et Django présents. Aucun moteur hébergé, embedding, LLM ou dépendance payante n'est nécessaire pour corriger le chemin lexical actuel. Reconsidérer une infrastructure distincte seulement si les mesures montrent une limite après ces corrections.

La vitesse doit être rapportée avec taille du corpus, machine, état du cache, percentile et requête. Ne pas présenter un test local comme un SLA de production. Cache éventuel : inclure filtres, tri, page et version du catalogue dans la clé ; ne jamais partager une réponse personnalisée entre utilisateurs.

## 5. Vérification locale après implémentation

Le diagnostic du vecteur concaténé a été confirmé par `EXPLAIN ANALYZE` sur 11 247 offres : scan séquentiel, 104 ms pour la sélection Python complète. La V2 utilise un document stocké incluant l'entreprise, maintenu par triggers, et son GIN est effectivement utilisé. Les API de référence passent d'environ 214–243 ms à 31–44 ms en médiane locale à chaud. Les tests conservent recherches mixtes, opérateurs, périmètre des publications et isolation des recommandations.

La [spec implémentée](../moteur/SEARCH_ENGINE_SPEC.md) contient les choix précis et limites ; les mesures brutes (`search-engine-benchmark-2026-10-01.json`, export historique supprimé ; voir la [note sur les exports](README.md)) permettent de vérifier les chiffres. Les recommandations de la section 4 restent une liste de possibilités : cette livraison implémente celles retenues dans la spec, pas toutes les pistes de recherche.
