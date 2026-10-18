etape_18() {
  case ${1:-analyser} in
    analyser)
      test -x .execution/analyse/bin/python || python3 -m venv .execution/analyse
      .execution/analyse/bin/pip install -r mesure/requirements-analyse.txt
      .execution/analyse/bin/python mesure/scripts/verifier17.py
      .execution/analyse/bin/python mesure/scripts/analyser18.py
      .execution/analyse/bin/python mesure/scripts/generer_rapport18.py
      python3 outils/ouvrir.py mesure/docs/rapport-charge.pdf
      ;;
    capacite)
      local source=${CAPACITE_SOURCE:-}
      if [[ -z $source && -f .execution/campagne-active.json ]]; then
        source=$(python3 -c 'import json; print(json.load(open(".execution/campagne-active.json"))["output"])')
      fi
      [[ -n $source ]] || fail 'Sélectionner une campagne de capacité ou définir CAPACITE_SOURCE.'
      test -x .execution/analyse/bin/python || python3 -m venv .execution/analyse
      .execution/analyse/bin/pip install -r mesure/requirements-analyse.txt
      .execution/analyse/bin/python mesure/scripts/analyser_capacite.py --source "$source"
      ;;
    *) bad_action "$1" ;;
  esac
}
