#!/usr/bin/env python3
"""Revenir à l'étape 7 en conservant les états précédents en snapshots."""
import argparse
import os
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET


def vbox(*args):
    print('VBoxManage ' + ' '.join(args), flush=True)
    return subprocess.check_output(['VBoxManage', *args], text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-propre', action='store_true',
                        help='Sauvegarder chaque état puis restaurer les snapshots base propre.')
    parser.add_argument('--vm-work', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    default = root / '.local-vms' if (root / '.local-vms/access').is_dir() else Path.home() / 'VMs-intern'
    work = (args.vm_work or Path(os.environ.get('VM_WORK', str(default)))).resolve()
    names = ('vm-proxy', 'vm-metier', 'vm-donnees')
    ns = {'v': 'http://www.virtualbox.org/'}
    # Tout contrôler avant la première modification.
    configs = []
    for name in names:
        target = work / 'machines' / name / (name + '.vbox')
        source = target if target.exists() else target.with_suffix('.vbox-prev')
        tree = ET.parse(source)
        machine = tree.find('v:Machine', ns)
        if machine is None or machine.attrib['name'] != name:
            raise SystemExit(f'Configuration incompatible : {source}')
        for disk in tree.findall('.//v:HardDisk', ns):
            if not (source.parent / disk.attrib['location']).is_file():
                raise SystemExit(f'Disque absent : {disk.attrib["location"]}')
        if args.base_propre:
            bases = [s for s in tree.findall('.//v:Snapshot', ns)
                     if s.attrib['name'] == 'base propre']
            if len(bases) != 1:
                raise SystemExit(f'{name} : snapshot base propre absent ou ambigu')
        configs.append((name, target, source, machine.attrib['uuid']))
    if vbox('list', 'runningvms').strip():
        raise SystemExit('Arrêter proprement les VM avant la restauration.')
    for name, target, source, uuid in configs:
        if target != source:
            with source.open('rb') as src, target.open('xb') as dst:
                shutil.copyfileobj(src, dst)
            target.chmod(0o600)
            vbox('unregistervm', uuid)
            vbox('registervm', str(target))
        vbox('showvminfo', name, '--machinereadable')
    if args.base_propre:
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        for name, target, _, _ in configs:
            tree = ET.parse(target)
            snapshots = tree.findall('.//v:Snapshot', ns)
            # Libérer les noms utilisés par les étapes suivantes sans supprimer
            # les snapshots ni les disques qui permettent de revenir en arrière.
            for snapshot in snapshots:
                label = snapshot.attrib['name']
                if label != 'base propre' and not label.startswith('archive-'):
                    vbox('snapshot', name, 'edit', snapshot.attrib['uuid'],
                         '--name', f'archive-{stamp}-{snapshot.attrib["uuid"].strip("{}")}')
            vbox('snapshot', name, 'take', f'archive-{stamp}-avant-remise-a-zero')
            vbox('snapshot', name, 'restore', 'base propre')
            # Configuration requise sur cet hôte, indépendante du disque invité.
            vbox('modifyvm', name, '--paravirtprovider', 'minimal')
        print('Trois VM restaurées à base propre ; états précédents archivés.')
    print(vbox('list', 'vms'))


if __name__ == '__main__':
    main()
