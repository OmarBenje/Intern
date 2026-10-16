etape_8() {
  case ${1:-configurer} in
    configurer) vm_network ;;
    verifier)
      vm_network
      vm_start
      # The verifier powers off the VMs and removes its temporary SSH rule.
      python3 deploiement/scripts/reseau_etape8.py "$VM_WORK" --verifier
      ;;
    *) bad_action "$1" ;;
  esac
  for vm in vm-proxy vm-metier vm-donnees; do
    VBoxManage showvminfo "$vm" --machinereadable
  done
}
