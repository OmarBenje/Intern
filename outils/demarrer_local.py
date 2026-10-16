"""Start missing local DEV layers, preserving existing services and data."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.execution'
PYTHON = ROOT / 'metier/.venv/bin/python'


def run(*command, **kwargs):
    print('+', ' '.join(map(str, command)), flush=True)
    return subprocess.run(list(map(str, command)), cwd=kwargs.pop('cwd', ROOT), check=True, **kwargs)


def occupied(port):
    with socket.socket() as connection:
        return connection.connect_ex(('127.0.0.1', port)) == 0


def ready(url, field=None):
    try:
        with urlopen(url, timeout=3) as response:
            body = response.read()
            if field:
                return response.status == 200 and field in json.loads(body)
            return response.status == 200
    except (OSError, ValueError):
        return False


def wait(check, description):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(1)
    raise SystemExit(f'{description} indisponible après 120 s ; lire .execution/*.log.')


def start(name, command, env, port, check):
    if check():
        print(f'{name} déjà disponible : conservé.', flush=True)
        return
    if occupied(port):
        # A service may still be starting; never replace a live listener.
        print(f'Port {port} occupé : attente du service existant.', flush=True)
        wait(check, name)
        return
    pidfile = RUNTIME / f'{name}.pid'
    if pidfile.exists():
        try:
            os.kill(int(pidfile.read_text()), 0)
        except ProcessLookupError:
            pass
        else:
            wait(check, name)
            return
    with (RUNTIME / f'{name}.log').open('a') as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, start_new_session=True)
    pidfile.write_text(str(process.pid))
    wait(check, name)


def local_environment(frontend_url, api_url):
    env = dict(os.environ)
    engine = RUNTIME / 'moteur.env'
    if engine.exists():
        # Same explicitly configured Bash file as the Docker execution steps.
        output = subprocess.check_output([
            'bash', '-c',
            'set -ae; source "$1" >&2; exec "$2" -c '
            "'import json, os; print(json.dumps(dict(os.environ)))'",
            'intern-config', str(engine), sys.executable,
        ], env=env, cwd=ROOT, text=True)
        env = json.loads(output)
    # uv must use metier/.venv, even when the caller activated another venv.
    env.pop('VIRTUAL_ENV', None)
    env.update(POSTGRES_HOST='127.0.0.1', POSTGRES_PORT='5433',
               POSTGRES_USER='intern_user', POSTGRES_PASSWORD='1234',
               POSTGRES_DB='intern_execution', PRIVATE_STORAGE_BACKEND='local',
               PRIVATE_STORAGE_ROOT=str(RUNTIME / 'media'), DJANGO_DEBUG='true',
               CSRF_TRUSTED_ORIGINS=frontend_url,
               DJANGO_ALLOWED_HOSTS='localhost,127.0.0.1,[::1]',
               PUBLIC_BASE_URL=api_url)
    config = RUNTIME / 'local.env'
    if config.exists():
        for number, line in enumerate(config.read_text().splitlines(), 1):
            if line.strip() and not line.lstrip().startswith('#'):
                key, separator, value = line.partition('=')
                if not separator or not key.strip().isidentifier():
                    raise SystemExit(f'{config.name}:{number} : ligne CLE=valeur attendue.')
                env[key.strip()] = value.strip()
    return env


def postgres_environment(env):
    return dict(env, PGHOST=env['POSTGRES_HOST'], PGPORT=env['POSTGRES_PORT'],
                PGUSER=env['POSTGRES_USER'], PGPASSWORD=env['POSTGRES_PASSWORD'],
                PGDATABASE=env['POSTGRES_DB'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('layer', choices=['donnees', 'metier', 'presentation', 'sql'])
    parser.add_argument('--database', help='Dedicated database name; created only if absent.')
    parser.add_argument('--api-port', type=int, default=8000)
    parser.add_argument('--frontend-port', type=int, default=5173)
    args = parser.parse_args()
    for value in [args.api_port, args.frontend_port]:
        if not 1024 <= value <= 65535:
            parser.error('Ports attendus entre 1024 et 65535.')
    api_url = f'http://127.0.0.1:{args.api_port}'
    frontend_url = f'http://127.0.0.1:{args.frontend_port}'
    os.chdir(ROOT)
    RUNTIME.mkdir(exist_ok=True)
    env = local_environment(frontend_url, api_url)
    tools = ['psql'] if args.layer == 'sql' else ['uv', 'psql']
    if args.layer == 'presentation':
        tools += ['node', 'npm']
    for tool in tools:
        if not shutil.which(tool, path=env.get('PATH')):
            raise SystemExit(f'Outil absent : {tool}. Voir REQUIREMENT.md.')
    if args.database:
        env['POSTGRES_DB'] = args.database
    if env['POSTGRES_HOST'] not in ['127.0.0.1', 'localhost']:
        raise SystemExit('Ce lanceur utilise uniquement PostgreSQL local.')
    if args.layer == 'sql':
        run('psql', '-X', env=postgres_environment(env))
        return
    run('uv', 'sync', '--project', 'metier', '--frozen', env=env)
    port = int(env['POSTGRES_PORT'])
    def database_available():
        probe = dict(env, PGHOST=env['POSTGRES_HOST'], PGPORT=str(port),
                     PGUSER=env['POSTGRES_USER'], PGPASSWORD=env['POSTGRES_PASSWORD'])
        return subprocess.run(['psql', '-X', '-d', 'postgres', '-Atc', 'SELECT 1'],
                              env=probe, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0
    if not database_available():
        if occupied(port):
            wait(database_available, 'PostgreSQL (vérifier aussi les identifiants)')
        else:
            docker = env.get('DOCKER_BIN', 'docker')
            if not shutil.which(docker, path=env.get('PATH')):
                raise SystemExit(f'Client Docker introuvable : {docker}. Voir REQUIREMENT.md.')
            info = subprocess.run([docker, 'info', '--format', '{{.ServerVersion}}'],
                                  env=env, capture_output=True, text=True)
            if 'podman' in (info.stdout + info.stderr).lower():
                raise SystemExit(
                    f'{docker} utilise Podman. Configurer DOCKER_BIN vers Docker Engine '
                    'dans .execution/moteur.env (voir REQUIREMENT.md). Aucun volume modifié.')
            if info.returncode:
                print(info.stderr.strip(), file=sys.stderr)
                raise SystemExit(
                    f'Docker Engine inaccessible via {docker}. Vérifier docker info dans ce '
                    'terminal, le contexte Docker, les droits et .execution/moteur.env. '
                    'Voir REQUIREMENT.md ; aucun volume modifié.')
            if port != 5433:
                raise SystemExit('Démarrer votre serveur PostgreSQL personnalisé avant de continuer.')
            # --no-recreate retains an already existing Compose container.
            run(docker, 'compose', 'up', '-d', '--no-recreate', 'db', env=env)
            wait(database_available, 'PostgreSQL')
    print('PostgreSQL disponible : aucun redémarrage.', flush=True)
    preparation = '''
import os, psycopg
from psycopg import sql
name = os.environ['POSTGRES_DB']
with psycopg.connect(dbname='postgres', host=os.environ['POSTGRES_HOST'],
    port=os.environ['POSTGRES_PORT'], user=os.environ['POSTGRES_USER'],
    password=os.environ['POSTGRES_PASSWORD'], autocommit=True) as conn:
    if not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', (name,)).fetchone():
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        print('Base dédiée créée :', name)
    else:
        print('Base existante conservée :', name)
'''
    run(PYTHON, '-c', preparation, env=env)
    pgenv = postgres_environment(env)
    count = subprocess.check_output(['psql', '-X', '-Atc',
        "SELECT count(*) FROM pg_tables WHERE schemaname='public'"], env=pgenv, text=True).strip()
    if count == '0':
        for file in ['schema', 'data']:
            run('psql', '-X', '-v', 'ON_ERROR_STOP=1', '-f', f'donnees/{file}.sql', env=pgenv)
        for user in ['alice', 'bob', 'vide']:
            destination = Path(env['PRIVATE_STORAGE_ROOT']) / f'dev/{user}/cv.pdf'
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'donnees/cv_fictif.pdf', destination)
    else:
        print('Tables présentes : pas de réimport ni de repeuplement.', flush=True)
    run(PYTHON, 'app/manage.py', 'check', cwd=ROOT / 'metier', env=env)
    if args.layer == 'donnees':
        run(PYTHON, 'donnees/verifier.py', env=pgenv)
        run('psql', '-X', '-v', 'ON_ERROR_STOP=1', '-f', 'donnees/requetes.sql', env=pgenv)
        return
    api_name = 'metier' if args.api_port == 8000 else f'metier-{args.api_port}'
    start(api_name, [str(PYTHON), 'metier/app/manage.py', 'runserver', f'127.0.0.1:{args.api_port}', '--noreload'],
          env, args.api_port, lambda: ready(f'{api_url}/health/ready/') and
          ready(f'{api_url}/api/v1/auth/csrf/', 'csrf_token'))
    if args.layer == 'presentation':
        lock = ROOT / 'frontend/package-lock.json'
        marker = RUNTIME / 'npm-lock.json'
        if not (ROOT / 'frontend/node_modules/.package-lock.json').exists() or not marker.exists() or marker.read_bytes() != lock.read_bytes():
            run('npm', '--prefix', 'frontend', 'ci', env=env)
            shutil.copyfile(lock, marker)
        env['API_PROXY_TARGET'] = api_url
        env['VITE_API_ROOT'] = '/api/v1'
        frontend_name = 'presentation' if args.frontend_port == 5173 else f'presentation-{args.frontend_port}'
        start(frontend_name, ['npm', '--prefix', 'frontend', 'run', 'dev', '--', '--strictPort', '--port', str(args.frontend_port)],
              env, args.frontend_port, lambda: ready(f'{frontend_url}/@vite/client') and
              ready(f'{frontend_url}/api/v1/auth/csrf/', 'csrf_token'))
        print(f'Présentation : {frontend_url}/login')
    print(f'Administration : {api_url}/admin/')


if __name__ == '__main__':
    main()
