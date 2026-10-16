"""Detect Docker Engine and generate the ignored local engine configuration."""

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / '.execution/moteur.env'
ENGINE_VERSION = '28.3.3'
COMPOSE_VERSION = '2.39.4'
KEYS = ('DOCKER_BIN', 'DOCKER_HOST', 'DOCKER_CONFIG', 'DOCKER_ENGINE_BIN',
        'DOCKER_ENGINE_RUNTIME', 'DOCKER_ENGINE_DATA')


def existing_config(path):
    if not path.exists():
        return {}
    result = subprocess.check_output([
        'bash', '-c', 'set -ae; source "$1" >&2; exec "$2" -c '
        "'import os,json; print(json.dumps(dict(os.environ)))'",
        'intern-config', str(path), sys.executable,
    ], text=True)
    env = json.loads(result)
    return {key: env[key] for key in KEYS if key in env}


def probe(command, env=None):
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
        return result.returncode == 0 and 'podman' not in (result.stdout + result.stderr).lower()
    except (OSError, subprocess.TimeoutExpired):
        return False


def find_client(old, explicit=None):
    candidates = [explicit] if explicit else [old.get('DOCKER_BIN'), shutil.which('docker')]
    if not explicit:
        candidates += [str(ROOT / '.execution/docker-engine/bin/docker'),
                       str(Path.home() / 'bin/docker'),
                       str(Path.home() / '.local/bin/docker'), '/usr/local/bin/docker',
                       '/usr/bin/docker']
    for candidate in candidates:
        if candidate and probe([candidate, '--version']):
            return str(Path(candidate).absolute())
    return None


def download(url, path):
    print(f'Téléchargement : {url}', flush=True)
    try:
        with urlopen(url, timeout=60) as response, path.open('wb') as stream:
            shutil.copyfileobj(response, stream)
    except (OSError, URLError) as error:
        raise SystemExit(f'Téléchargement impossible : {error}. Ancienne configuration conservée.') from error


def restore_engine(directory):
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'aarch64'):
        raise SystemExit('Restauration automatique prévue pour Linux x86_64/ARM64. Voir REQUIREMENT.md.')
    for tool in ('newuidmap', 'newgidmap', 'fuse-overlayfs'):
        if not shutil.which(tool):
            raise SystemExit(f'Prérequis rootless absent : {tool}. Voir REQUIREMENT.md.')
    binary = directory / 'bin'
    binary.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        for archive in ('docker', 'docker-rootless-extras'):
            path = work / f'{archive}.tgz'
            download(f'https://download.docker.com/linux/static/stable/{platform.machine()}/'
                     f'{archive}-{ENGINE_VERSION}.tgz', path)
            with tarfile.open(path) as tar:
                tar.extractall(work / archive, filter='data')
            for source in (work / archive).rglob('*'):
                if source.is_file():
                    shutil.copy2(source, binary / source.name)
        name = f'docker-compose-linux-{platform.machine()}'
        base = f'https://github.com/docker/compose/releases/download/v{COMPOSE_VERSION}'
        plugin = work / name
        checksum = work / 'checksum'
        download(f'{base}/{name}', plugin)
        download(f'{base}/{name}.sha256', checksum)
        if hashlib.sha256(plugin.read_bytes()).hexdigest() != checksum.read_text().split()[0]:
            raise SystemExit('Empreinte Compose incorrecte ; configuration conservée.')
        plugins = directory / 'cli-plugins'
        plugins.mkdir(exist_ok=True)
        shutil.copy2(plugin, plugins / 'docker-compose')
        (plugins / 'docker-compose').chmod(0o755)
    return str(binary / 'docker')


