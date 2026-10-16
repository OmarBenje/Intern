# Domaines et sous-domaines — livraison locale

Date : 1 octobre 2026. Nomenclature `job-taxonomy-1`, classificateur `job-taxonomy-1-rules3`. Recherche initiale : [comparatif, nomenclature et UX](../research/job-taxonomy-ux-2026-10-01.md), [référentiels officiels](../research/job-taxonomy-sources-2026-10-01.md).

## Comportement livré

- Référentiel partagé en base : **24 domaines, 229 sous-domaines**. Il reprend les 206 entrées proposées, dont Développement logiciel généraliste, et ajoute 23 généralistes. Soit 205 spécialités et 24 généralistes. Les libellés sont français et les slugs anglais ; les alias comprennent des intitulés français, anglais et certains intitulés allemands et autres langues. Le dictionnaire n’est pas exhaustif pour chaque langue européenne.
- Filtre « Domaines et métiers » : groupes repliables, recherche par nom/alias, plusieurs cases à cocher, domaine entier et état parent mixte, compteurs, badges supprimables, URL persistante et retour navigateur. L’application réinitialise la pagination, conserve les autres critères et restaure le focus.
- Un même domaine ou plusieurs spécialités se combinent par **OU** ; les autres facettes se combinent par **ET**. Un parent couvre ses descendants, y compris le généraliste. Un parent et son enfant sont simplifiés ; des enfants de parents différents restent des alternatives valides.
- API de vocabulaire et facettes : `GET /api/v1/taxonomy/`. Les comptes sont calculés sur le même catalogue publiable et frais que les résultats, avec les autres filtres actifs et sans la sélection métier courante. Les associations secondaires ne multiplient ni cartes ni totaux.
- Cartes d’offres : spécialité principale affichée. Détail : chemin domaine → sous-domaine et état de revue. Les preuves sont disponibles dans la réponse détaillée `taxonomy.evidence`.
- Profil : mêmes choix de domaines et de spécialités, plus spécialités à exclure. Les préférences de contrat et de mode de travail existantes sont conservées. Les recommandations utilisent la spécialité avant le parent, exposent leurs raisons et appliquent les exclusions avant pagination. Le classement `preferences-taxonomy-2` ajoute 16 points pour une spécialité et 8 pour un domaine ; ces poids sont des paramètres initiaux, pas une qualité de matching mesurée.
- Les filtres historiques `domain` et les recherches existantes sont conservés. Ils ne se combinent pas avec `domains/subdomains` ; le sélecteur de métiers retire le filtre historique quand il remplace ce choix. Aucune conversion silencieuse des anciennes préférences ni suppression de `Role`.

## Classement des offres

`Offer.job_subdomain` contient le principal, `secondary_subdomains` les fonctions transversales prouvées. Les états sont `classified`, `broad`, `needs_review`, `unclassified`. Les filtres métiers précis incluent seulement les deux premiers états. Les offres ambiguës restent accessibles à la recherche libre et au catalogue général ; elles ne reçoivent pas de bonus métier.

Le classificateur hors ligne reconnaît des expressions métier dans le titre. Il traite les intitulés composés et les fonctions secondaires explicitement reliées dans le titre ; un suffixe décrivant le projet ne remplace pas une fonction principale précise. Les compétences accessoires et le secteur de l’employeur ne suffisent pas à choisir un métier. Pour spécialiser un titre généraliste, la description doit fournir des missions correspondantes. Un titre non identifié nécessite plusieurs phrases concordantes dans une section de responsabilités identifiée.

La projection conserve méthode, version, empreinte d’entrée, extraits et, lorsqu’une correspondance est trouvée, révision source. Elle est appelée lors de l’enrichissement, même si la projection d’éligibilité n’a pas changé. Aucun appel IA ou réseau n’est ajouté aux recherches. Il n’y a pas de référentiel ESCO/ROME importé ni de filtre secteur d’entreprise dans cette livraison : les liens officiels préparent des mappings ultérieurs.

L’admin permet de corriger le principal et les secondaires avec ses permissions catalogue existantes. Une correction devient manuelle et les imports la conservent ; si le texte change, elle passe en revue sans être remplacée. Aucun endpoint candidat ne modifie le classement partagé. La correction doit être réexaminée explicitement dans l’admin.

## Migration et reprise

Migration additive `0028_job_taxonomy`, après les migrations locales de descriptions, recherche, logos et file ATS. Elle crée les modèles, relations, contraintes et vocabulaire. Le fichier `jobboard/data/job-taxonomy-v1.json` est la source commune ; conserver cette version pour les anciennes migrations et créer un nouveau fichier/version pour une évolution future.

Depuis la racine :

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py classify_job_taxonomy --dry-run
python manage.py classify_job_taxonomy
```

La commande travaille offre par offre sous transaction ; elle est réexécutable et affiche le dernier ID traité. `--after-id N` reprend au-delà d’un ID, `--limit N` borne le lot, `--all` vérifie également les empreintes déjà traitées. Sans `--all`, seules les autres versions et les corrections manuelles sont vérifiées. Le mode à blanc n’écrit rien. Les révisions source et les domaines historiques restent conservés. Une nouvelle version des règles implique un nouveau suffixe de version pour reclasser le corpus.

Les collecteurs Python persistants doivent être relancés lors d’un changement des règles : ils peuvent garder leurs anciens modules en mémoire. Les trois collecteurs locaux catalogue, NAV et ATS ont été relancés avec leurs paramètres précédents (limite 1, intervalles respectifs 30/10/60 s). Leurs files et leases restent conservés ; les leases interrompues peuvent attendre leur expiration avant reprise.

Retour arrière : revenir au code antérieur puis migrer vers `0027`. Les nouvelles relations et corrections de taxonomie sont supprimées ; exporter ces tables avant ce retour si elles doivent être gardées. Le catalogue, les révisions source, les rôles et les domaines historiques subsistent. Aucun déploiement production, commit ni push effectué pour cette livraison.

## Vérification

- Suite backend complète : 451 tests passent sur `test_intern_taxonomy`. Après la dernière restriction du fallback par description, 58 tests ciblant taxonomie, enrichissement, recherche, recommandations et contrat API passent.
- Navigateur : 34 tests de recherche, filtres, détail, pagination et profil passent ; un test supplémentaire vérifie ensuite la sauvegarde des spécialités et exclusions sans perte des contrats. Les quatre tests dédiés à la taxonomie passent.
- Build frontend, contrôles des tokens, lint frontend sans erreur, Ruff des nouveaux modules, contrôles Django et absence de migration manquante. Les avertissements Fast Refresh du fichier historique `EngineControls.tsx` subsistent.
- Vérification visuelle du sélecteur à 320 px ; navigation clavier, Échap, annulation, restauration du focus, réponses obsolètes et panne de vocabulaire vérifiées. Les tests navigateur utilisent des fixtures publiques simulées ; les lectures HTTP réelles du catalogue local sont vérifiées séparément.
- API locale et frontend relancés sur 8000 et 5173 ; catalogue et facettes répondent 200, avec `Cache-Control: no-store` côté API. Bilan et mesures locales (`job-taxonomy-validation-2026-10-01.json`, export historique supprimé ; voir la [note sur les exports](../research/README.md)).

Les collecteurs modifient le corpus pendant les mesures. La couverture du classement n’établit ni sa précision ni son rappel. Les règles restent conservatrices et les cas non identifiés restent à classer ; le protocole d’annotation indépendant proposé dans la recherche demeure nécessaire avant d’annoncer un taux de précision ou un gain UX chiffré.
