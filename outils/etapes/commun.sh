# Shared helpers; sourcing this file does not start services or write files.
export PATH="$HOME/.local/bin:$PATH"

fail() { echo "$*" >&2; exit 1; }
bad_action() { fail "Action inconnue : $1. Voir bash outils/executer_etape.sh --help"; }

vm_workspace() {
  if [[ -z ${VM_WORK:-} && -d ../.local-vms/access ]]; then
    VM_WORK="$(cd ../.local-vms && pwd)"
  else
    VM_WORK="${VM_WORK:-$HOME/VMs-intern}"
  fi
  export VM_WORK
}

vm_network() {
  vm_workspace
  bash outils/preparer_vm.sh
  if VBoxManage showvminfo vm-proxy --machinereadable | rg -q '^intnet1="intnet-app"$'; then
    test -f "$VM_WORK/access/ssh-etape8-interne.conf" || fail 'Configuration SSH absente : inspecter la préparation réseau.'
    echo 'Réseau existant conservé.'
  else
    python3 deploiement/scripts/reseau_etape8.py "$VM_WORK"
  fi
}

vmssh() { (cd "$VM_WORK/access" && ssh -F ssh-etape8-interne.conf "$@"); }

vm_start() {
  vm_workspace
  for vm in vm-donnees vm-metier vm-proxy; do
    state=$(VBoxManage showvminfo "$vm" --machinereadable | sed -n 's/^VMState="\(.*\)"$/\1/p')
    case "$state" in
      running) echo "$vm déjà démarrée : conservée" ;;
      poweroff) VBoxManage startvm "$vm" --type headless ;;
      *) fail "$vm : état $state, inspecter avant de continuer" ;;
    esac
  done
  if ! VBoxManage showvminfo vm-proxy --machinereadable | rg -q 'ssh-verification,tcp,127.0.0.1,2221'; then
    VBoxManage controlvm vm-proxy natpf2 'ssh-verification,tcp,127.0.0.1,2221,,22'
  fi
  test -f "$VM_WORK/access/ssh-etape8-interne.conf"
  mkdir -p .execution
  local ssh_wait=${VM_SSH_WAIT_SECONDS:-240}
  [[ $ssh_wait =~ ^[1-9][0-9]*$ ]] || fail 'VM_SSH_WAIT_SECONDS doit être un entier positif.'
  # Private SSH connections use ProxyJump: wait for the proxy first.
  for vm in vm-proxy vm-donnees vm-metier; do
    local deadline=$((SECONDS + ssh_wait))
    local error_log=".execution/ssh-$vm.log"
    echo "Attente SSH : $vm (maximum $ssh_wait s)."
    while true; do
      local remaining=$((deadline - SECONDS))
      if (( remaining <= 0 )); then
        cat "$error_log" >&2
        fail "SSH indisponible : $vm après $ssh_wait s. Voir $error_log."
      fi
      local attempt=$remaining
      (( attempt <= 15 )) || attempt=15
      if (cd "$VM_WORK/access" && timeout --kill-after=2 "$attempt" ssh -F ssh-etape8-interne.conf "$vm" true) 2> "$error_log"; then
        break
      fi
      (( SECONDS >= deadline )) || sleep 1
    done
  done
}

vm_deploy() {
  vm_network
  vm_start
  if vmssh vm-donnees 'test -f /etc/postgresql/16/main/conf.d/intern.conf'; then
    vmssh vm-donnees 'systemctl is-active --quiet postgresql || sudo systemctl start postgresql'
  else
    python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" donnees
  fi
  if vmssh vm-metier 'systemctl cat intern.service >/dev/null 2>&1'; then
    vmssh vm-metier 'systemctl is-active --quiet intern || sudo systemctl start intern'
  else
    python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" metier
  fi
  if vmssh vm-proxy 'test -f /etc/nginx/sites-available/intern'; then
    vmssh vm-proxy 'systemctl is-active --quiet nginx || sudo systemctl start nginx'
  else
    npm --prefix frontend ci
    python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" proxy
  fi
  curl --fail --retry 20 --retry-connrefused --retry-delay 2 http://127.0.0.1:8080/health/ready/
}

