# Migration de l’API vers Django REST framework

## Objectif et périmètre

Remplacer la couche HTTP Django artisanale par DRF : Request/Response, vues,
authentification, permissions, parsers, serializers, pagination et exceptions.
Conserver les modèles, migrations, transactions, services, connecteurs et worker.
Les endpoints santé et l’administration restent des vues Django.

## Recommandations vérifiées

Sources officielles consultées le 30 septembre 2026 :

- [Vues DRF](https://www.django-rest-framework.org/api-guide/views/) : les vues
  fonctionnelles `api_view` utilisent le même cycle de traitement que les APIView.
  Elles conviennent aux actions métier existantes ; aucun CRUD générique ne doit
  permettre de modifier directement une révision, une autorisation ou un run.
- [Serializers](https://www.django-rest-framework.org/api-guide/serializers/) :
  déclarer explicitement les champs exposés. Séparer validation HTTP et opérations
  transactionnelles ; les sauvegardes passent toujours par les services existants.
- [Authentification](https://www.django-rest-framework.org/api-guide/authentication/) :
  SessionAuthentication convient au frontend sous le même domaine. DRF ne vérifie
  normalement CSRF que pour les utilisateurs authentifiés : étendre cette vérification
  aux requêtes anonymes, notamment inscription, connexion et réinitialisation.
- [Permissions](https://www.django-rest-framework.org/api-guide/permissions/) :
  authentification obligatoire par défaut et filtrage explicite des collections par
  propriétaire ; les permissions objet ne filtrent pas automatiquement les listes.
- [Pagination](https://www.django-rest-framework.org/api-guide/pagination/) et
  [exceptions](https://www.django-rest-framework.org/api-guide/exceptions/) :
  personnaliser les classes DRF pour préserver le contrat public existant.
- [Throttling](https://www.django-rest-framework.org/api-guide/throttling/) : les
  compteurs intégrés peuvent dépasser leur limite sous concurrence ; conserver le
  compteur atomique PostgreSQL existant pour les opérations d’authentification.

## Contrat à préserver

- URLs `/api/v1/`, méthodes, statuts métier et clés JSON de `docs/backend/API.md`.
- Erreurs `{error: {code, message, details}}`, 401 sans session, 403 pour CSRF.
- Sessions Django, rotation à la connexion et après changement de mot de passe.
- JSON strict : objet seulement, champs inconnus/interdits refusés, NaN refusé,
  aucun assouplissement implicite des types ; validation métier finale inchangée.
- Pagination `{results,count,page,page_size}`, défaut 20, maximum 100, refus des
  tailles excessives et des pages inexistantes.
- Dates et décimaux encodés comme auparavant via DjangoJSONEncoder.
- Upload multipart limité à un fichier et un kind ; téléchargements privés en streaming.
- Cache-Control no-store sur l’API, y compris erreurs ; pas de nouvelle exposition
  des clés de stockage, secrets, payloads des fournisseurs ou jetons du worker.
- Préférences PUT partiel et suppressions 200/204 existantes conservés.

DRF ajoute OPTIONS et la négociation de contenu (406 pour un format non proposé).
Les téléchargements PDF/ZIP conservent leur négociation fichier ; leurs erreurs
restent JSON. L’API reste JSON ; pas de Browsable API ni de nouvelle authentification Basic/JWT.

## Implémentation

1. Ajouter et verrouiller DRF dans pyproject.toml/uv.lock ; config globale restrictive.
2. Introduire authentification de session avec CSRF anonyme, exception handler,
   renderer de compatibilité, pagination DRF et middleware no-store.
3. Introduire serializers explicites pour les commandes d’authentification et de
   candidature, ainsi que serializers de saisie des profils et ressources enfants.
   Les services conservent leurs validations afin de protéger aussi les appels worker.
4. Migrer les vues API vers api_view (APIView pour les téléchargements), Request.data et Response ; supprimer
   le décorateur endpoint, le parsing JSON manuel et le paginateur Django artisanal.
5. Actualiser la documentation et ajouter les tests spécifiques aux différences DRF.

## Critères d’acceptation

- Tous les endpoints API v1 sont des vues DRF ; aucune modification du schéma DB.
- Suite de 109 tests existante verte, sans affaiblir ses assertions.
- Tests de non-régression : CSRF anonyme/authentifié, accès privé, erreurs de parsing,
  champs inconnus, types, négociation, OPTIONS, no-store et pagination stricte.
- Tests de serializers et contrôle de non-exposition des champs privés.
- `manage.py check`, `makemigrations --check --dry-run`, Ruff et tests PostgreSQL.

## Déploiement et retour arrière

Livrer le code et le lockfile ensemble, reconstruire l’image. Aucune migration de
base n’est nécessaire ; retour arrière par restauration de l’image précédente.
Les connecteurs ATS restent désactivés sans configuration partenaire explicite.
