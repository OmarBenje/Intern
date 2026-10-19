"""Run paired VM/Docker campaigns with a common snapshot and per-service metrics."""

import argparse
import csv
import json
import os
from pathlib import Path
import secrets
import shlex
import signal
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

from etalonnage import ROOT, PERFORMANCE_PROTOCOL, digest, save
from repos import idle_window, idle_blockers
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from deploiement.scripts.maintenance.commun import VMUpdates, operation_lock

DATABASE = "intern_mesure17"
PROJECT = "intern-etape17"
SERVICES = ("proxy", "metier", "donnees")
NAT_RULES = ("ssh-mesure17,tcp,127.0.0.1,2221,,22", "http-mesure17,tcp,127.0.0.1,8081,,8082")
QUERY = """SELECT json_build_object(
'db_connections',(SELECT count(*) FROM pg_stat_activity WHERE datname='intern_mesure17'),
'db_active_connections',(SELECT count(*) FROM pg_stat_activity WHERE datname='intern_mesure17' AND state='active'),
'db_blocks_read',blks_read,'db_blocks_hit',blks_hit,'db_transactions',xact_commit+xact_rollback)
FROM pg_stat_database WHERE datname='intern_mesure17';"""


def validate_runtime_versions(vm, docker):
    for library in ("python", "django", "drf", "gunicorn"):
        if library not in vm or library not in docker:
            raise RuntimeError("Missing runtime version: " + library)
        if vm[library] != docker[library]:
            raise RuntimeError("VM and Docker dependency versions differ: " + library)


