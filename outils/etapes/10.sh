etape_10() {
  case ${1:-consulter} in
    consulter)
      cat deploiement/docs/etape10.md deploiement/docs/mesures.md deploiement/docs/exports-etape10.json
      ;;
    demarrer) vm_deploy; python3 outils/ouvrir.py http://127.0.0.1:8080/login ;;
    mesurer)
      vm_workspace
      [[ ! -e $VM_WORK/exports-etape10 ]] || fail "Exports déjà présents : $VM_WORK/exports-etape10. Les conserver avant une nouvelle mesure ; aucun écrasement automatique."
      vm_deploy
      backup_reports 10 deploiement/docs
      if VBoxManage showvminfo vm-proxy --machinereadable | rg -q ssh-verification; then
        VBoxManage controlvm vm-proxy natpf2 delete ssh-verification
      fi
      python3 deploiement/scripts/verifier_etape10.py "$VM_WORK"
      python3 deploiement/scripts/exporter_etape10.py "$VM_WORK"
      (cd "$VM_WORK/exports-etape10" && sha256sum -c SHA256SUMS)
      ;;
    *) bad_action "$1" ;;
  esac
}