engine_ready() {
  if [[ -f ${EXECUTION_ENGINE_CONFIG:-.execution/moteur.env} ]]; then
    set -a
    source "${EXECUTION_ENGINE_CONFIG:-.execution/moteur.env}"
    set +a
  fi
  export DOCKER_BIN="${DOCKER_BIN:-docker}"
  if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
    if [[ -f .execution/moteur.env && -n ${DOCKER_ENGINE_DATA:-} ]]; then
      python3 outils/configurer_moteur.py --restaurer --demarrer
      set -a
      source .execution/moteur.env
      set +a
    elif command -v systemctl >/dev/null && systemctl --user cat docker.service >/dev/null 2>&1; then
      systemctl --user start docker.service
    elif command -v systemctl >/dev/null && systemctl cat docker.service >/dev/null 2>&1; then
      sudo systemctl start docker.service
    else
      fail 'Docker Engine inaccessible : démarrer Docker Desktop ou configurer le moteur selon REQUIREMENT.md.'
    fi
  fi
  local deadline=$((SECONDS + 60))
  until "$DOCKER_BIN" info >/dev/null 2>&1; do
    (( SECONDS < deadline )) || fail 'Docker Engine inaccessible après 60 s.'
    sleep 1
  done
  local version
  version=$("$DOCKER_BIN" info --format '{{.ServerVersion}}' 2>&1)
  [[ $(printf '%s' "$version" | tr '[:upper:]' '[:lower:]') != *podman* ]] || fail 'Utiliser Docker Engine ; ce client utilise Podman.'
  "$DOCKER_BIN" compose version
  export DOCKER_ENV_FILE="${DOCKER_ENV_FILE:-docker/.env}"
}

course_docker() {
  engine_ready
  export EXECUTION_PROJECT="${EXECUTION_PROJECT:-intern-docker}"
  bash outils/demarrer_docker.sh "$1"
}

jmeter_ready() {
  export JMETER_BIN="${JMETER_BIN:-$HOME/.local/share/intern-jmeter/apache-jmeter-5.6.3/bin/jmeter}"
  if [[ ! -x $JMETER_BIN ]]; then
    local install_dir
    install_dir=$(dirname "$(dirname "$(dirname "$JMETER_BIN")")")
    [[ $(basename "$(dirname "$(dirname "$JMETER_BIN")")") == apache-jmeter-5.6.3 ]] || fail 'JMETER_BIN personnalisé introuvable : installer cet exécutable.'
    mkdir -p "$install_dir"
    (
      cd "$install_dir"
      curl -fLO https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-5.6.3.tgz
      curl -fLO https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-5.6.3.tgz.sha512
      local checksum
      checksum=$(awk '{print $1}' apache-jmeter-5.6.3.tgz.sha512)
      [[ $checksum =~ ^[[:xdigit:]]{128}$ ]] || fail 'Empreinte SHA-512 JMeter invalide.'
      printf '%s  apache-jmeter-5.6.3.tgz\n' "$checksum" | sha512sum -c -
      tar -xf apache-jmeter-5.6.3.tgz
    )
  fi
  JMETER_BIN="$(cd "$(dirname "$JMETER_BIN")" && pwd)/$(basename "$JMETER_BIN")"
  export JMETER_BIN
  java -version
  "$JMETER_BIN" --version
}

measure_prepare() {
  engine_ready
  jmeter_ready
  export EXECUTION_PROJECT=intern-mesure EXECUTION_MESURE=1
  bash outils/demarrer_docker.sh proxy
  curl --fail http://127.0.0.1:8081/health/ready/
  mkdir -p .execution
  local accounts
  accounts=$(mktemp .execution/comptes-mesure.XXXXXX)
  if ! "$DOCKER_BIN" compose --env-file "$DOCKER_ENV_FILE" -f docker/compose.yaml \
      -f mesure/compose.test.yaml -p "$EXECUTION_PROJECT" exec -T metier \
      .venv/bin/python app/manage.py shell --verbosity 0 \
      --command 'exec(__import__("sys").stdin.read())' \
      < mesure/scripts/preparer_comptes.py > "$accounts"; then
    rm -f "$accounts"
    fail 'Préparation des comptes échouée ; CSV livré conservé.'
  fi
  test -s "$accounts" || fail 'CSV de comptes vide ; CSV livré conservé.'
  if ! cmp -s "$accounts" mesure/comptes.csv; then
    if [[ -f mesure/comptes.csv ]]; then
      cp mesure/comptes.csv ".execution/comptes-avant-$(date +%Y%m%d-%H%M%S)-$$.csv"
    fi
    cp "$accounts" mesure/comptes.csv
  fi
  rm -f "$accounts"
}

measure_isolated() {
  if command -v VBoxManage >/dev/null; then
    local running
    running=$(VBoxManage list runningvms)
    [[ -z $running ]] || fail "Arrêter explicitement les VM étrangères à cet essai : $running"
  fi
  local projects
  projects=$("$DOCKER_BIN" ps --format '{{.Label "com.docker.compose.project"}}')
  [[ -n $projects ]] || return 0
  while IFS= read -r project; do
    [[ $project == intern-mesure ]] || fail 'Autre conteneur actif : vérifier docker ps et arrêter explicitement les autres déploiements.'
  done <<< "$projects"
}

backup_reports() {
  local destination=".execution/sauvegardes/etape-$1-$(date +%Y%m%d-%H%M%S)-$$"
  shift
  mkdir -p "$destination"
  for path in "$@"; do
    if [[ -e $path ]]; then
      mkdir -p "$destination/$(dirname "$path")"
      cp -a "$path" "$destination/$path"
    fi
  done
  echo "Rapports précédents sauvegardés : $destination"
}
