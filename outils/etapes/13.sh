etape_13() {
  case ${1:-demarrer} in
    demarrer)
      course_docker proxy
      curl --fail http://127.0.0.1:8080/health/ready/
      python3 outils/ouvrir.py http://127.0.0.1:8080/login
      ;;
    *) bad_action "$1" ;;
  esac
}
