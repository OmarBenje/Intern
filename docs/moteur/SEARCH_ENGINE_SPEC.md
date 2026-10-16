# Recherche et recommandations — V2

Date : 1 octobre 2026. Statut : implémenté et vérifié en local. Périmètre : catalogue candidat, recherches sauvegardées et API de recommandations.

## Problème et preuves

Le catalogue reconstruit `search_vector || to_tsvector(company.name)` dans le WHERE. L'index GIN existant ne couvre pas cette expression. Sur la base locale de 11 247 offres (7 145 publiables), `EXPLAIN ANALYZE` montre une lecture séquentielle et 104 ms pour la sélection complète « Python ». Les médianes API à chaud, cinq mesures après échauffement, page de 36 : Python 242 ms, stage développeur 243 ms, Bosch software 214 ms, catalogue sans mot-clé 88 ms. Ces chiffres sont locaux, sans charge concurrente, et les collecteurs peuvent modifier le corpus.

Les recommandations filtrent contrats, modes, exclusions et salaire, mais ne classent pas les résultats selon les métiers, lieux ou compétences. Les raisons sont calculées après pagination. La recherche `C++` est actuellement tokenisée comme `C`, ce qui mélange des technologies différentes.

La [recherche concurrentielle et technique](../research/search-engine-2026-10-01.md) décrit les références et leurs sources officielles. WTTJ et JobTeaser confirment l'intérêt des critères explicites et du profil ; Simplify distingue catalogue et matches personnalisés et explique les raisons. Leurs algorithmes privés et leurs performances ne sont pas connus. L'ADR-001 reste applicable : PostgreSQL, matching structuré, pas de service vectoriel nécessaire.

## Comportement attendu

1. Rechercher titre, entreprise et description avec un document pondéré stocké : titre/entreprise A, description C. Utiliser directement son index GIN ; calculer le rang uniquement sur les candidats sélectionnés. Aucun appel réseau ni modèle IA pendant une recherche.
2. Normaliser accents et casse des deux côtés, et conserver C++, C# et .NET comme technologies distinctes via `cpp`, `csharp`, `dotnet`. Étendre les synonymes validés développeur logiciel / software engineer avec « développeuse », « développeur logiciel », « software development », « SWE ». Conserver AND entre critères, phrases entre guillemets, OR et exclusions. Une requête vide ou composée de ponctuation ne provoque pas d'erreur serveur.
3. Synchroniser le document sur INSERT/UPDATE d'offre et renommage d'entreprise, y compris bulk_create, QuerySet.update et SQL direct. Migration avec backfill des offres existantes. Les champs d'index sont internes, absents de l'API.
4. Si la recherche ne retourne rien, proposer jusqu'à trois titres proches, issus du même catalogue filtré, via `GET offers/suggestions/?q=...`. Recherche trigramme indexée, requêtes simples seulement (au moins trois caractères alphanumériques, au plus 100 caractères et huit mots), pas de correction automatique des opérateurs. Le clic remplace le mot-clé et revient à la page 1 en conservant les filtres. Pas d'appel de suggestions pour les résultats non vides ; une panne des suggestions conserve l'état vide fonctionnel.
5. Classer les recommandations avant pagination avec des critères explicites : métier +12, lieu +8, compétence +4 (maximum trois compétences), contrat connu accepté +2, mode connu accepté +2. Ce score sert au classement, ce n'est ni un pourcentage ni une preuve d'éligibilité. Exposer score et version, conserver raisons et compatibilité séparées. Départager par pertinence textuelle puis publication et ID ; `sort=newest` conserve le choix de l'utilisateur.
6. Conserver l'état d'onboarding requis et le catalogue général accessible. Les exclusions et contraintes explicites priment sur le score. Une donnée inconnue n'ajoute pas de bonus. Aucune inférence de nationalité, de sponsoring ou de compétence depuis la prose du CV.

## Performance et contraintes

- Préserver le périmètre des stages confirmés en Europe, ouverts, non expirés et avec une source fraîche active. Les suggestions respectent aussi ces règles et les filtres.
- Conserver le contrat de pagination et ses totaux exacts ; éviter DISTINCT et le transport de description/documents d'index/contenu enrichi dans les listes lorsque les jointures ne multiplient pas les lignes.
- Supprimer les requêtes par offre dans l'évaluation des autorisations de travail en préchargeant les confirmations du profil une seule fois.
- Garder `Cache-Control: no-store`, sans cache partagé de résultats personnalisés ou risque de péremption des sources. Réutiliser le serializer dans une page, sans modifier les champs de réponse.
- Cible locale : réduire d'au moins 50 % la médiane des trois recherches de référence, avec un objectif de 150 ms à chaud. Documenter résultats observés et limites ; aucune garantie de latence production à partir d'un benchmark local.
- Fournir une commande de benchmark reproductible, en lecture seule, avec échauffement, médiane/p95, nombre de requêtes SQL et EXPLAIN optionnel. Ne jamais journaliser CV, sessions ou identifiants privés.

