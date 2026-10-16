etape_17() {
  local action=${1:-verifier}
  case "$action" in
    verifier)
      python3 mesure/scripts/verifier17.py
      cat mesure/resultats/etape17/verification.json
      return ;;
    statut|arreter)
      vm_workspace
      local runtime=${MESURE_RUNTIME:-$PWD/../.execution-campagnes}
      test -f "$runtime/configuration.json" || fail 'Campagne non configurée : utiliser l’action preparer.'
      if [[ $action == statut ]]; then
        python3 mesure/scripts/lancer17.py status --runtime "$runtime"
      else
        python3 mesure/scripts/lancer17.py stop --runtime "$runtime"
      fi
      return ;;
    preparer|lancer) ;;
    *) bad_action "$action" ;;
  esac
  export MESURE_RUNTIME="${MESURE_RUNTIME:-$PWD/../.execution-campagnes}"
  python3 outils/configurer_campagne.py --verifier-lancement
  vm_deploy
  engine_ready
  jmeter_ready
  export DOCKER_ENV_FILE="${DOCKER_ENV_FILE:-$PWD/docker/.env}"
  # Prepare secrets/images if absent; do not bind 8080 while the VMs use it.
  export EXECUTION_PROJECT=intern-mesure EXECUTION_MESURE=1
  bash outils/demarrer_docker.sh donnees
  if ! "$DOCKER_BIN" image inspect intern-metier:etape12 >/dev/null 2>&1; then
    "$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml -f mesure/compose.test.yaml -p intern-mesure build metier
  fi
  if ! "$DOCKER_BIN" image inspect intern-proxy:etape13 >/dev/null 2>&1; then
    "$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml -f mesure/compose.test.yaml -p intern-mesure build proxy
  fi
  export MESURE_SSH_CONFIG="$VM_WORK/access/ssh-etape8-interne.conf"
  export MESURE_RUNTIME="${MESURE_RUNTIME:-$PWD/../.execution-campagnes}"
  export MESURE_OUTPUT="${MESURE_OUTPUT:-$PWD/mesure/resultats/nouvelle-campagne}"
  export MESURE_REFERENCE_PROJECT="${MESURE_REFERENCE_PROJECT:-intern-docker}"
  export DOCKER_CONFIG="${DOCKER_CONFIG:-$HOME/.docker}"
  # Respect the selected Docker context instead of assuming /var/run/docker.sock.
  if [[ -z ${DOCKER_HOST:-} ]]; then
    DOCKER_HOST=$("$DOCKER_BIN" context inspect --format '{{.Endpoints.docker.Host}}')
    export DOCKER_HOST
  fi
  export DOCKER_BIN="$(command -v "$DOCKER_BIN")"
  python3 outils/configurer_campagne.py
  if [[ $action == lancer ]]; then
    python3 outils/configurer_campagne.py --verifier-lancement
    python3 mesure/scripts/lancer17.py start --runtime "$MESURE_RUNTIME"
  fi
  python3 mesure/scripts/lancer17.py status --runtime "$MESURE_RUNTIME"
}
