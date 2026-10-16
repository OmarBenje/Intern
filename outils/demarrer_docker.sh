#!/usr/bin/env bash
# Start missing course Compose services, never recreate a live container.
set -euo pipefail
cd "$(dirname "$0")/.."
export DOCKER_BIN="${DOCKER_BIN:-docker}"
export DOCKER_ENV_FILE="${DOCKER_ENV_FILE:-docker/.env}"
export EXECUTION_PROJECT="${EXECUTION_PROJECT:-intern-docker}"
layer="${1:-proxy}"
case "$layer" in donnees|metier|proxy) ;; *) echo 'Usage : bash outils/demarrer_docker.sh [donnees|metier|proxy]' >&2; exit 1 ;; esac
if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  echo 'Docker Engine arrêté ou inaccessible : voir EXECUTION.md.' >&2
  exit 1
fi
if "$DOCKER_BIN" info --format '{{.ServerVersion}}' | grep -qi podman; then
  echo 'Utiliser Docker Engine natif.' >&2; exit 1
fi
if [ ! -f "$DOCKER_ENV_FILE" ]; then
  umask 077
  python3 - "$DOCKER_ENV_FILE" <<'PY'
from pathlib import Path
import secrets, sys
path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
with path.open('x') as stream:
    stream.write('POSTGRES_DB=intern\nPOSTGRES_USER=intern_user\n'
                 + 'POSTGRES_PASSWORD=' + secrets.token_urlsafe(32) + '\n'
                 + 'DJANGO_SECRET_KEY=' + secrets.token_urlsafe(64) + '\n')
PY
fi
dc() {
  local files=(-f docker/compose.yaml)
  if [ "${EXECUTION_MESURE:-0}" = 1 ]; then files+=(-f mesure/compose.test.yaml); fi
  "$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" "${files[@]}" -p "$EXECUTION_PROJECT" "$@"
}
dc config --quiet
if [ "$layer" != donnees ]; then
  if ! "$DOCKER_BIN" image inspect intern-metier:etape12 >/dev/null 2>&1; then dc build metier; fi
fi
if [ "$layer" = proxy ]; then
  if ! "$DOCKER_BIN" image inspect intern-proxy:etape13 >/dev/null 2>&1; then dc build proxy; fi
fi
# Compose's --no-recreate also starts stopped containers and creates missing ones.
# It does not restart running containers, including ones whose health is pending.
dc up -d --no-build --no-recreate --wait --wait-timeout 180 "$layer"
dc ps
