"""Explicit real-engine test: python3 mesure/tests/integration_nettoyage_docker.py --configuration PATH."""

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from campagnes17 import Campaigns
from etalonnage import ROOT, save
from deploiement.scripts.maintenance.commun import operation_lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.configuration.read_text())
    env = dict(os.environ, DOCKER_HOST=config['docker_host'], DOCKER_CONFIG=config['docker_config'])
    image = 'intern-metier:mesure'
    project = 'intern-test-nettoyage-' + secrets.token_hex(6)
    volume = project + '_preuve'
    proof = dict(epoch_s=time.time(), project=project, success=False)
    proof_path = ROOT.parent / '.execution/verification-nettoyage-capacite.json'

    def docker(*parts, check=True):
        return subprocess.run([config['docker'], *parts], env=env, capture_output=True,
                              text=True, check=check, timeout=60)

    with operation_lock(), tempfile.TemporaryDirectory(prefix='intern-nettoyage-') as directory:
        work = Path(directory)
        compose = work / 'compose.json'
        service = dict(image=image, entrypoint=['/usr/local/bin/python'],
                       command=['-c', "from pathlib import Path;import time;Path('/preuve/temoin').write_text('conserve');print('integration-log-marker',flush=True);time.sleep(60)"],
                       volumes=['preuve:/preuve'], networks=['frontal', 'interne'])

        def configure():
            compose.write_text(json.dumps(dict(services=dict(sonde=service), volumes=dict(preuve={}),
                                              networks=dict(frontal={}, interne=dict(internal=True)))))

        controller = Campaigns.__new__(Campaigns)
        controller.args = argparse.Namespace(docker=config['docker'])
        controller.env = env
        controller.runtime = work
        controller.output = work
        controller.manifest = dict(kind='capacity')
        controller.compose = [config['docker'], 'compose', '-f', str(compose), '-p', project]
        controller.collectors = []
        controller.measurement_touched = True
        controller.vm_touched = controller.reference_touched = controller.calibration_touched = False
        try:
            docker('image', 'inspect', image)
            # Reproduce the original probe's permissions error, keeping its cause.
            configure()
            controller.dc('up', '-d', '--no-build')
            container = project + '-sonde-1'
            deadline = time.monotonic() + 10
            while docker('inspect', '--format', '{{.State.Running}}', container).stdout.strip() == 'true':
                if time.monotonic() >= deadline:
                    raise RuntimeError('Expected probe permissions failure did not occur')
                time.sleep(.1)
            logs = docker('logs', container).stderr
            if 'PermissionError' not in logs:
                raise RuntimeError('Unexpected initial probe failure: ' + logs)
            proof['initial_probe_failure'] = 'PermissionError: fresh volume owned by root'
            # This isolated filesystem probe needs write access to its fresh volume.
            # No application credentials or reference database are mounted here.
            service['user'] = '0:0'
            configure()
            controller.dc('up', '-d', '--no-build')
            deadline = time.monotonic() + 10
            while True:
                ready = docker('exec', container, '/usr/local/bin/python', '-c',
                               "from pathlib import Path;assert Path('/preuve/temoin').read_text()=='conserve'", check=False)
                if ready.returncode == 0:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('Probe unavailable: ' + ready.stderr + docker('logs', container).stderr)
                time.sleep(.1)
            controller.restore()
            archives = controller.manifest.get('docker_log_archives', [])
            if not archives or not any('integration-log-marker' in (work / path).read_text() for path in archives):
                raise RuntimeError('Container logs were not archived before removal')
            if docker('network', 'ls', '--filter', 'label=com.docker.compose.project=' + project,
                      '--format', '{{.ID}}').stdout.strip():
                raise RuntimeError('Dedicated networks still present')
            docker('volume', 'inspect', volume)
            docker('run', '--rm', '--network', 'none', '--entrypoint', '/usr/local/bin/python',
                   '-v', volume + ':/preuve:ro', image, '-c',
                   "from pathlib import Path;assert Path('/preuve/temoin').read_text()=='conserve'")
            proof.update(success=True, networks_released=True, volume_content_preserved=True,
                         docker_logs_archived=True)
        except Exception as error:
            proof.update(error=str(error), type=type(error).__name__)
            raise
        finally:
            # Only this freshly generated project's resources can be removed.
            docker('compose', '-f', str(compose), '-p', project, 'down', '--timeout', '10', check=False)
            docker('volume', 'rm', volume, check=False)
            save(proof_path, proof)
        print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()
