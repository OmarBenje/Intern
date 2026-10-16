"""Configure a private campaign runtime, preserving existing configuration/results."""

import argparse
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def default_runtime():
    return ROOT.parent / '.execution-campagnes/active'


def require_inactive(runtime):
    pidfile = runtime / 'controller.pid'
    if pidfile.exists():
        try:
            os.kill(int(pidfile.read_text()), 0)
        except ProcessLookupError:
            pass
        else:
            raise SystemExit('Une campagne est déjà active ; utiliser l’action statut.')


def new_campaign(runtime):
    output = ROOT / 'mesure/resultats/campagne'
    if runtime != default_runtime().resolve():
        raise SystemExit('L’action nouvelle utilise le dossier standard .execution-campagnes/active.')
    require_inactive(runtime)
    configfile = runtime / 'configuration.json'
    if not configfile.exists():
        if output.exists():
            raise SystemExit('Résultats sans configuration : conservés, vérifier leur provenance.')
        return
    config = json.loads(configfile.read_text())
    if Path(config['output']).resolve() != output.resolve():
        raise SystemExit('La configuration doit utiliser mesure/resultats/campagne.')
    manifest = output / 'manifest.json'
    state = json.loads(manifest.read_text()) if manifest.exists() else {}
    stamp = datetime.fromtimestamp(state.get('started_epoch_s', datetime.now(timezone.utc).timestamp()), timezone.utc).strftime('%Y-%m-%d_%H-%M-%S')
    archive_runtime = runtime.parent / 'archives' / stamp
    archive_output = output.parent / 'archives' / stamp
    if archive_runtime.exists() or archive_output.exists():
        raise SystemExit('Archive déjà présente : conservée, choisir un autre instant de création.')
    archive_runtime.parent.mkdir(parents=True, exist_ok=True)
    archive_output.parent.mkdir(parents=True, exist_ok=True)
    runtime.rename(archive_runtime)
    try:
        if output.exists():
            output.rename(archive_output)
    except OSError:
        archive_runtime.rename(runtime)
        raise
    config.update(runtime=str(archive_runtime), output=str(archive_output))
    archived_config = archive_runtime / 'configuration.json'
    archived_config.write_text(json.dumps(config, indent=2) + '\n')
    archived_config.chmod(0o600)
    (ROOT / '.execution/campagne-active.json').unlink(missing_ok=True)
    print(f'Campagne conservée dans archives/{stamp}.')


def activate(runtime):
    config = json.loads((runtime / 'configuration.json').read_text())
    path = ROOT / '.execution/campagne-active.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'runtime': str(runtime.resolve()), 'output': config['output']}) + '\n')
    temporary.replace(path)


def check_start(runtime):
    require_inactive(runtime)
    if (runtime / 'stop-requested').exists():
        raise SystemExit('Arrêt précédent enregistré : inspecter le runtime avant une nouvelle campagne.')
    path = runtime / 'configuration.json'
    if path.exists():
        config = json.loads(path.read_text())
        manifest = Path(config['output']) / 'manifest.json'
        if manifest.exists():
            state = json.loads(manifest.read_text())
            if state.get('status') == 'complete':
                raise SystemExit('Campagne déjà complète : utiliser 17 nouvelle pour archiver et préparer la suivante.')
            if state.get('error', '').startswith('Services did not return to idle'):
                raise SystemExit('Repos non validé : mesures conservées. Corriger la cause puis utiliser 17 nouvelle ; la reprise ne peut pas sauter le repos échoué.')


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
    parser.add_argument('--selection', action='store_true')
    parser.add_argument('--activer', action='store_true')
    parser.add_argument('--nouvelle', action='store_true')
    args = parser.parse_args()
    runtime = Path(os.environ.get('MESURE_RUNTIME', default_runtime())).resolve()
    if args.nouvelle:
        new_campaign(runtime)
        return
    if args.selection:
        selected = json.loads((ROOT / '.execution/campagne-active.json').read_text())
        if not (Path(selected['runtime']) / 'configuration.json').is_file():
            raise SystemExit('Configuration de la campagne sélectionnée absente.')
        print(selected['runtime'])
        print(selected['output'])
        return
    if args.activer:
        activate(runtime)
        return
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
