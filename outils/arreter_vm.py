#!/usr/bin/env python3
"""Éteindre proprement les trois VM Intern avec le bouton ACPI."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deploiement/scripts'))
from reseau_etape8 import info, vbox, wait_off


def main():
    names = ('vm-donnees', 'vm-metier', 'vm-proxy')
    states = {name: info(name)['VMState'] for name in names}
    # Contrôler toutes les VM avant de demander le premier arrêt.
    for name, state in states.items():
        if state not in ('running', 'poweroff', 'aborted'):
            raise SystemExit(f'{name} : état {state}, inspecter dans VirtualBox avant de continuer.')
    for name, state in states.items():
        if state == 'running':
            print(f'Arrêt propre demandé : {name}', flush=True)
            vbox('controlvm', name, 'acpipowerbutton')
        else:
            print(f'{name} déjà arrêtée ({state}).')
    for name, state in states.items():
        if state == 'running':
            wait_off(name)
    print('Les trois VM sont arrêtées. Vous pouvez passer à Docker.')


if __name__ == '__main__':
    main()
