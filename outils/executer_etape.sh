#!/usr/bin/env bash
# Run a documented course step from any working directory.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
usage() {
  cat <<'HELP'
Usage : bash outils/executer_etape.sh ETAPE [ACTION]
  8  configurer (défaut), verifier
  9  demarrer (défaut)
 10  consulter (défaut), demarrer, arreter, mesurer
 11  demarrer (défaut)
 12  demarrer (défaut)
 13  demarrer (défaut)
 14  consulter (défaut), demarrer, mesurer
 15  preparer (défaut), gui, gui-echec, cli, tout
 16  consulter (défaut), mesurer
 17  verifier (défaut : preuves livrées), preparer, lancer, statut, arreter, nouvelle, capacite
 18  analyser (défaut), capacite (campagne sélectionnée)

Les modes mesurer/lancer exécutent de vraies mesures. Ils ne sont jamais
appelés implicitement par une consultation. Les GUI demandent une interaction.
Variables optionnelles : VM_WORK, DOCKER_ENV_FILE, EXECUTION_PROJECT,
JMETER_BIN, MESURE15_OUTPUT, MESURE16_OUTPUT, MESURE_RUNTIME, MESURE_OUTPUT.
Les chemins relatifs se résolvent depuis Intern. Détails : EXECUTION.md.
HELP
}
if [[ ${1:-} == --help || ${1:-} == -h ]]; then usage; exit 0; fi
step=${1:-}
case "$step" in 8|9|10|11|12|13|14|15|16|17|18) ;; *) usage >&2; exit 2 ;; esac
if (( $# > 2 )); then usage >&2; exit 2; fi
source outils/etapes/commun.sh
source "outils/etapes/$step.sh"
"etape_$step" "${2:-}"
