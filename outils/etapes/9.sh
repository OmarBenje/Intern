etape_9() {
  case ${1:-demarrer} in
    demarrer) vm_deploy; python3 outils/ouvrir.py http://127.0.0.1:8080/login ;;
    *) bad_action "$1" ;;
  esac
}
