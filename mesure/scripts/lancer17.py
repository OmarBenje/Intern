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
        if manifest.exists():
            data = json.loads(manifest.read_text())
            result = {"status": data["status"], "paliers_enregistres": len(data["runs"]),
                      "paliers_attendus": 16, "progress": data.get("progress")}
            if data.get("progress", {}).get("action") == "cooldown":
                result["repos_restant_s"] = max(0, int(data["progress"]["until_epoch_s"] - time.time()))
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("Préparation en cours ; manifeste pas encore disponible.")
        if pidfile.exists():
            print("Processus actif :", alive(int(pidfile.read_text())))
        return
    if not configfile.exists():
        parser.error("Create a private runtime configuration first")
    if pidfile.exists() and alive(int(pidfile.read_text())):
        parser.error("A campaign controller is already running")
    if (runtime / "stop-requested").exists():
        parser.error("A stop was requested; inspect saved data before a new run")
    configuration = json.loads(configfile.read_text())
    manifest_path = Path(configuration["output"]) / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        manifest["status"] = "preparing"
        manifest["progress"] = {"epoch_s": time.time(), "action": "controller_start"}
        temporary = manifest_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(manifest_path)
    command = [sys.executable, str(ROOT / "scripts/campagnes17.py")]
    for key, value in configuration.items():
        command.extend(["--" + key.replace("_", "-"), str(value)])
    with (runtime / "controller.log").open("a") as stream:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True,
                                   cwd=ROOT.parent)
    pidfile.write_text(str(process.pid) + "\n")
    print("Campagnes lancées en arrière-plan. PID :", process.pid)


if __name__ == "__main__":
    main()
