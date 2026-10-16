etape_11() {
  case ${1:-demarrer} in
    demarrer)
      course_docker donnees
      "$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml -p "$EXECUTION_PROJECT" \
        exec -T donnees sh -c 'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM jobboard_offer;"'
      ;;
    *) bad_action "$1" ;;
  esac
}
