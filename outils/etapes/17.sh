etape_17() {
  local action=${1:-verifier}
  if [[ $action == capacite ]]; then
    local stamp
    stamp=$(date +%Y%m%d-%H%M%S)-$$
    export MESURE_RUNTIME="${CAPACITE_RUNTIME:-$PWD/../.execution-campagnes/capacite-$stamp}"
    export MESURE_OUTPUT="${CAPACITE_OUTPUT:-$PWD/mesure/resultats/capacite-$stamp}"
    export MESURE_CAPACITY_PROTOCOL="${CAPACITE_PROTOCOL:-$PWD/mesure/protocole-capacite.json}"
    action=lancer
  fi
  case "$action" in
    verifier)
      python3 mesure/scripts/verifier17.py
      cat mesure/resultats/etape17/verification.json
      return ;;
    statut|arreter|preparer|lancer|nouvelle) ;;
    *) bad_action "$action" ;;
  esac
  if [[ -z ${MESURE_RUNTIME:-} && -f .execution/campagne-active.json ]]; then
    local selection=()
    mapfile -t selection < <(python3 outils/configurer_campagne.py --selection)
    [[ ${#selection[@]} == 2 ]] || fail 'Impossible de lire la campagne sélectionnée.'
    export MESURE_RUNTIME="${selection[0]}"
    export MESURE_OUTPUT="${MESURE_OUTPUT:-${selection[1]}}"
  fi
  export MESURE_RUNTIME="${MESURE_RUNTIME:-$PWD/../.execution-campagnes/active}"
  export MESURE_OUTPUT="${MESURE_OUTPUT:-$PWD/mesure/resultats/campagne}"
  if [[ $action == nouvelle ]]; then
    python3 outils/configurer_campagne.py --nouvelle
    action=preparer
  fi
  case "$action" in
    statut|arreter)
      vm_workspace
      local runtime=$MESURE_RUNTIME
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
  python3 outils/configurer_campagne.py --verifier-lancement
  vm_deploy
  engine_ready
  jmeter_ready
  export DOCKER_ENV_FILE="${DOCKER_ENV_FILE:-$PWD/docker/.env}"
  # Prepare secrets/images if absent; do not bind 8080 while the VMs use it.
  export EXECUTION_PROJECT=intern-mesure EXECUTION_MESURE=1
  bash outils/demarrer_docker.sh donnees
  "$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml -f mesure/compose.test.yaml -p intern-mesure build metier
  if ! "$DOCKER_BIN" image inspect intern-proxy:etape13 >/dev/null 2>&1; then
    "$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml -f mesure/compose.test.yaml -p intern-mesure build proxy
  fi
  export MESURE_SSH_CONFIG="$VM_WORK/access/ssh-etape8-interne.conf"
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
  python3 outils/configurer_campagne.py --activer
  python3 mesure/scripts/lancer17.py status --runtime "$MESURE_RUNTIME"
}
