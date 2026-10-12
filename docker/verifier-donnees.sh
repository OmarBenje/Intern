#!/bin/sh
# Depuis la racine d'Intern. Lecture seule ; aucun secret affiché.
set -eu

dc() {
    docker compose --env-file docker/.env -f docker/compose.yaml "$@"
}

result=$(dc exec -T donnees sh -c 'psql -X -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT (SELECT count(*) FROM auth_user),
       (SELECT count(*) FROM jobboard_company),
       (SELECT count(*) FROM jobboard_offer),
       (SELECT count(*) FROM jobboard_application),
       (SELECT count(*) FROM auth_user WHERE username = 'attente' AND NOT is_active);
SQL
)
if [ "$result" != '8|3|4|2|1' ]; then
    printf 'ÉCHEC : effectifs observés %s ; attendus 8|3|4|2|1\n' "$result" >&2
    exit 1
fi
printf 'PASS : 8 comptes, 3 entreprises, 4 stages, 2 candidatures, attente inactif\n'
dc exec -T donnees sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < donnees/requetes.sql
