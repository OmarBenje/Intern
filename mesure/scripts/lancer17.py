"""Start detached campaigns, inspect progress or request a graceful stop."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Existence without permission is not evidence that it is safe to restart.
        return True


def update_guard_status(output):
    journal = output / 'journal.jsonl'
    paused, restored = set(), False
    if journal.exists():
        for line in journal.read_text().splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue  # Status can read while the controller writes its last line.
            if event.get('action') == 'updates_paused':
                paused.add(event['service'])
            elif event.get('action') == 'updates_restored':
                paused.discard(event['service'])
                restored = True
    if paused:
        return 'protection active pour ' + ', '.join(sorted(paused))
    if restored:
        return 'politique initiale restaurée'
    return 'protection pas encore activée'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "status", "stop"])
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    pidfile = runtime / "controller.pid"
    configfile = runtime / "configuration.json"
    if args.action == "stop":
        if not configfile.exists():
            parser.error("No configured campaign")
        (runtime / "stop-requested").touch()
        print("Arrêt demandé ; attendre la restauration du déploiement de référence.")
        return
    if args.action == "status":
        configuration = json.loads(configfile.read_text())
        manifest = Path(configuration["output"]) / "manifest.json"
        active = pidfile.exists() and alive(int(pidfile.read_text()))
        if manifest.exists():
            data = json.loads(manifest.read_text())
            result = {"status": data["status"], "paliers_enregistres": len(data["runs"]),
                      "paliers_attendus": (data["expected_plateaus"] if data.get("kind") == "worker" else "adaptatifs" if data.get("kind") == "capacity" else
                          4 * len(json.loads((ROOT / "protocole-performance.json").read_text())["paliers_utilisateurs"])),
                      "progress": data.get("progress")}
            if data.get('kind') == 'worker':
                result['deploiement'] = data.get('worker_deployment', 'docker')
                result['charges_annulees'] = data.get('skipped_loads', [])
                result['etalonnages_refuses'] = len(data.get('calibration_attempts', []))
                result['etalonnages_avec_requetes_lentes'] = len(data.get('calibration_warnings', []))
            if data.get('resumptions'):
                latest = data['resumptions'][-1]
                result['reprise_depuis'] = {k: latest[k] for k in ('deployment', 'series', 'users')}
                result['tentatives_archivees'] = len(data['resumptions'])
            for key in ("error", "restoration_errors", "collector_errors", "diagnostic_errors", "measurement_project"):
                if key in data and (key in ("measurement_project", "diagnostic_errors") or data["status"] in ("failed", "stopped")):
                    result[key] = data[key]
            if data.get("progress", {}).get("action") == "cooldown":
                result["repos_restant_s"] = max(0, int(data["progress"]["until_epoch_s"] - time.time()))
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("Préparation en cours ; manifeste pas encore disponible." if active else
                  "Contrôleur inactif ; aucun manifeste disponible. Consulter le journal de démarrage.")
            log = runtime / "controller.log"
            if not active and log.exists():
                print("\n".join(log.read_text(errors="replace").splitlines()[-35:]))
        if pidfile.exists():
            print("Processus actif :", active)
        if manifest.exists() and data["status"] in ("failed", "stopped"):
            restored = data.get("progress", {}).get("action") == "reference_restored"
            refused = data.get("progress", {}).get("action") in ("campaigns_refused", "preflight_failed")
            print("Restauration :", "sans objet : contrôleur refusé avant modification des déploiements" if refused else "confirmée" if restored else
                  "non confirmée (contrôleur encore actif)" if active else
                  "non confirmée ; vérifier les services avant une nouvelle campagne")
        print("Journal :", runtime / "controller.log")
        if manifest.exists() and data.get('maintenance_guard'):
            print("Mises à jour VM :", update_guard_status(manifest.parent))
        if manifest.exists() and data["status"] == "failed":
            recovered = data.get("progress", {}).get("action") == "reference_restored"
            print("Historique de l’échec (services restaurés ensuite) :" if recovered else
                  "Dernières lignes du journal :")
            log = runtime / "controller.log"
            if log.exists():
                print("\n".join(log.read_text(errors="replace").splitlines()[-35:]))
            for collector in data.get("collector_errors", []):
                diagnostic = (runtime / collector["diagnostic"]).resolve()
                if diagnostic.is_relative_to(runtime) and diagnostic.is_file():
                    print("Diagnostic collecteur", collector["service"], ":", diagnostic)
                    print("\n".join(diagnostic.read_text(errors="replace").splitlines()[-25:]))
            diagnostic = runtime / "last-error.txt"
            if diagnostic.exists():
                print("Diagnostic de commande archivé, antérieur à la restauration confirmée :" if recovered else
                      "Dernier diagnostic de commande :", diagnostic)
                print(diagnostic.read_text(errors="replace"))
        return
    if not configfile.exists():
        parser.error("Create a private runtime configuration first")
    if pidfile.exists() and alive(int(pidfile.read_text())):
        parser.error("A campaign controller is already running")
    if (runtime / "stop-requested").exists():
        parser.error("A stop was requested; inspect saved data before a new run")
    configuration = json.loads(configfile.read_text())
    command = [sys.executable, str(ROOT / "scripts/campagnes17.py")]
    for key, value in configuration.items():
        command.extend(["--" + key.replace("_", "-"), str(value)])
    # Validate ownership, VM access and port conflicts before detaching.
    with (runtime / "controller.log").open("a") as stream:
        check = subprocess.run([*command, "--preflight"], stdin=subprocess.DEVNULL,
                               stdout=stream, stderr=subprocess.STDOUT, cwd=ROOT.parent)
    if check.returncode:
        print("Préparation refusée ; aucun service arrêté par le contrôleur.")
        print("\n".join((runtime / "controller.log").read_text(errors="replace").splitlines()[-20:]))
        diagnostic = runtime / "last-error.txt"
        if diagnostic.exists():
            print(diagnostic.read_text(errors="replace"))
        raise SystemExit(f"Consulter {runtime / 'controller.log'}")
    manifest_path = Path(configuration["output"]) / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        manifest["status"] = "preparing"
        manifest["progress"] = {"epoch_s": time.time(), "action": "controller_start"}
        manifest.pop("error", None)
        manifest.pop("restoration_errors", None)
        temporary = manifest_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(manifest_path)
    with (runtime / "controller.log").open("a") as stream:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True,
                                   cwd=ROOT.parent)
    pidfile.write_text(str(process.pid) + "\n")
    print("Campagnes lancées en arrière-plan. PID :", process.pid)
    print("Démarrage du contrôleur ; vérifier ensuite avec l’action statut.")
    print("Journal :", runtime / "controller.log")


if __name__ == "__main__":
    main()