class Campaigns:
    def __init__(self, args):
        self.args = args
        self.runtime = args.runtime.resolve()
        if self.runtime.is_relative_to(ROOT.parent):
            raise RuntimeError("Private runtime files must stay outside the application repository")
        self.runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.output = args.output.resolve()
        if not self.output.is_relative_to(ROOT):
            raise RuntimeError("Results must be inside mesure/")
        self.output.mkdir(parents=True, exist_ok=True)
        self.protocol_path = getattr(args, "capacity_protocol", None) or PERFORMANCE_PROTOCOL
        self.protocol = json.loads(self.protocol_path.read_text())
        self.accounts = self.output / "comptes.csv" if getattr(args, "capacity_protocol", None) else ROOT / "comptes.csv"
        if not getattr(args, "capacity_protocol", None) and max(self.protocol["paliers_utilisateurs"]) > 20:
            raise RuntimeError("This calibrated campaign supports at most twenty users")
        self.env = {**os.environ, "DOCKER_HOST": args.docker_host, "DOCKER_CONFIG": str(args.docker_config)}
        self.owner_path = self.runtime / "measurement-project.json"
        if self.owner_path.exists():
            self.project = json.loads(self.owner_path.read_text())["project"]
        elif (self.runtime / "base.sql").exists():
            self.project = PROJECT  # Resume campaigns created by the original controller.
        else:
            self.project = PROJECT + "-" + secrets.token_hex(6)
        self.updates = VMUpdates(lambda *a, **kw: self.ssh(*a, **kw), self.project, self.event)
        self.reference_touched = False
        self.measurement_touched = False
        self.vm_touched = False
        self.suspended_containers = []
        self.calibration_touched = False
        self.nat_path = self.runtime / "nat-rules.json"
        self.created_nat_rules = json.loads(self.nat_path.read_text()) if self.nat_path.exists() else []
        self.compose = [args.docker, "compose", "--env-file", str(self.runtime / "docker.env"),
                        "-f", str(ROOT.parent / "docker/compose.yaml"),
                        "-f", str(ROOT / "compose.test.yaml"), "-p", self.project]
        self.reference = [args.docker, "compose", "--env-file", str(args.env_file.resolve()),
                          "-f", str(ROOT.parent / "docker/compose.yaml"), "-p", args.reference_project]
        self.ssh_config = args.ssh_config.resolve()
        self.collectors = []
        self.manifest_path = self.output / "manifest.json"
        self.manifest = json.loads(self.manifest_path.read_text()) if self.manifest_path.exists() else {
            "status": "preparing", "protocol_sha256": digest(self.protocol_path),
            "source_plan_sha256": digest(ROOT / "plan.jmx"), "order": ["vm", "docker", "docker", "vm"],
            "runs": [], "started_epoch_s": time.time(), "maintenance_guard": True,
        }
        if self.manifest["protocol_sha256"] != digest(self.protocol_path):
            raise RuntimeError("Protocol changed since campaign preparation")

    def event(self, action, **fields):
        value = {"epoch_s": time.time(), "action": action, **fields}
        with (self.output / "journal.jsonl").open("a") as stream:
            stream.write(json.dumps(value) + "\n")
        self.manifest["progress"] = value
        save(self.manifest_path, self.manifest)
        print(json.dumps(value), flush=True)

    def check_stop(self):
        if getattr(self, "stop_requested", False) or (self.runtime / "stop-requested").exists():
            raise InterruptedError("Graceful stop requested")

    def record_incident(self, error, phase=None):
        incident = self.manifest.setdefault("incident", dict(
            epoch_s=time.time(), type=type(error).__name__, message=str(error),
            phase=phase or self.manifest.get("progress", {}).get("action", "preparation")))
        incident["command_diagnostics"] = self.manifest.get("command_errors", [])
        incident["restoration_errors"] = self.manifest.get("restoration_errors", [])
        incident["safety_evidence"] = sorted(str(path.relative_to(self.output))
                                             for path in self.output.rglob("arret-securite.json"))
        save(self.output / "incident.json", incident)

    def record_command_failure(self, command, *, stdout=None, stderr=None, returncode=None, error=None):
        def decode(value):
            return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
        directory = self.runtime / "command-errors"
        directory.mkdir(mode=0o700, exist_ok=True)
        diagnostic = dict(epoch_s=time.time(), command=list(map(str, command)), returncode=returncode,
                          error=type(error).__name__ if error else None,
                          message=str(error) if error else None,
                          stdout=decode(stdout), stderr=decode(stderr),
                          action=self.manifest.get("progress", {}).get("action"))
        # Keep the first failure even when recovery commands fail afterwards.
        with tempfile.NamedTemporaryFile(dir=directory, prefix="command-", suffix=".json",
                                         mode="w", encoding="utf-8", delete=False) as stream:
            json.dump(diagnostic, stream, ensure_ascii=False, indent=2)
            path = Path(stream.name)
        (self.runtime / "last-error.txt").write_text(diagnostic["stderr"] or diagnostic["stdout"] or
                                                       diagnostic["message"] or "Command failed")
        self.manifest.setdefault("command_errors", []).append(str(path.relative_to(self.runtime)))
        return path

    def run(self, command, *, data=None, check=True, timeout=90, cwd=None):
        try:
            result = subprocess.run(command, input=data, capture_output=True, env=self.env, timeout=timeout, cwd=cwd)
        except (subprocess.TimeoutExpired, OSError) as error:
            self.record_command_failure(command, stdout=getattr(error, "stdout", None),
                                        stderr=getattr(error, "stderr", None), error=error)
            # Preserve the type: bounded SSH boot retries handle TimeoutExpired.
            raise
        if check and result.returncode:
            # Keep diagnostics outside deliverables; they can contain local paths.
            self.record_command_failure(command, stdout=result.stdout, stderr=result.stderr,
                                        returncode=result.returncode)
            raise RuntimeError("Command failed; diagnostic saved in the private runtime directory")
        return result

    def docker(self, *parts, **kwargs):
        return self.run([self.args.docker, *parts], **kwargs)

    def dc(self, *parts, **kwargs):
        return self.run([*self.compose, *parts], **kwargs)

    def ssh(self, service, command, **kwargs):
        return self.run(["ssh", "-F", self.ssh_config.name, f"vm-{service}", command], cwd=self.ssh_config.parent, **kwargs)

    def vm_info(self, service):
        command = ["VBoxManage", "showvminfo", f"vm-{service}", "--machinereadable"]
        # Guest shutdown can transiently invalidate the shared session or its
        # RemoteUSBDevices object. Other access errors still fail immediately.
        for attempt in range(6):
            result = self.run(command, check=False)
            if result.returncode == 0:
                break
            transient = (b"VBOX_E_INVALID_OBJECT_STATE" in result.stderr or
                         (b"RemoteUSBDevices" in result.stderr and b"E_ACCESSDENIED" in result.stderr
                          and b"The object is not ready" in result.stderr))
            if not transient or attempt == 5:
                (self.runtime / "last-error.txt").write_bytes(result.stderr)
                raise RuntimeError(f"Cannot read vm-{service} state; inspect last-error.txt")
            time.sleep(2)
        return result.stdout.decode()

    def vm_state(self, service):
        info = self.vm_info(service)
        return next(line.split("=", 1)[1].strip('"') for line in info.splitlines() if line.startswith("VMState="))

    @staticmethod
    def nat_rules(info):
        return [line.split("=", 1)[1].strip('"') for line in info.splitlines()
                if line.startswith("Forwarding(")]

    @staticmethod
    def nat_rule_needed(rule, existing):
        desired = rule.split(",")
        for current in existing:
            fields = current.split(",")
            if fields[1:] == desired[1:]:
                return False  # Equivalent forwarding can have a different name.
        for current in existing:
            fields = current.split(",")
            if fields[0] == desired[0] or (fields[1] == desired[1] and fields[3] == desired[3]
                    and (fields[2] == desired[2] or not fields[2] or not desired[2])):
                raise RuntimeError(f"Redirection NAT incompatible : {current} ; attendue : {rule}. Règle existante conservée.")
        return True

    def boot_vm(self, restoring=False):
        self.vm_touched = True
        self.dc("stop", check=False)
        for service in ("donnees", "metier", "proxy"):
            if self.vm_state(service) != "running":
                self.run(["VBoxManage", "startvm", f"vm-{service}", "--type", "headless"])
        rules = self.nat_rules(self.vm_info("proxy"))
        for rule in NAT_RULES:
            if self.nat_rule_needed(rule, rules):
                if rule not in self.created_nat_rules:
                    self.created_nat_rules.append(rule)
                    save(self.nat_path, self.created_nat_rules)
                self.run(["VBoxManage", "controlvm", "vm-proxy", "natpf2", rule])
                rules.append(rule)
        for service in SERVICES:
            deadline = time.monotonic() + 240
            while True:
                try:
                    if self.ssh(service, "true", check=False, timeout=10).returncode == 0:
                        break
                except subprocess.TimeoutExpired:
                    pass  # The guest may still be booting; respect the overall deadline.
                if time.monotonic() > deadline:
                    raise RuntimeError(f"SSH indisponible sur vm-{service} après 240 s")
                time.sleep(3)
        for service in SERVICES:
            self.updates.pause(service, purpose='maintenance' if restoring else 'measurement',
                               check_stop=(lambda: None) if restoring else self.check_stop)


    def request_vm_shutdown(self, service):
        try:
            self.run(["VBoxManage", "controlvm", f"vm-{service}", "acpipowerbutton"])
        except RuntimeError:
            # The guest may have begun shutting down since the state query.
            # Confirm that transition; unrelated command failures still propagate.
            if self.vm_state(service) not in ("stopping", "poweroff", "aborted"):
                raise

    def stop_vm(self):
        # ACPI works even when SSH or the proxy forwarding is unavailable.
        for service in ("metier", "donnees", "proxy"):
            if self.vm_state(service) == "running":
                self.request_vm_shutdown(service)
        deadline = time.monotonic() + 120
        next_acpi = time.monotonic() + 10
        while True:
            pending = {service: self.vm_state(service) for service in SERVICES}
            pending = {service: state for service, state in pending.items() if state not in ("poweroff", "aborted")}
            if not pending:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(f"VM non arrêtées après 120 s (ACPI) : {pending}")
            if time.monotonic() >= next_acpi:
                for service, state in pending.items():
                    if state == "running":
                        self.request_vm_shutdown(service)
                next_acpi = time.monotonic() + 10
            time.sleep(2)
        rules = self.nat_rules(self.vm_info("proxy"))
        for rule in list(self.created_nat_rules):
            if rule in rules:
                self.run(["VBoxManage", "modifyvm", "vm-proxy", "--natpf2", "delete", rule.split(",", 1)[0]])
            self.created_nat_rules.remove(rule)
            save(self.nat_path, self.created_nat_rules)

    def wait_http(self):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen("http://127.0.0.1:8081/health/ready/", timeout=5) as response:
                    if response.status == 200:
                        return
            except OSError:
                pass
            time.sleep(2)
        raise RuntimeError("Measurement proxy unavailable")

    def preflight(self):
        self.check_previous_rests()
        env_text = self.args.env_file.read_text()
        values = dict(line.split("=", 1) for line in env_text.splitlines() if "=" in line and not line.startswith("#"))
        self.pg_user = values["POSTGRES_USER"].strip().strip('"').strip("'")
        values["POSTGRES_DB"] = DATABASE
        private = self.runtime / "docker.env"
        private.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
        private.chmod(0o600)
        snapshot = self.runtime / "base.sql"
        if not snapshot.exists() and not self.owner_path.exists():
            existing = self.dc("ps", "-a", "-q").stdout.strip()
            if existing:
                raise RuntimeError(f"Projet Docker {self.project} sans propriétaire : ressources conservées. Choisir un nouveau MESURE_RUNTIME et MESURE_OUTPUT.")
            if self.docker("volume", "inspect", f"{self.project}_pgdata", check=False).returncode == 0:
                raise RuntimeError(f"Volume Docker {self.project}_pgdata sans propriétaire : ressources conservées. Choisir un nouveau MESURE_RUNTIME et MESURE_OUTPUT.")
        if snapshot.exists() and not (self.runtime / "sources.tar").exists():
            raise RuntimeError("Snapshot sans sources.tar : préparation incomplète conservée. Choisir un nouveau MESURE_RUNTIME et MESURE_OUTPUT.")
        for service in SERVICES:
            self.vm_state(service)
        rules = self.nat_rules(self.vm_info("proxy"))
        for rule in NAT_RULES:
            self.nat_rule_needed(rule, rules)
        # Step 15/16 may still own the measurement port. Preserve their containers.
        containers = self.docker("ps", "--filter", "publish=8081", "--format", "{{.ID}} {{.Label \"com.docker.compose.project\"}}").stdout.decode().splitlines()
        for container in containers:
            fields = container.split()
            if len(fields) != 2 or fields[1] not in (self.project, "intern-mesure"):
                raise RuntimeError("Port 8081 occupé par un autre projet : aucun service arrêté. Libérer ce port avant de relancer.")
        self.suspended_containers = self.docker("ps", "--filter", "label=com.docker.compose.project=intern-mesure", "--format", "{{.ID}}").stdout.decode().split()
        if not self.owner_path.exists():
            self.owner_path.write_text(json.dumps({"project": self.project}) + "\n")
        self.manifest["measurement_project"] = self.project
        diagnostic = self.runtime / "last-error.txt"
        if diagnostic.exists():
            diagnostic.replace(self.runtime / "previous-error.txt")

    def check_previous_rests(self):
        journal = self.output / "journal.jsonl"
        if not journal.exists():
            return
        events = [json.loads(line) for line in journal.read_text().splitlines()]
        for index, event in enumerate(events):
            if event["action"] != "cooldown_start":
                continue
            following = events[index + 1] if index + 1 < len(events) else {}
            if following.get("action") != "cooldown_complete" or following.get("path") != event["path"]:
                raise RuntimeError(f"Repos non validé : {event['path']}. Mesures conservées ; consulter les relevés de repos et choisir un nouveau MESURE_RUNTIME et MESURE_OUTPUT après correction. La reprise ne peut pas sauter ce repos.")

    def preflight_only(self):
        try:
            self.preflight()
        except Exception as error:
            self.manifest.update(status="failed", error=str(error))
            self.record_incident(error, phase="preflight")
            self.event("preflight_failed")
            raise

    def bootstrap(self):
        snapshot = self.runtime / "base.sql"
        self.measurement_touched = True
        if not snapshot.exists():
            # The VM proxy may still reserve 8081. Bootstrap needs only private
            # database/API services; copy frontend assets from a stopped container.
            self.dc("up", "-d", "--no-build", "--wait", "--wait-timeout", "180", "donnees", "metier", timeout=240)
            self.dc("create", "--no-build", "proxy")
            seed = self.dc("exec", "-T", "-e",
                           f"MESURE_ACCOUNTS={max(self.protocol['paliers_utilisateurs'])}",
                           "metier", ".venv/bin/python", "app/manage.py", "shell",
                           "--verbosity", "0", "--command", 'exec(__import__("sys").stdin.read())',
                           data=(ROOT / "scripts/preparer_comptes.py").read_bytes(),
                           timeout=max(90, max(self.protocol["paliers_utilisateurs"]) * 2)).stdout
            if getattr(self.args, "capacity_protocol", None):
                rows = list(csv.DictReader(seed.decode().splitlines()))
                count = max(self.protocol["paliers_utilisateurs"])
                if len(rows) != count or [r["username"] for r in rows] != [f"mesure{n:02d}" for n in range(1, count + 1)]:
                    raise RuntimeError("Capacity fixture accounts differ")
                self.accounts.write_bytes(seed)
            elif seed != self.accounts.read_bytes():
                raise RuntimeError("Fixture accounts differ")
            sql = self.dc("exec", "-T", "donnees", "pg_dump", "-U", self.pg_user,
                          "-d", DATABASE, "--no-owner", "--no-privileges").stdout
            with tempfile.TemporaryDirectory(dir=self.runtime) as directory:
                staging = Path(directory)
                for service, source, target in (("metier", "/app/metier/app", "app"),
                                                ("metier", "/app/donnees", "donnees"),
                                                ("proxy", "/usr/share/nginx/html", "client"),
                                                ("proxy", "/usr/share/nginx/static", "static")):
                    self.docker("cp", f"{self.project}-{service}-1:{source}", str(staging / target))
                with tarfile.open(staging / "sources.tar", "w") as archive:
                    for target, name in (("app", "metier/app"), ("donnees", "donnees"), ("client", "client"), ("static", "static")):
                        archive.add(staging / target, arcname=name)
                (staging / "sources.tar").replace(self.runtime / "sources.tar")
                (staging / "base.sql").write_bytes(sql)
                (staging / "base.sql").chmod(0o600)
                (staging / "base.sql").replace(snapshot)
        self.manifest["snapshot_sha256"] = digest(snapshot)
        self.manifest["accounts_sha256"] = digest(self.accounts)
        self.manifest["sources_sha256"] = digest(self.runtime / "sources.tar")
        images = json.loads(self.docker("inspect", *(f"{self.project}-{service}-1" for service in SERVICES)).stdout)
        self.manifest["images"] = {item["Config"]["Labels"]["com.docker.compose.service"]: item["Image"] for item in images}
        self.manifest["docker_resources"] = {
            item["Config"]["Labels"]["com.docker.compose.service"]:
            {key: item["HostConfig"][key] for key in ("NanoCpus", "Memory")}
            for item in images
        }
        version_code = "import json,platform,django,rest_framework,gunicorn; print(json.dumps(dict(python=platform.python_version(),django=django.get_version(),drf=rest_framework.VERSION,gunicorn=gunicorn.__version__)))"
        # A saved snapshot can belong to an interrupted run with stopped services.
        self.dc("up", "-d", "--no-build", "--wait", "--wait-timeout", "180", "donnees", "metier", timeout=240)
        self.manifest["docker_versions"] = json.loads(self.dc("exec", "-T", "metier", ".venv/bin/python", "-c", version_code).stdout)
        self.dc("stop")
        self.event("common_snapshot_ready")

    def prepare_vm(self):
        for service in SERVICES:
            self.ssh(service, "sudo install -d -m 0755 /opt/intern-mesure17")
            self.ssh(service, "sudo tee /opt/intern-mesure17/metrics_serveur.py >/dev/null",
                     data=(ROOT / "scripts/metrics_serveur.py").read_bytes())
        for service in ("metier", "proxy"):
            self.ssh(service, "sudo tar -xf - -C /opt/intern-mesure17", data=(self.runtime / "sources.tar").read_bytes())
        for service in SERVICES:
            self.ssh(service, f"sudo python3 - {service}", data=(ROOT / "scripts/preparer_vm_mesure.py").read_bytes())
        self.ssh("metier", "sudo systemctl stop intern")
        version_code = "import json,platform,django,rest_framework,gunicorn; print(json.dumps(dict(python=platform.python_version(),django=django.get_version(),drf=rest_framework.VERSION,gunicorn=gunicorn.__version__)))"
        self.manifest["vm_versions"] = json.loads(self.ssh("metier", shlex.join(["/opt/intern/metier/.venv/bin/python", "-c", version_code])).stdout)
        validate_runtime_versions(self.manifest["vm_versions"], self.manifest["docker_versions"])
        self.manifest["vm_configuration"] = {}
        for service in SERVICES:
            info = self.run(["VBoxManage", "showvminfo", f"vm-{service}", "--machinereadable"]).stdout.decode()
            data = dict(line.split("=", 1) for line in info.splitlines() if "=" in line)
            self.manifest["vm_configuration"][service] = {key: data[key].strip('"') for key in ("cpus", "memory", "paravirtprovider")}
        self.event("isolated_vm_services_prepared")

    def reset(self, deployment):
        snapshot = (self.runtime / "base.sql").read_bytes()
        if deployment == "docker":
            self.dc("up", "-d", "--no-build", "--wait", "--wait-timeout", "180", timeout=240)
            self.dc("stop", "metier", "proxy")
            self.dc("exec", "-T", "donnees", "dropdb", "-U", self.pg_user, "--force", "--if-exists", DATABASE)
            self.dc("exec", "-T", "donnees", "createdb", "-U", self.pg_user, "-O", self.pg_user, DATABASE)
            self.dc("exec", "-T", "donnees", "psql", "-U", self.pg_user, "-d", DATABASE, "-v", "ON_ERROR_STOP=1", data=snapshot)
            self.dc("up", "-d", "--no-build", "--wait", "--wait-timeout", "180", timeout=240)
        else:
            self.ssh("metier", "sudo systemctl stop intern intern-mesure17")
            # Only this dedicated database is ever dropped; the original intern database is retained.
            marker = "/opt/intern-mesure17/database-owned"
            self.ssh("donnees", f"set -eu; if [ ! -f {marker} ]; then test \"$(sudo -u postgres psql -XAt -c \"SELECT count(*) FROM pg_database WHERE datname='intern_mesure17'\")\" = 0; sudo touch {marker}; fi")
            self.ssh("donnees", "sudo -u postgres dropdb --force --if-exists intern_mesure17; sudo -u postgres createdb -O intern_user intern_mesure17")
            self.ssh("donnees", "sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d intern_mesure17", data=b"SET ROLE intern_user;\n" + snapshot)
            self.ssh("metier", "sudo systemctl start intern-mesure17")
        self.wait_http()
        if deployment == "docker":
            effective = self.dc("exec", "-T", "metier", ".venv/bin/python", "app/manage.py",
                                "shell", "--verbosity", "0", "--command",
                                "from django.conf import settings; print(settings.AUTH_LOGIN_RATE_LIMIT_ENABLED)")
        else:
            code = b"""import os, pwd, sys
from pathlib import Path
os.environ.update(dict(line.split('=', 1) for line in Path('/etc/intern/mesure17.env').read_text().splitlines() if '=' in line and not line.startswith('#')))
account = pwd.getpwnam('intern')
os.initgroups(account.pw_name, account.pw_gid)
os.setgid(account.pw_gid)
os.setuid(account.pw_uid)
sys.dont_write_bytecode = True
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
sys.path.insert(0, '/opt/intern-mesure17/metier/app')
from django.conf import settings
print(settings.AUTH_LOGIN_RATE_LIMIT_ENABLED)
"""
            effective = self.ssh("metier", "sudo /opt/intern/metier/.venv/bin/python -", data=code)
        if effective.stdout.decode().strip() != "False":
            raise RuntimeError("Measurement login rate limit is still enabled; rebuild the measurement image")
        self.event("login_rate_limit_checked", deployment=deployment, enabled=False)
        self.event("database_restored", deployment=deployment, snapshot_sha256=digest(self.runtime / "base.sql"))

    def collect(self, deployment, folder):
        self.collectors = []
        for service in SERVICES:
            if deployment == "docker":
                pid = self.docker("inspect", f"{self.project}-{service}-1", "--format", "{{.State.Pid}}").stdout.decode().strip()
                command = [sys.executable, str(ROOT / "scripts/metrics_serveur.py"), "--pid", pid, "--service", service]
                if service == "donnees":
                    sql = [self.args.docker, "exec", f"{self.project}-donnees-1", "psql", "-U", self.pg_user, "-d", "postgres", "-XAtc", QUERY]
                    command += ["--sql-command", json.dumps(sql)]
            else:
                pid_command = {"proxy": "cat /run/nginx.pid", "metier": "systemctl show intern-mesure17 -p MainPID --value", "donnees": "head -1 /var/run/postgresql/16-main.pid"}[service]
                pid = self.ssh(service, "sudo " + pid_command).stdout.decode().strip()
                remote = ["sudo", "python3", "/opt/intern-mesure17/metrics_serveur.py", "--pid", pid, "--service", service]
                if service == "donnees":
                    remote += ["--sql-command", json.dumps(["sudo", "-u", "postgres", "psql", "-d", "postgres", "-XAtc", QUERY])]
                command = ["ssh", "-F", self.ssh_config.name, f"vm-{service}", shlex.join(remote)]
            stream = (folder / f"serveur-{service}.jsonl").open("w")
            # Keep each plateau/rest diagnostic; later collectors must not erase it.
            log_folder = self.runtime / "collecteurs" / folder.relative_to(self.output)
            log_folder.mkdir(parents=True, exist_ok=True)
            errors = (log_folder / f"{service}.log").open("w")
            wrapped = [sys.executable, str(ROOT / "scripts/collecteur_serveur.py"), "--command", json.dumps(command)]
            process = subprocess.Popen(wrapped, stdout=stream, stderr=errors, env=self.env,
                                       cwd=self.ssh_config.parent if deployment == "vm" else None)
            self.collectors.append((process, stream, errors))

    def check_collectors(self, folder):
        failures = []
        for process, stream, errors in self.collectors:
            code = process.poll()
            if code is not None:
                failures.append(dict(service=Path(stream.name).stem.removeprefix("serveur-"),
                                     exit_code=code,
                                     diagnostic=str(Path(errors.name).relative_to(self.runtime))))
        if failures:
            save(folder / "collecteurs-echec.json", dict(collectors=failures))
            self.manifest["collector_errors"] = failures
            self.event("collector_failed", collectors=failures, path=str(folder.relative_to(self.output)))
            details = "; ".join(f"{r['service']} (exit {r['exit_code']}, log: {r['diagnostic']})" for r in failures)
            raise RuntimeError("Server collector stopped: " + details + "; plateau preserved")

    def stop_collectors(self):
        for process, stream, errors in self.collectors:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            stream.close()
            errors.close()
        self.collectors = []

    def server_summary(self, folder):
        client = json.loads((folder / "synthese.json").read_text())
        result = {}
        for service in SERVICES:
            rows = [json.loads(line) for line in (folder / f"serveur-{service}.jsonl").read_text().splitlines()]
            stable = [row for row in rows if row["epoch_s"] - row["interval_s"] >= client["window_start_ms"] / 1000
                      and row["epoch_s"] <= client["window_end_ms"] / 1000]
            if len(stable) < 15:
                raise RuntimeError("Insufficient server samples: " + service)
            result[service] = {"samples": len(stable), "cpu_io_methods": sorted({row["cpu_io_method"] for row in stable})}
            for field in ("cpu_pct", "rss_bytes", "memory_cgroup_bytes", "read_bytes_per_s", "write_bytes_per_s", "db_connections", "db_active_connections"):
                values = [row[field] for row in stable if row.get(field) is not None]
                if values:
                    result[service][field + "_mean"] = statistics.mean(values)
                    result[service][field + "_max"] = max(values)
        save(folder / "serveurs.json", result)

    def campaign(self, deployment, series):
        self.check_stop()
        if all((self.output / f"serie-{series}/{deployment}/{users}/serveurs.json").exists()
               for users in self.protocol["paliers_utilisateurs"]):
            self.event("campaign_already_complete", series=series, deployment=deployment)
            return
        self.reset(deployment)
        for index, users in enumerate(self.protocol["paliers_utilisateurs"]):
            self.check_stop()
            name = f"serie-{series}/{deployment}/{users}"
            folder = self.output / name
            if (folder / "serveurs.json").exists():
                continue
            self.run_plateau(deployment, series, users)
            if index + 1 < len(self.protocol["paliers_utilisateurs"]):
                self.cooldown(deployment, series, users)

    def run_plateau(self, deployment, series, users):
        name = f"serie-{series}/{deployment}/{users}"
        folder = self.output / name
        folder.parent.mkdir(parents=True, exist_ok=True)
        if folder.exists():
            raise RuntimeError("Partial palier exists; preserve and review before resuming")
        # The measurement runner creates the output directory itself.
        self.event("palier_start", series=series, deployment=deployment, users=users)
        command = [sys.executable, str(ROOT / "scripts/etalonnage.py"), "application", "--jmeter", self.args.jmeter,
                   "--users", str(users), "--output", str(folder),
                   "--accounts", str(self.accounts), "--protocol", str(self.protocol_path),
                   "--private-log", str(self.runtime / "jmeter" / name / "jmeter.log")]
        if getattr(self.args, "capacity_protocol", None):
            command += ["--capacity-guard"]
        with (self.runtime / "runner.log").open("w") as console:
            process = subprocess.Popen(command, stdout=console, stderr=console, env=self.env, start_new_session=True)
            try:
                deadline = time.monotonic() + 20
                while not folder.exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Measurement runner failed to start")
                    time.sleep(.1)
                self.collect(deployment, folder)
                while process.poll() is None:
                    self.check_stop()
                    if getattr(self.args, "capacity_protocol", None):
                        self.check_capacity_health(folder)
                    time.sleep(2)
                if process.returncode:
                    raise RuntimeError("Measurement runner failed; inspect private runner.log")
            finally:
                self.terminate_runner(process)
                self.stop_collectors()
        self.server_summary(folder)
        client = json.loads((folder / "synthese.json").read_text())
        self.manifest["runs"].append({"series": series, "deployment": deployment, "users": users,
                                      "path": name, "errors": client["all_errors"]})
        self.event("palier_complete", series=series, deployment=deployment, users=users,
                   requests=client["requests"], errors=client["all_errors"])

    @staticmethod
    def terminate_runner(process):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()

    def cooldown(self, deployment, series, users):
        policy = self.protocol["repos_dynamique"]
        folder = self.output / f"repos/serie-{series}/{deployment}/{users}"
        folder.mkdir(parents=True, exist_ok=False)
        started = time.monotonic()
        self.event("cooldown_start", series=series, deployment=deployment, users=users,
                   path=str(folder.relative_to(self.output)))
        blockers = [{"reason": "minimum_rest_not_reached"}]
        try:
            self.collect(deployment, folder)
            while time.monotonic() - started < policy["maximum_s"]:
                self.check_stop()
                self.check_collectors(folder)
                time.sleep(2)
                elapsed = time.monotonic() - started
                if elapsed < policy["minimum_s"]:
                    continue
                idle_epoch = time.time()
                samples = {}
                for service in SERVICES:
                    lines = (folder / f"serveur-{service}.jsonl").read_text().splitlines()
                    # A collector can be in the middle of writing its last line.
                    samples[service] = []
                    for line in lines:
                        try:
                            row = json.loads(line)
                            if row["epoch_s"] <= idle_epoch:
                                samples[service].append(row)
                        except json.JSONDecodeError:
                            break
                blockers = idle_blockers(samples, idle_epoch, policy)
                if not blockers:
                    try:
                        with urllib.request.urlopen("http://127.0.0.1:8081/health/ready/", timeout=5) as response:
                            ready = response.status == 200
                    except OSError:
                        ready = False
                    if not ready:
                        blockers = [{"service": "proxy", "reason": "http_not_ready"}]
                    if ready:
                        self.event("cooldown_complete", series=series, deployment=deployment,
                                   users=users, path=str(folder.relative_to(self.output)),
                                   elapsed_s=time.monotonic() - started, ready=True,
                                   idle_epoch_s=idle_epoch)
                        return
            diagnostic = dict(policy=policy, blockers=blockers)
            save(folder / "diagnostic.json", diagnostic)
            self.event("cooldown_failed", series=series, deployment=deployment, users=users,
                       path=str(folder.relative_to(self.output)), **diagnostic)
            raise RuntimeError("Services did not return to idle within the frozen maximum rest: "
                               + json.dumps(blockers, ensure_ascii=False))
        finally:
            self.stop_collectors()

    def restore_vm_configuration(self, timer_policies):
        # Masks survive the powered-off Docker passes. Reopen SSH if cleanup is needed there.
        if self.updates.touched and any(self.vm_state(s) != "running" for s in SERVICES):
            self.boot_vm(restoring=True)
        if self.vm_state("proxy") == "running":
            self.ssh("metier", "if [ -f /opt/intern-mesure17/.measurement-owned ]; then sudo systemctl stop intern-mesure17; sudo rm -f /etc/intern/mesure17.env /etc/systemd/system/intern-mesure17.service; sudo systemctl daemon-reload; sudo systemctl start intern; fi", check=False)
            self.ssh("proxy", "if [ -f /opt/intern-mesure17/.measurement-owned ]; then sudo rm -f /etc/nginx/conf.d/mesure17.conf; sudo nginx -t && sudo systemctl reload nginx; fi", check=False)
            self.ssh("donnees", "if [ -f /opt/intern-mesure17/.measurement-owned ] && [ -f /etc/postgresql/16/main/pg_hba.conf.before-mesure17 ]; then sudo cp /etc/postgresql/16/main/pg_hba.conf.before-mesure17 /etc/postgresql/16/main/pg_hba.conf; sudo systemctl reload postgresql@16-main; fi", check=False)
        for service in SERVICES:
            if service in self.updates.touched:
                state = self.updates.restore(service, poweroff=True)
                timer_policies[service] = state.get("restored_timers", [])

    def restore_vm(self):
        timer_policies = {}
        try:
            self.restore_vm_configuration(timer_policies)
        finally:
            # Even permanent SSH failure must not leave the proxy reserving
            # 8080 and thereby prevent the independent Docker restoration.
            try:
                self.stop_vm()
            except Exception:
                # If shutdown fails, restart only the original timers already restored.
                for service, timers in timer_policies.items():
                    if timers and self.vm_state(service) == "running":
                        self.ssh(service, shlex.join(["sudo", "systemctl", "start", *timers]), check=False)
                raise

    def archive_measurement_logs(self):
        containers = self.dc("ps", "-a", "-q").stdout.decode().split()
        directory = self.runtime / "container-logs"
        directory.mkdir(mode=0o700, exist_ok=True)
        for container in containers:
            result = self.docker("logs", "--timestamps", container, check=False)
            with tempfile.NamedTemporaryFile(dir=directory, prefix=container + "-", suffix=".log",
                                             delete=False) as stream:
                stream.write(result.stdout)
                stream.write(result.stderr)
                path = Path(stream.name)
            self.manifest.setdefault("docker_log_archives", []).append(str(path.relative_to(self.runtime)))
            if result.returncode:
                raise RuntimeError("Cannot read logs for measurement container " + container)

    def restore(self):
        errors = []

        def attempt(action, callback):
            try:
                callback()
            except Exception as error:
                errors.append(f"{action}: {error}")

        attempt("collecteurs", self.stop_collectors)
        if self.measurement_touched:
            # Capacity runs are immutable. Release their per-run networks while
            # keeping named volumes, private snapshots and measurement evidence.
            if self.manifest.get("kind") in ("capacity", "worker"):
                try:
                    self.archive_measurement_logs()
                except Exception as error:
                    self.manifest.setdefault("diagnostic_errors", []).append("Docker logs: " + str(error))
                    print("Cannot archive measurement container logs; cleanup continues", file=sys.stderr, flush=True)
                attempt("Docker de mesure", lambda: self.dc("down", "--timeout", "30", timeout=90))
            else:
                attempt("Docker de mesure", lambda: self.dc("stop"))
        if self.vm_touched:
            attempt("VM", self.restore_vm)
        # A VM error must not prevent Docker restoration.
        if self.reference_touched:
            attempt("Docker de référence", lambda: self.run(
                [*self.reference, "up", "-d", "--no-build", "--wait", "--wait-timeout", "180"], timeout=240))
        if self.calibration_touched and self.suspended_containers:
            attempt("Docker d’étalonnage", lambda: self.docker("start", *self.suspended_containers))
        if errors:
            self.manifest["restoration_errors"] = errors
            self.record_incident(RuntimeError("; ".join(errors)), phase="restoration")
            self.event("restoration_failed", errors=errors)
            raise RuntimeError("Restauration incomplète ; consulter statut et controller.log")
        if self.reference_touched:
            self.manifest.pop("restoration_errors", None)
            self.event("reference_restored")

    def main(self):
        previous_handlers = {}
        self.stop_requested = False

        def request_stop(signum, frame):
            # A second signal must not interrupt recovery or package-manager cleanup.
            self.stop_requested = True

        try:
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous_handlers[signum] = signal.signal(signum, request_stop)
            with operation_lock(ROOT.parent / '.execution/operations-vm.lock'):
                self.run_campaigns()
        except RuntimeError as error:
            if self.manifest["status"] != "failed" and not self.reference_touched and not self.vm_touched and not self.measurement_touched:
                self.manifest.update(status="failed", error=str(error))
                self.record_incident(error, phase="operation_lock")
                self.event("campaigns_refused")
            raise
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)

    def run_campaigns(self):
        primary_error = None
        try:
            if getattr(self, "resuming", False):
                self.resume_work()
                return
            self.preflight()
            self.manifest.pop("error", None)
            self.manifest.pop("restoration_errors", None)
            self.reference_touched = True
            self.run([*self.reference, "stop"])
            if self.suspended_containers:
                self.calibration_touched = True
                self.docker("stop", *self.suspended_containers)
            self.bootstrap()
            self.boot_vm()
            self.prepare_vm()
            self.manifest["status"] = "running"
            self.campaign("vm", 1)
            self.stop_vm()
            self.campaign("docker", 1)
            self.dc("stop")
            self.campaign("docker", 2)
            self.dc("stop")
            self.boot_vm()
            self.ssh("metier", "sudo systemctl stop intern")
            self.campaign("vm", 2)
            self.manifest["status"] = "complete"
            self.manifest["finished_epoch_s"] = time.time()
            self.event("campaigns_complete")
        except BaseException as error:
            primary_error = error
            self.manifest["error"] = str(error)
            self.manifest["status"] = "stopped" if isinstance(error, InterruptedError) else "failed"
            try:
                if (self.runtime / "last-error.txt").exists():
                    (self.runtime / "campaign-error.txt").write_bytes((self.runtime / "last-error.txt").read_bytes())
                self.record_incident(error)
                self.event("campaigns_stopped" if isinstance(error, InterruptedError) else "campaigns_failed")
            except OSError as diagnostic_error:
                # Full/unavailable storage must not skip recovery or mask the cause.
                print(f"Failure: {error}; cannot save diagnostics: {diagnostic_error}", file=sys.stderr, flush=True)
            raise
        finally:
            try:
                self.restore()
            except Exception:
                if primary_error is None:
                    self.manifest["status"] = "failed"
                    save(self.manifest_path, self.manifest)
                    raise
                # The restoration failure is already recorded; retain the original traceback.
                print("Restauration incomplète ; consulter statut et controller.log", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", required=True)
    parser.add_argument("--docker-host", required=True)
    parser.add_argument("--docker-config", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    parser.add_argument("--jmeter", required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "resultats/etape17")
    parser.add_argument("--reference-project", default="intern-etape14")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--capacity-protocol", type=Path)
    args = parser.parse_args()
    if args.capacity_protocol:
        if json.loads(args.capacity_protocol.read_text()).get("worker_comparison"):
            from workers import WorkerCampaign
            controller = WorkerCampaign(args)
        else:
            from capacite import CapacityCampaign
            controller = CapacityCampaign(args)
    else:
        controller = Campaigns(args)
    if args.preflight:
        controller.preflight_only()
    else:
        controller.main()


if __name__ == "__main__":
    main()
