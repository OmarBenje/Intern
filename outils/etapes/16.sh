etape_16() {
  case ${1:-consulter} in
    consulter) cat mesure/ETAPE16.md ;;
    mesurer)
      local output=${MESURE16_OUTPUT:-mesure/resultats/etape16-$(date +%Y%m%d-%H%M%S)-$$}
      [[ ! -e $output ]] || fail "Résultats déjà présents : $output. Choisir MESURE16_OUTPUT neuf."
      # Reserve a new output directory before starting any load.
      python3 - "$output" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1]).resolve()
if not path.is_relative_to(Path('mesure').resolve()):
    raise SystemExit('MESURE16_OUTPUT doit se trouver dans mesure/.')
path.mkdir(parents=True, exist_ok=False)
PY
      measure_prepare
      measure_isolated
      python3 mesure/scripts/etalonnage.py static --jmeter "$JMETER_BIN" --users 1 --output "$output/statique-1"
      python3 mesure/scripts/etalonnage.py static --jmeter "$JMETER_BIN" --users 20 --output "$output/statique-20"
      python3 mesure/scripts/etalonnage.py application --jmeter "$JMETER_BIN" --users 10 --output "$output/controle-1"
      sleep 30
      python3 mesure/scripts/etalonnage.py application --jmeter "$JMETER_BIN" --users 10 --output "$output/controle-2"
      python3 outils/resumer_etalonnage.py "$output"
      echo "Nouvelles mesures et rapport : $output. Les preuves canoniques sont conservées."
      ;;
    *) bad_action "$1" ;;
  esac
}
