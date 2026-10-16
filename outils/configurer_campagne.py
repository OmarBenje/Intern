"""Configure a private campaign runtime, preserving existing configuration/results."""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def check_start(runtime):
    pidfile = runtime / 'controller.pid'
    if pidfile.exists():
        try:
            os.kill(int(pidfile.read_text()), 0)
        except ProcessLookupError:
            pass
        else:
            raise SystemExit('Une campagne est déjà active ; utiliser l’action statut.')
    if (runtime / 'stop-requested').exists():
        raise SystemExit('Arrêt précédent enregistré : inspecter le runtime avant une nouvelle campagne.')
    path = runtime / 'configuration.json'
    if path.exists():
        config = json.loads(path.read_text())
        manifest = Path(config['output']) / 'manifest.json'
        if manifest.exists() and json.loads(manifest.read_text()).get('status') == 'complete':
            raise SystemExit('Campagne déjà complète : choisir MESURE_RUNTIME et MESURE_OUTPUT neufs.')


def configuration(env):
    paths = {'docker': 'DOCKER_BIN', 'docker_config': 'DOCKER_CONFIG',
             'env_file': 'DOCKER_ENV_FILE', 'ssh_config': 'MESURE_SSH_CONFIG',
             'jmeter': 'JMETER_BIN', 'runtime': 'MESURE_RUNTIME', 'output': 'MESURE_OUTPUT'}
    config = {key: str(Path(env[var]).resolve()) for key, var in paths.items()}
    config.update(docker_host=env['DOCKER_HOST'], reference_project=env['MESURE_REFERENCE_PROJECT'])
    if Path(config['runtime']).is_relative_to(ROOT):
        raise SystemExit('Le dossier privé MESURE_RUNTIME doit être hors Intern.')
    output = Path(config['output'])
    if output == ROOT / 'mesure/resultats/etape17':
        raise SystemExit('Les preuves livrées etape17 sont réservées : choisir MESURE_OUTPUT neuf.')
    for key in ('docker', 'env_file', 'ssh_config', 'jmeter'):
        if not Path(config[key]).is_file():
            raise SystemExit(f'Fichier requis absent : {key} = {config[key]}')
    return config


def save(config):
    runtime = Path(config['runtime'])
    path = runtime / 'configuration.json'
    if path.exists():
        old = json.loads(path.read_text())
        if old != config:
            changed = ', '.join(key for key in set(old) | set(config) if old.get(key) != config.get(key))
            raise SystemExit(f'Configuration existante différente ({changed}) : conservée. Choisir un nouveau runtime ou corriger les variables.')
        print('Configuration de campagne existante conservée.')
        return
    if Path(config['output']).exists():
        raise SystemExit('MESURE_OUTPUT existe déjà sans configuration associée : choisir un dossier neuf.')
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(config, indent=2) + '\n')
    path.chmod(0o600)
    print(f'Configuration de campagne créée : {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verifier-lancement', action='store_true')
    args = parser.parse_args()
    runtime = Path(os.environ.get('MESURE_RUNTIME', ROOT.parent / '.execution-campagnes')).resolve()
    if args.verifier_lancement:
        check_start(runtime)
        return
    try:
        config = configuration(os.environ)
    except KeyError as error:
        raise SystemExit(f'Paramètre absent : {error.args[0]}. Utiliser bash outils/executer_etape.sh 17 preparer.') from error
    save(config)


if __name__ == '__main__':
    main()
