etape_14() {
  case ${1:-consulter} in
    consulter) python3 outils/ouvrir.py docs/compte_rendu_comparaison.pdf ;;
    demarrer)
      course_docker proxy
      curl --fail http://127.0.0.1:8080/health/ready/
      python3 outils/ouvrir.py http://127.0.0.1:8080/login
      ;;
    mesurer)
      export EXECUTION_PROJECT="${EXECUTION_PROJECT:-intern-verification}"
      [[ $EXECUTION_PROJECT != intern-docker && $EXECUTION_PROJECT != intern-mesure ]] || fail 'Choisir un projet dédié avec EXECUTION_PROJECT pour cette mesure.'
      course_docker proxy
      mkdir -p .execution
      if [[ -z ${DOCKER_PIDFILE:-} ]]; then
        if [[ -n ${DOCKER_ENGINE_RUNTIME:-} ]]; then
          export DOCKER_PIDFILE="$DOCKER_ENGINE_RUNTIME/docker.pid"
        else
          systemctl show docker.service -p MainPID --value > .execution/docker-engine.pid
          export DOCKER_PIDFILE="$PWD/.execution/docker-engine.pid"
        fi
      fi
      test -f "$DOCKER_PIDFILE"
      local pid
      pid=$(cat "$DOCKER_PIDFILE")
      [[ $pid =~ ^[0-9]+$ && $pid -gt 0 ]] || fail 'PID du moteur invalide.'
      [[ $(cat "/proc/$pid/comm") == dockerd ]] || fail 'Le PID fourni ne désigne pas dockerd.'
      backup_reports 14 docker/docs docs/comparaison.md docs/compte_rendu_comparaison.pdf
      local command=(python3 docker/verifier-etape14.py --docker "$DOCKER_BIN"
        --env-file "$DOCKER_ENV_FILE" --project "$EXECUTION_PROJECT" --engine-pidfile "$DOCKER_PIDFILE")
      if [[ -n ${DOCKER_ENGINE_RUNTIME:-} ]]; then
        nsenter -t "$pid" -U -m --wd="$PWD" -- "${command[@]}"
      else
        "${command[@]}"
      fi
      python3 docker/rediger-comparaison.py
      test -x .execution/docs/bin/python || python3 -m venv .execution/docs
      .execution/docs/bin/pip install -r analyse/requirements-docs.txt
      .execution/docs/bin/python docker/generer-comparaison.py
      python3 outils/ouvrir.py docs/compte_rendu_comparaison.pdf
      ;;
    *) bad_action "$1" ;;
  esac
}
