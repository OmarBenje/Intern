"""Open a document or URL using the host desktop, when available."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target')
    args = parser.parse_args()
    target = args.target
    is_url = target.startswith(('https://', 'http://'))
    if not is_url:
        path = Path(target).resolve()
        if not path.exists():
            parser.error(f'Fichier absent : {target}')
        target = str(path)
    if sys.platform == 'win32':
        os.startfile(target)
        return
    if sys.platform == 'darwin':
        command = ['open', target]
    elif os.environ.get('WSL_DISTRO_NAME'):
        if not is_url:
            target = subprocess.check_output(['wslpath', '-w', target], text=True).strip()
        # rundll32 avoids cmd.exe interpreting characters in paths or URLs.
        command = ['rundll32.exe', 'url.dll,FileProtocolHandler', target]
    elif os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
        command = ['xdg-open', target]
    else:
        print(f'Ouvrir depuis votre poste : {target}')
        return
    if not shutil.which(command[0]):
        print(f'Ouvrir manuellement : {target} (outil absent : {command[0]})')
        return
    if subprocess.run(command).returncode:
        print(f'Ouverture automatique impossible. Ouvrir manuellement : {target}')


if __name__ == '__main__':
    main()
