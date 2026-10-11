#!/usr/bin/env bash
# Create a new dedicated database, restore the SQL and verify the dataset.
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(dirname -- "$script_dir")"
cd -- "$project_dir"

export PGHOST="${PGHOST:-127.0.0.1}"
export PGPORT="${PGPORT:-5433}"
export PGUSER="${PGUSER:-intern_user}"
export PGDATABASE="${PGDATABASE:-intern_dev3}"

for tool in createdb psql; do
    command -v "$tool" >/dev/null || {
        printf '%s\n' "Commande requise : $tool" >&2
        exit 1
    }
done
if [[ ! -x metier/.venv/bin/python ]]; then
    printf '%s\n' "Installer les dépendances Python : uv sync --project metier --frozen" >&2
    exit 1
fi
metier/.venv/bin/python -c 'import psycopg'

printf '%s\n' "Création d'une base dédiée : $PGDATABASE"
# createdb refuses an existing database before any import is attempted.
createdb "$PGDATABASE"
for file in schema data requetes; do
    printf '%s\n' "Exécution de donnees/$file.sql"
    psql -X -v ON_ERROR_STOP=1 -f "donnees/$file.sql"
done
metier/.venv/bin/python donnees/verifier.py
printf '%s\n' "Base prête. Connexion interactive : psql -X" 
