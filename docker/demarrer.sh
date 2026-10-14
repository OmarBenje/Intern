#!/bin/sh
# Trois services ; commandes exécutables depuis tout répertoire.
set -eu
cd "$(dirname "$0")/.."
dc() {
    docker compose --env-file docker/.env -f docker/compose.yaml "$@"
}
case "${1:-up}" in
    up)
        # Le proxy collecte les statiques depuis l'image métier construite.
        dc build metier
        dc build proxy
        dc up -d --no-build --wait --wait-timeout 180
        ;;
    down) dc down ;;
    restart)
        dc down
        dc up -d --no-build --wait --wait-timeout 180
        ;;
    ps) dc ps ;;
    *) printf 'Usage : sh docker/demarrer.sh [up|down|restart|ps]\n' >&2; exit 2 ;;
esac
