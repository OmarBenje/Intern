"""Summarize a new calibration run without changing the archived step-16 report."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def gap(first, second):
    average = (first + second) / 2
    return abs(second - first) / average * 100 if average else 0


def summarize(directory):
    names = ('statique-1', 'statique-20', 'controle-1', 'controle-2')
    results, configurations = {}, {}
    for name in names:
        results[name] = json.loads((directory / name / 'synthese.json').read_text())
        configurations[name] = json.loads((directory / name / 'configuration.json').read_text())
        if configurations[name]['exit_code'] != 0:
            raise ValueError(f'Exécution JMeter échouée : {name}')
    first, second = (configurations[name] for name in ('controle-1', 'controle-2'))
    invariants = ('mode', 'users', 'ramp_s', 'warmup_s', 'plateau_s', 'duration_s', 'port',
                  'reflection_ms', 'source_plan_sha256', 'run_plan_sha256', 'accounts_sha256',
                  'sql_schema_sha256', 'sql_data_sha256', 'seed_script_sha256', 'protocol_sha256', 'host')
    for key in invariants:
        if first[key] != second[key]:
            raise ValueError(f'Contrôles non comparables : {key}')
    controls = [results[name] for name in ('controle-1', 'controle-2')]
    throughput = gap(*(row['successful_throughput_rps'] for row in controls))
    p95 = gap(*(row['p95_ms'] for row in controls))
    return {
        'results': results, 'configurations': configurations,
        'control_throughput_gap_pct': throughput, 'control_p95_gap_pct': p95,
        'repeatability_criteria_passed': throughput <= 10 and p95 <= 10 and all(row['all_errors'] == 0 for row in controls),
        'raw_files_sha256': {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in sorted(directory.glob('*/brut.csv'))},
    }


def write_report(directory, data):
    started = min(config['started_epoch_s'] for config in data['configurations'].values())
    date = datetime.fromtimestamp(started, timezone.utc).isoformat()
    rows = '\n'.join(f"| {name} | {row['successful_throughput_rps']:.3f} | {row['p95_ms']:.2f} | {row['all_errors']} |"
                     for name, row in data['results'].items())
    text = f'''# Étalonnage — nouvelle exécution

Début des mesures : {date} (UTC). Les configurations exactes, dates et
empreintes sont conservées dans les sous-dossiers et dans `etalonnage.json`.

| Essai | Débit réussi (req/s) | p95 (ms) | Erreurs |
| --- | ---: | ---: | ---: |
{rows}

Écart entre contrôles : débit {data['control_throughput_gap_pct']:.2f} % ;
p95 {data['control_p95_gap_pct']:.2f} %.
Critère de répétabilité (écarts ≤ 10 %, aucune erreur) :
**{'réussi' if data['repeatability_criteria_passed'] else 'non satisfait'}**.

Ce rapport porte uniquement sur ces quatre essais. Il ne valide pas une
nouvelle campagne VM/Docker, une saturation ni l’approbation pédagogique.
Les preuves archivées dans `mesure/resultats/etape16` restent distinctes.
'''
    (directory / 'etalonnage.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    (directory / 'rapport.md').write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    canonical = Path(__file__).resolve().parents[1] / 'mesure/resultats/etape16'
    if directory == canonical:
        parser.error('Dossier livré réservé ; utiliser le générateur historique pour ses preuves.')
    write_report(directory, summarize(directory))


if __name__ == '__main__':
    main()
