#!/bin/sh
# Depuis la racine d'Intern, après le démarrage des deux services.
set -eu
dc() {
    docker compose --env-file docker/.env -f docker/compose.yaml "$@"
}
dc exec -T metier .venv/bin/python -c 'import os, socket, urllib.request; assert os.environ["POSTGRES_HOST"] == "donnees"; print("DNS donnees:", socket.gethostbyname("donnees")); print("Disponibilité API:", urllib.request.urlopen("http://127.0.0.1:8000/health/ready/", timeout=5).read().decode())'
dc exec -T metier sh -c '
    export PGHOST="$POSTGRES_HOST" PGPORT="$POSTGRES_PORT"
    export PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB" PGPASSWORD="$POSTGRES_PASSWORD"
    exec .venv/bin/python /app/donnees/verifier.py
'