def save_config(path, values):
    text = '# Généré par outils/configurer_moteur.py\nunset DOCKER_CONTEXT\n'
    # Clear stale exported values when this file is sourced by a Bash step.
    text += 'unset ' + ' '.join(key for key in KEYS if key not in values) + '\n'
    text += ''.join(f'export {key}={shlex.quote(str(value))}\n' for key, value in values.items())
    if path.exists() and path.read_text() == text:
        print('Configuration déjà à jour.')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(f'moteur.env.{datetime.now():%Y%m%d-%H%M%S-%f}.bak')
        shutil.copy2(path, backup)
        backup.chmod(0o600)
        print(f'Ancienne configuration conservée : {backup.name}')
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(text)
    temporary.chmod(0o600)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restaurer', action='store_true', help='Télécharger les binaires rootless manquants dans .execution, hors /tmp.')
    parser.add_argument('--demarrer', action='store_true', help='Démarrer le moteur rootless configuré si nécessaire.')
    parser.add_argument('--docker-bin', help='Chemin explicite du véritable client Docker.')
    parser.add_argument('--data-root', type=Path, help='Stockage rootless existant à conserver.')
    args = parser.parse_args()
    old = existing_config(CONFIG)
    data = args.data_root or (Path(old['DOCKER_ENGINE_DATA']) if old.get('DOCKER_ENGINE_DATA') else None)
    client = find_client(old, args.docker_bin)
    managed = ROOT / '.execution/docker-engine'
    repair_managed = (client and Path(client).is_relative_to(managed) and args.restaurer
                      and not all((managed / name).is_file() for name in
                                  ('bin/dockerd', 'bin/dockerd-rootless.sh', 'cli-plugins/docker-compose')))
    if (not client and args.restaurer) or repair_managed:
        if not data or not data.is_dir():
            raise SystemExit('Stockage rootless existant requis : préciser --data-root. Aucun nouveau stockage créé.')
        client = restore_engine(managed)
    if not client:
        raise SystemExit('Docker Engine introuvable (Podman est exclu). Pour restaurer les binaires disparus :\n'
                         'python3 outils/configurer_moteur.py --restaurer --demarrer\n'
                         'Le fichier existant et les données sont conservés.')
    env = dict(os.environ)
    for key in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG'):
        env.pop(key, None)
    values = {'DOCKER_BIN': client}
    if data:
        if not data.is_dir():
            raise SystemExit(f'Stockage existant introuvable : {data}. Configuration conservée.')
        # Preserve the old daemon and its data rather than selecting another context.
        engine_bin = Path(client).parent
        if not (engine_bin / 'dockerd-rootless.sh').is_file():
            raise SystemExit('Client trouvé sans dockerd-rootless.sh ; conserver le stockage nécessite les binaires rootless.')
        directory = engine_bin.parent
        runtime = Path(old.get('DOCKER_ENGINE_RUNTIME', f'/tmp/intern-docker-runtime-{os.getuid()}'))
        values.update(DOCKER_HOST=old.get('DOCKER_HOST', f'unix://{runtime}/docker.sock'),
                      DOCKER_CONFIG=str(directory), DOCKER_ENGINE_BIN=str(engine_bin),
                      DOCKER_ENGINE_RUNTIME=str(runtime), DOCKER_ENGINE_DATA=str(data.resolve()))
        env.update(values)
        if args.demarrer and not probe([client, 'info'], env):
            runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
            if runtime.stat().st_uid != os.getuid():
                raise SystemExit('Le répertoire runtime appartient à un autre utilisateur.')
            runtime.chmod(0o700)
            env.update(PATH=f'{engine_bin}:{env["PATH"]}', XDG_RUNTIME_DIR=str(runtime))
            log_path = ROOT / '.execution/moteur.log'
            with log_path.open('a') as log:
                process = subprocess.Popen([
                    str(engine_bin / 'dockerd-rootless.sh'), f'--host={values["DOCKER_HOST"]}',
                    f'--data-root={data.resolve()}', f'--exec-root={runtime}/exec',
                    '--storage-driver=fuse-overlayfs', f'--pidfile={runtime}/docker.pid',
                ], env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            for _ in range(30):
                if probe([client, 'info'], env):
                    break
                if process.poll() is not None:
                    raise SystemExit('Échec du démarrage : lire .execution/moteur.log. Configuration conservée.')
                time.sleep(1)
            else:
                raise SystemExit('Moteur non prêt : lire .execution/moteur.log. Configuration conservée.')
    else:
        # Native Docker/Desktop uses its selected context, without a guessed socket.
        if not probe([client, 'info'], env):
            raise SystemExit('Client Docker trouvé, serveur inaccessible : démarrer votre service Docker/Desktop.')
    if not probe([client, 'compose', 'version'], env):
        raise SystemExit('Plugin Docker Compose v2 absent ; configuration conservée.')
    save_config(CONFIG, values)
    print(f'Configuration écrite : {CONFIG}')
    print('Stockage conservé. Lancer ensuite python3 outils/demarrer_local.py metier')


if __name__ == '__main__':
    main()
