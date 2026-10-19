"""Export small reviewed summaries, optionally archive the selected raw evidence outside Git."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]
SELECTED = ('capacite-20261018-195024-455892', 'worker-20261019-103419-13231',
            'worker-vm-20261019-143401-202396')
SUMMARY_NAMES = {'manifest.json', 'protocole.json', 'synthese.json', 'serveurs.json',
                 'injecteur.json', 'rejet.json', 'verification.json', 'incident.json',
                 'rapport-workers.md', 'comparatif-workers.csv', 'capacite.json',
                 'rapport.md', 'rapport.pdf', 'erreurs-par-requete.csv'}
RAW_NAMES = (SUMMARY_NAMES - {'erreurs-par-requete.csv'}) | {'brut.csv', 'ressources.csv', 'configuration.json', 'journal.jsonl',
                            'comptes.csv', 'plan.jmx', 'disponibilite.jsonl', 'arret-securite.json'}
MANIFEST_KEYS = ('kind', 'status', 'started_epoch_s', 'finished_epoch_s', 'order', 'runs',
                 'worker_deployment', 'worker_levels', 'expected_plateaus', 'skipped_loads',
                 'protocol_sha256', 'source_plan_sha256', 'snapshot_sha256', 'sources_sha256',
                 'accounts_sha256', 'images', 'docker_resources', 'docker_versions',
                 'vm_versions', 'vm_configuration', 'calibration_attempts', 'calibration_warnings')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def raw_file(path):
    return path.name in RAW_NAMES or (path.name.startswith('serveur-') and path.suffix == '.jsonl')


def export(campaigns, destination):
    destination.mkdir(parents=True, exist_ok=True)
    for name in campaigns:
        if Path(name).name != name:
            raise ValueError('Use campaign names without directory components')
        source = ROOT / 'resultats' / name
        manifest = json.loads((source / 'manifest.json').read_text())
        if manifest['status'] not in ('complete', 'failed', 'stopped'):
            raise ValueError('Cannot export an active campaign: ' + name)
        target = destination / name
        target.mkdir(exist_ok=True)
        entries = []
        for path in sorted(source.rglob('*')):
            if path.is_symlink():
                raise ValueError('Symlinks are not evidence files: ' + str(path))
            if not path.is_file() or not (raw_file(path) or path.name in SUMMARY_NAMES):
                continue
            relative = path.relative_to(source)
            if raw_file(path):
                entries.append(dict(path=str(relative), bytes=path.stat().st_size, sha256=digest(path)))
            # Historical attempts remain in the raw archive; keep the Git selection concise.
            if path.name not in SUMMARY_NAMES or relative.parts[0] == 'reprises':
                continue
            output = target / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            if path.name == 'manifest.json':
                continue
            else:
                shutil.copyfile(path, output)
        # A reviewed manifest excerpt omits private command diagnostics and local context.
        (target / 'manifest.json').write_text(json.dumps(
            {k: manifest[k] for k in MANIFEST_KEYS if k in manifest}, indent=2) + '\n')
        (target / 'SOURCE.json').write_text(json.dumps(dict(campaign=name,
            original_manifest_sha256=digest(source / 'manifest.json'),
            original_folder='mesure/resultats/' + name, raw_files=len(entries),
            raw_bytes=sum(e['bytes'] for e in entries), manifest_is_excerpt=True), indent=2) + '\n')
        with (target / 'inventaire-bruts.csv').open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=['path', 'bytes', 'sha256'])
            writer.writeheader()
            writer.writerows(entries)
        print(name, ':', len(entries), 'fichiers bruts inventoriés', flush=True)


def archive(campaigns, path, destination):
    path = path.resolve()
    if path.is_relative_to(ROOT.parent):
        raise ValueError('Store the archive outside the Intern repository')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite an existing archive.
    with path.open('xb') as stream:
        with tarfile.open(fileobj=stream, mode='w:gz', compresslevel=6) as tar:
            for name in campaigns:
                for source in sorted((ROOT / 'resultats' / name).rglob('*')):
                    if source.is_symlink():
                        raise ValueError('Symlink refused')
                    if source.is_file() and raw_file(source):
                        tar.add(source, arcname=str(Path(name) / source.relative_to(ROOT / 'resultats' / name)), recursive=False)
    entry = f'{digest(path)}  {path.name}\n'
    path.with_name(path.name + '.sha256').write_text(entry)
    (destination / 'ARCHIVE-SHA256.txt').write_text(entry)
    print('Archive :', path, 'octets :', path.stat().st_size, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campagnes', nargs='+', default=list(SELECTED))
    parser.add_argument('--destination', type=Path, default=ROOT / 'preuves')
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    export(args.campagnes, args.destination)
    if args.archive:
        archive(args.campagnes, args.archive, args.destination)
    files = sorted(p for p in args.destination.rglob('*') if p.is_file() and p.name != 'SHA256SUMS')
    (args.destination / 'SHA256SUMS').write_text(''.join(
        f'{digest(p)}  {p.relative_to(args.destination)}\n' for p in files))


if __name__ == '__main__':
    main()
