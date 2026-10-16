etape_15() {
  local action=${1:-preparer}
  case "$action" in preparer|gui|gui-echec|cli|tout) ;; *) bad_action "$action" ;; esac
  if [[ $action == gui || $action == gui-echec || $action == tout ]]; then
    [[ -n ${DISPLAY:-}${WAYLAND_DISPLAY:-} ]] || fail 'Une session graphique est nécessaire pour JMeter GUI.'
  fi
  measure_prepare
  if [[ $action == gui || $action == tout ]]; then
    echo 'Exécuter une itération dans JMeter, puis fermer la fenêtre pour continuer.'
    (cd mesure && "$JMETER_BIN" -t plan.jmx -Jport=8081)
  fi
  if [[ $action == gui-echec || $action == tout ]]; then
    echo 'Exécuter le cas de mot de passe incorrect, puis fermer la fenêtre.'
    (cd mesure && "$JMETER_BIN" -t plan.jmx -Jport=8081 -Jmot_de_passe=incorrect)
  fi
  if [[ $action == cli || $action == tout ]]; then
    local output=${MESURE15_OUTPUT:-mesure/resultats/essai-execution15-$(date +%Y%m%d-%H%M%S)-$$}
    # Refuse reuse even if the old directory is empty.
    [[ ! -e $output ]] || fail "Résultats déjà présents : $output. Choisir MESURE15_OUTPUT neuf."
    mkdir -p "$output"
    output=$(cd "$output" && pwd)
    (cd mesure && "$JMETER_BIN" -n -t plan.jmx -Jport=8081 -l "$output/reussite.jtl" -j "$output/reussite.log")
    (cd mesure && "$JMETER_BIN" -n -t plan.jmx -Jport=8081 -Jmot_de_passe=incorrect -l "$output/echec.jtl" -j "$output/echec.log")
    echo "Résultats : $output"
  fi
}
