# Livraison backend — 30 septembre 2026

## Livré et vérifié

- API JSON Django REST framework avec sessions, CSRF, reset/changement de mot de passe, limitation partagée PostgreSQL et validation explicite.
- Catalogue filtrable/paginé, favoris, recommandations respectant contrats/modes et comparabilité des salaires ; import public Greenhouse atomique et relançable.
- Profil, parcours, préférences, version ; PDF privés locaux/R2, empreintes et protection des documents historiques.
- Dossiers/révisions immuables par l'API, snapshots factuels, hash canonique, approbation individuelle et outbox atomique.
- Worker avec leases/tokens, contrôles de formulaire/destination/accord, absence de retry automatique après résultat incertain ; adaptateur Greenhouse partenaire configurable.
- Historique, suivi manuel, tâches/entretiens ; export ZIP et suppression reprenable avec protection des opérations encore en vol.
- Configuration d'environnement, image Docker non root, web/worker Compose, healthchecks HTTP, documentation [API](API.md) et [spec](BACKEND_SPEC.md).

## Preuves de la livraison initiale (avant migration DRF)

| Vérification | Résultat |
|---|---|
| `manage.py test jobboard --noinput`, base PostgreSQL isolée `test_intern_complete` | **109 tests réussis**, 15,086 s ; base de test supprimée à la fin |
| Deux approbations concurrentes, deux claims concurrents | Un seul run/outbox ; un seul worker obtient le run |
| Suite historique de migration 0008 → 0014 → rollback → upgrade | Réussie ; teardown rétablit désormais la dernière migration |
| `manage.py check` | Aucun problème |
| `manage.py makemigrations --check --dry-run` | Aucune dérive |
| Ruff sur nouveaux modules, tests et fichiers modifiés | Réussi (`E4,E7,E9,F,I`) |
| `git diff --check` | Réussi |
| `check --deploy --tag security` avec environnement de production temporaire | Aucun problème ; secrets éphémères, pas de modification de la configuration locale |
| `docker compose config --quiet` et construction image `intern-web` | Réussies |
| Démarrage Gunicorn depuis image, connexion PostgreSQL réel | `/health/live/` et `/health/ready/` 200 |
| Contrôles HTTP dans le conteneur | CSRF GET 200, identité anonyme 401, login sans CSRF 403 |

Le conteneur de vérification a été arrêté et supprimé après le contrôle. Aucun worker d'envoi n'a été laissé en marche. Les tests R2/ATS utilisent des doubles contrôlés ; aucun document personnel n'a été envoyé à un tiers.

La seule nouvelle migration est `0015_request_throttle`, table technique de compteurs expirables. Elle est appliquée à la base locale après sauvegarde PostgreSQL : `/Users/omarbenjelloun/.codex/backups/intern-backend-20260930/before-0015.dump`. Les migrations métier et le volume existant ont été conservés.

## Migration DRF — vérifications du 30 septembre 2026

La [spec de migration](DRF_MIGRATION_SPEC.md) documente les recommandations officielles
et le contrat conservé. DRF 3.18.1 est verrouillé dans `uv.lock`.

- Les 109 tests historiques sont passés après remplacement de la couche HTTP.
- Les dix nouveaux tests `jobboard.tests.test_drf_contract` sont passés après les
  derniers ajustements : CSRF anonyme/origine, permissions, parsing, serializers,
  pagination, négociation, uploads, téléchargements et champs privés.
- `manage.py check` et `makemigrations --check --dry-run` ont réussi avant l’incident
  d’environnement décrit ci-dessous ; aucune modification de modèle ou migration.
- Ruff (toutes les règles configurées) et formatage passent sur les fichiers Python
  de la migration ; `git diff --check` passe. Le lint global garde des diagnostics
  préexistants hors périmètre.

La dernière relance combinée des 119 tests a été bloquée avant leur exécution :
macOS a signalé `No space left on device`, puis Docker Desktop/PostgreSQL sont
devenus indisponibles. Elle reste à rejouer après rétablissement de Docker :

```bash
docker compose up -d db
TEST_DATABASE_NAME=test_intern_drf uv run manage.py test jobboard --noinput
```

La migration DRF n’a pas été déployée. Les contrôles Docker de la section précédente
concernent l’image antérieure à cette migration.

## Limites avant activation du produit complet

Le backend applicatif est livré, mais le parcours externe complet n'est pas déclaré validé :

1. **ATS non choisi par l'utilisateur** : adaptateur partenaire Greenhouse disponible mais désactivé sans accès autorisé. Pas d'agent navigateur universel. Formulaires avancés de conformité/localisation/démographie bloqués avant envoi.
2. **Rédaction IA non branchée** : le préparateur reprend les informations confirmées du profil et les pièces choisies. Fournisseur de génération et extraction automatique du CV restent à choisir ; aucun résultat déterministe n'est présenté comme de la rédaction IA.
3. **Services distants non activés** : bucket R2 privé, SMTP et accès ATS nécessitent la configuration réelle et un test d'intégration ciblé.
4. **Déploiement distant non effectué** : HTTPS/proxy, static admin, limites de corps, sauvegarde/restauration et supervision doivent être validés sur l'environnement retenu. Le contrôle de sécurité utilise une configuration de production simulée.
5. **Uploads interrompus et envois incertains** : conservés pour récupération explicite ; ne pas purger des objets encore en cours d'écriture ni relancer un envoi potentiellement réussi. Un opérateur doit vérifier les opérations d'un compte déjà désactivé.

Ces limites distinguent le code et les tests livrés des accès externes et fonctionnalités IA encore nécessaires à la vision complète.
