etape_12() {
  case ${1:-demarrer} in
    demarrer)
      course_docker metier
      "$DOCKER_BIN" image inspect intern-metier:etape12 --format '{{.Size}}'
      "$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml -p "$EXECUTION_PROJECT" \
        exec -T metier .venv/bin/python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/health/ready/").read().decode())'
      ;;
    *) bad_action "$1" ;;
  esac
}
