#!/usr/bin/env python3
"""Standalone production maintenance; independent of course-step launchers."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploiement.scripts.maintenance.machines import Maintenance
from deploiement.scripts.maintenance.serveurs import Servers, configuration


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('statut', 'executer', 'restaurer'))
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--configuration', type=Path, help='Profil JSON des serveurs de production')
    target.add_argument('--vm', action='store_true', help='Les trois VM VirtualBox locales')
    parser.add_argument('--config-ssh', type=Path, help='Configuration SSH des VM locales')
    parser.add_argument('--redemarrer', action='store_true', help='Autoriser les redémarrages de production requis par Ubuntu')
    args = parser.parse_args(argv)
    if args.configuration:
        if args.config_ssh:
            parser.error('--config-ssh concerne uniquement --vm')
        try:
            profile = configuration(args.configuration)
        except (OSError, ValueError, KeyError, TypeError) as error:
            parser.error(str(error))
        args.config = profile['ssh_config']
        client = Servers(args, profile)
    else:
        args.config = args.config_ssh or Path(__file__).resolve().parents[2] / '.local-vms/access/ssh-etape8-interne.conf'
        if not args.config.is_file():
            parser.error('Configuration SSH des VM absente ; préciser --config-ssh')
        client = Maintenance(args)
    if args.action == 'statut':
        client.status()
    else:
        client.main()


if __name__ == '__main__':
    main()