## Validation et livraison

Tests PostgreSQL : renommage/SQL bulk, accents, tokens techniques distincts, alias avec termes obligatoires, opérateurs/ponctuation, rang titre > description, suggestions filtrées/fraîches et bornées, classement personnalisé avant pagination, tri récent, inconnues, exclusions et nombre de requêtes stable entre pages de 1 et 20 offres. Vérifier que le GIN est utilisable avec EXPLAIN (le planificateur peut préférer une lecture séquentielle sur les petits corpus).

Frontend : clic suggestion au clavier, filtres préservés, page réinitialisée, réponses obsolètes ignorées, panne silencieuse des suggestions. Build, lint et tests des filtres/pagination existants.

Migration additive `0025` : extensions PostgreSQL `unaccent` et `pg_trgm`, champs d'index, fonctions/triggers et index. En production, prévoir les droits d'installation des extensions et une fenêtre de migration pour le backfill/index ; cette V2 vise le volume actuel. Le retour arrière retire champs/fonctions/triggers/index de V2, conserve les extensions partagées et le vecteur V1 ; revenir aussi au code V1. Les modifications locales d'enrichissement des descriptions sont préservées.

## Hors périmètre

Embeddings, moteur SaaS, apprentissage du classement, personnalisation implicite par clic, suggestions de mots pendant la saisie, nouveaux collecteurs et refonte des écrans. Ces options nécessitent des évaluations de pertinence et des mesures de charge supplémentaires.

## Résultats vérifiés

La migration `0025` est appliquée sur la base locale. L'API réelle sur le port 8000 répond 200 pour la recherche et les suggestions ; le frontend sur 5173 répond 200. `EXPLAIN ANALYZE` utilise `offer_document_idx` sur les recherches de référence. Les synonymes sont préparés par des sous-requêtes non corrélées, pour éviter de normaliser et parser chaque alternative pour chaque offre classée.

Corpus identique de 11 247 offres, dont 7 145 publiables. Une mesure d'échauffement, puis cinq mesures API par requête, page de 36, sans simulation de charge concurrente :

| Requête | Médiane avant | Médiane après | Gain |
|---|---:|---:|---:|
| Sans mot-clé | 88,30 ms | 40,88 ms | 2,16× |
| Python | 242,15 ms | 39,32 ms | 6,16× |
| stage développeur | 242,57 ms | 44,25 ms | 5,48× |
| Bosch software | 214,00 ms | 30,87 ms | 6,93× |
| C++ | 265,86 ms | 25,67 ms | 10,36× |
| développement | 293,22 ms | 45,54 ms | 6,44× |

Les temps varient sur la machine partagée. Le résultat n'est pas un SLA. Les comptes Python (616) et Bosch software (97) restent identiques ; stage développeur passe de 360 à 384 avec les nouveaux alias. C++ passe de 786 à 108 parce que son token est désormais distinct de C ; cela ne constitue pas à lui seul une mesure de précision ou de rappel. La sélection SQL Python complète passe de 104 à environ 10 ms lors de la vérification du plan.

Mesures brutes, p95, comptes SQL et noms des index (`search-engine-benchmark-2026-10-01.json`, export historique supprimé ; voir la [note sur les exports](../research/README.md)). Chaque liste publique nécessite six requêtes SQL, indépendamment de la taille de la page. Les tests vérifient également un nombre constant de requêtes pour les recommandations et leurs autorisations de travail.

Validation finale : 407 tests backend passent sur une base PostgreSQL dédiée ; les 15 tests navigateur ciblant filtres, pagination et suggestions passent. Build frontend, contrôles des tokens, contrôles Django, absence de dérive des migrations, lint des fichiers modifiés et vérification du diff passent. Le lint frontend signale trois avertissements Fast Refresh existants. Le lint backend global relève des erreurs préexistantes hors de ces changements (anciennes migrations, imports et fichiers d'enrichissement) ; elles sont conservées avec le travail local déjà présent.

Reproduire les mesures depuis la racine :

```bash
source .venv/bin/activate
python manage.py benchmark_search --samples 10 --explain
python manage.py benchmark_search --query Python --query 'stage développeur' --samples 5
```

La commande effectue des lectures et renvoie le JSON sur stdout ; elle ne crée pas de profil ni d'offres. L'affichage mobile des suggestions a été inspecté à 320 px ; clavier, conservation des filtres et réponses obsolètes sont couverts par les tests navigateur.
