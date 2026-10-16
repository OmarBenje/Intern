"""Run paired VM/Docker campaigns with a common snapshot and per-service metrics."""

import argparse
import csv
import hashlib
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
import time
import urllib.request

from etalonnage import ROOT, PERFORMANCE_PROTOCOL, digest, save
from repos import idle_window

DATABASE = "intern_mesure17"
PROJECT = "intern-etape17"
SERVICES = ("proxy", "metier", "donnees")
QUERY = """SELECT json_build_object(
'db_connections',(SELECT count(*) FROM pg_stat_activity WHERE datname='intern_mesure17'),
'db_active_connections',(SELECT count(*) FROM pg_stat_activity WHERE datname='intern_mesure17' AND state='active'),
'db_blocks_read',blks_read,'db_blocks_hit',blks_hit,'db_transactions',xact_commit+xact_rollback)
FROM pg_stat_database WHERE datname='intern_mesure17';"""


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
        self.protocol = json.loads(PERFORMANCE_PROTOCOL.read_text())
        if max(self.protocol["paliers_utilisateurs"]) > 20:
            raise RuntimeError("This calibrated campaign supports at most twenty users")
        self.env = {**os.environ, "DOCKER_HOST": args.docker_host, "DOCKER_CONFIG": str(args.docker_config)}
        self.compose = [args.docker, "compose", "--env-file", str(self.runtime / "docker.env"),
                        "-f", str(ROOT.parent / "docker/compose.yaml"),
                        "-f", str(ROOT / "compose.test.yaml"), "-p", PROJECT]
        self.reference = [args.docker, "compose", "--env-file", str(args.env_file.resolve()),
                          "-f", str(ROOT.parent / "docker/compose.yaml"), "-p", args.reference_project]
        self.ssh_config = args.ssh_config.resolve()
        self.collectors = []
        self.manifest_path = self.output / "manifest.json"
        self.manifest = json.loads(self.manifest_path.read_text()) if self.manifest_path.exists() else {
            "status": "preparing", "protocol_sha256": digest(PERFORMANCE_PROTOCOL),
            "source_plan_sha256": digest(ROOT / "plan.jmx"), "order": ["vm", "docker", "docker", "vm"],
            "runs": [], "started_epoch_s": time.time(),
        }
        if self.manifest["protocol_sha256"] != digest(PERFORMANCE_PROTOCOL):
            raise RuntimeError("Protocol changed since campaign preparation")

    def event(self, action, **fields):
        value = {"epoch_s": time.time(), "action": action, **fields}
        with (self.output / "journal.jsonl").open("a") as stream:
            stream.write(json.dumps(value) + "\n")
        self.manifest["progress"] = value
        save(self.manifest_path, self.manifest)
        print(json.dumps(value), flush=True)

    def check_stop(self):
        if (self.runtime / "stop-requested").exists():
            raise InterruptedError("Graceful stop requested")

    def run(self, command, *, data=None, check=True, timeout=90, cwd=None):
        result = subprocess.run(command, input=data, capture_output=True, env=self.env, timeout=timeout, cwd=cwd)
        if check and result.returncode:
            # Keep diagnostics outside deliverables; they can contain local paths.
            (self.runtime / "last-error.txt").write_bytes(result.stderr)
            raise RuntimeError("Command failed; diagnostic saved in the private runtime directory")
        return result

    def docker(self, *parts, **kwargs):
        return self.run([self.args.docker, *parts], **kwargs)

    def dc(self, *parts, **kwargs):
        return self.run([*self.compose, *parts], **kwargs)

    def ssh(self, service, command, **kwargs):
        return self.run(["ssh", "-F", self.ssh_config.name, f"vm-{service}", command], cwd=self.ssh_config.parent, **kwargs)

    def vm_state(self, service):
        info = self.run(["VBoxManage", "showvminfo", f"vm-{service}", "--machinereadable"]).stdout.decode()
        return next(line.split("=", 1)[1].strip('"') for line in info.splitlines() if line.startswith("VMState="))

    def boot_vm(self):
        self.dc("stop", check=False)
        for service in ("donnees", "metier", "proxy"):
            if self.vm_state(service) != "running":
                self.run(["VBoxManage", "startvm", f"vm-{service}", "--type", "headless"])
        info = self.run(["VBoxManage", "showvminfo", "vm-proxy", "--machinereadable"]).stdout.decode()
        for rule in ("ssh-mesure17,tcp,127.0.0.1,2221,,22", "http-mesure17,tcp,127.0.0.1,8081,,8082"):
            if rule.split(",", 1)[0] not in info:
                self.run(["VBoxManage", "controlvm", "vm-proxy", "natpf2", rule])
        for service in SERVICES:
            deadline = time.monotonic() + 240
            while self.ssh(service, "true", check=False, timeout=10).returncode:
                if time.monotonic() > deadline:
                    raise RuntimeError("SSH unavailable")
                time.sleep(3)

    def stop_vm(self):
        for service in ("metier", "donnees", "proxy"):
            if self.vm_state(service) == "running":
                self.ssh(service, "sudo systemctl poweroff", check=False, timeout=20)
        for service in SERVICES:
            deadline = time.monotonic() + 120
            while self.vm_state(service) == "running":
                if time.monotonic() > deadline:
                    raise RuntimeError("VM failed to stop")
                time.sleep(2)
        for name in ("ssh-mesure17", "http-mesure17"):
            self.run(["VBoxManage", "modifyvm", "vm-proxy", "--natpf2", "delete", name], check=False)

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

    def bootstrap(self):
        env_text = self.args.env_file.read_text()
        values = dict(line.split("=", 1) for line in env_text.splitlines() if "=" in line and not line.startswith("#"))
        self.pg_user = values["POSTGRES_USER"].strip().strip('"').strip("'")
        values["POSTGRES_DB"] = DATABASE
        private = self.runtime / "docker.env"
        private.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
        private.chmod(0o600)
        snapshot = self.runtime / "base.sql"
        if not snapshot.exists():
            existing = self.dc("ps", "-a", "-q").stdout.strip()
            if existing:
                raise RuntimeError("Refuse to reuse an unowned measurement project")
            if self.docker("volume", "inspect", f"{PROJECT}_pgdata", check=False).returncode == 0:
                raise RuntimeError("Refuse to reuse an unowned measurement volume")
            self.dc("up", "-d", "--no-build", "--wait", "--wait-timeout", "180", timeout=240)
            seed = self.dc("exec", "-T", "metier", ".venv/bin/python", "app/manage.py", "shell",
                           "--verbosity", "0", "--command", 'exec(__import__("sys").stdin.read())',
                           data=(ROOT / "scripts/preparer_comptes.py").read_bytes()).stdout
            if seed != (ROOT / "comptes.csv").read_bytes():
                raise RuntimeError("Fixture accounts differ")
            snapshot.write_bytes(self.dc("exec", "-T", "donnees", "pg_dump", "-U", self.pg_user,
                                        "-d", DATABASE, "--no-owner", "--no-privileges").stdout)
            snapshot.chmod(0o600)
            self.docker("cp", f"{PROJECT}-metier-1:/app/metier/app", str(self.runtime / "app"))
            self.docker("cp", f"{PROJECT}-metier-1:/app/donnees", str(self.runtime / "donnees"))
            self.docker("cp", f"{PROJECT}-proxy-1:/usr/share/nginx/html", str(self.runtime / "client"))
            self.docker("cp", f"{PROJECT}-proxy-1:/usr/share/nginx/static", str(self.runtime / "static"))
            with tarfile.open(self.runtime / "sources.tar", "w") as archive:
                archive.add(self.runtime / "app", arcname="metier/app")
                archive.add(self.runtime / "donnees", arcname="donnees")
                archive.add(self.runtime / "client", arcname="client")
                archive.add(self.runtime / "static", arcname="static")
        self.manifest["snapshot_sha256"] = digest(snapshot)
        self.manifest["accounts_sha256"] = digest(ROOT / "comptes.csv")
        self.manifest["sources_sha256"] = digest(self.runtime / "sources.tar")
        images = json.loads(self.docker("inspect", *(f"{PROJECT}-{service}-1" for service in SERVICES)).stdout)
        self.manifest["images"] = {item["Config"]["Labels"]["com.docker.compose.service"]: item["Image"] for item in images}
        self.manifest["docker_resources"] = {
            item["Config"]["Labels"]["com.docker.compose.service"]:
            {key: item["HostConfig"][key] for key in ("NanoCpus", "Memory")}
            for item in images
        }
        version_code = "import json,platform,django,rest_framework,gunicorn; print(json.dumps(dict(python=platform.python_version(),django=django.get_version(),drf=rest_framework.VERSION,gunicorn=gunicorn.__version__)))"
        # A saved snapshot can belong to an interrupted run with stopped services.
        self.dc("up", "-d", "--no-build", "--wait", "--wait-timeout", "180", timeout=240)
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
        for library in ("django", "drf", "gunicorn"):
            if self.manifest["vm_versions"][library] != self.manifest["docker_versions"][library]:
                raise RuntimeError("VM and Docker dependency versions differ: " + library)
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
            code = b"""import os, sys
from pathlib import Path
os.environ.update(dict(line.split('=', 1) for line in Path('/etc/intern/mesure17.env').read_text().splitlines() if '=' in line and not line.startswith('#')))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
sys.path.insert(0, '/opt/intern-mesure17/metier/app')
from django.conf import settings
print(settings.AUTH_LOGIN_RATE_LIMIT_ENABLED)
"""
            effective = self.ssh("metier", "sudo -u intern /opt/intern/metier/.venv/bin/python -", data=code)
        if effective.stdout.decode().strip() != "False":
            raise RuntimeError("Measurement login rate limit is still enabled; rebuild the measurement image")
        self.event("login_rate_limit_checked", deployment=deployment, enabled=False)
        self.event("database_restored", deployment=deployment, snapshot_sha256=digest(self.runtime / "base.sql"))

    def collect(self, deployment, folder):
        self.collectors = []
        for service in SERVICES:
            if deployment == "docker":
                pid = self.docker("inspect", f"{PROJECT}-{service}-1", "--format", "{{.State.Pid}}").stdout.decode().strip()
                command = [sys.executable, str(ROOT / "scripts/metrics_serveur.py"), "--pid", pid, "--service", service]
                if service == "donnees":
                    sql = [self.args.docker, "exec", f"{PROJECT}-donnees-1", "psql", "-U", self.pg_user, "-d", "postgres", "-XAtc", QUERY]
                    command += ["--sql-command", json.dumps(sql)]
            else:
                pid_command = {"proxy": "cat /run/nginx.pid", "metier": "systemctl show intern-mesure17 -p MainPID --value", "donnees": "head -1 /var/run/postgresql/16-main.pid"}[service]
                pid = self.ssh(service, "sudo " + pid_command).stdout.decode().strip()
                remote = ["sudo", "python3", "/opt/intern-mesure17/metrics_serveur.py", "--pid", pid, "--service", service]
                if service == "donnees":
                    remote += ["--sql-command", json.dumps(["sudo", "-u", "postgres", "psql", "-d", "postgres", "-XAtc", QUERY])]
                command = ["ssh", "-F", self.ssh_config.name, f"vm-{service}", shlex.join(remote)]
            stream = (folder / f"serveur-{service}.jsonl").open("w")
            errors = (self.runtime / f"collector-{service}.log").open("w")
            wrapped = [sys.executable, str(ROOT / "scripts/collecteur_serveur.py"), "--command", json.dumps(command)]
            process = subprocess.Popen(wrapped, stdout=stream, stderr=errors, env=self.env,
                                       cwd=self.ssh_config.parent if deployment == "vm" else None)
            self.collectors.append((process, stream, errors))

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
            folder.parent.mkdir(parents=True, exist_ok=True)
            if folder.exists():
                raise RuntimeError("Partial palier exists; preserve and review before resuming")
            # The measurement runner creates the output directory itself.
            self.event("palier_start", series=series, deployment=deployment, users=users)
            command = [sys.executable, str(ROOT / "scripts/etalonnage.py"), "application", "--jmeter", self.args.jmeter,
                       "--users", str(users), "--output", str(folder)]
            console = (self.runtime / "runner.log").open("w")
            process = subprocess.Popen(command, stdout=console, stderr=console, env=self.env, start_new_session=True)
            deadline = time.monotonic() + 20
            while not folder.exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Measurement runner failed to start")
                time.sleep(.1)
            self.collect(deployment, folder)
            while process.poll() is None:
                if (self.runtime / "stop-requested").exists():
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=20)
                    self.stop_collectors()
                    console.close()
                    self.check_stop()
                time.sleep(2)
            code = process.returncode
            console.close()
            self.stop_collectors()
            if code:
                raise RuntimeError("Measurement runner failed; inspect private runner.log")
            self.server_summary(folder)
            client = json.loads((folder / "synthese.json").read_text())
            self.manifest["runs"].append({"series": series, "deployment": deployment, "users": users,
                                          "path": name, "errors": client["all_errors"]})
            self.event("palier_complete", series=series, deployment=deployment, users=users,
                       requests=client["requests"], errors=client["all_errors"])
            if index + 1 < len(self.protocol["paliers_utilisateurs"]):
                self.cooldown(deployment, series, users)

    def cooldown(self, deployment, series, users):
        policy = self.protocol["repos_dynamique"]
        folder = self.output / f"repos/serie-{series}/{deployment}/{users}"
        folder.mkdir(parents=True, exist_ok=False)
        started = time.monotonic()
        self.event("cooldown_start", series=series, deployment=deployment, users=users,
                   path=str(folder.relative_to(self.output)))
        try:
            self.collect(deployment, folder)
            while time.monotonic() - started < policy["maximum_s"]:
                self.check_stop()
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
                if idle_window(samples, idle_epoch, policy):
                    try:
                        with urllib.request.urlopen("http://127.0.0.1:8081/health/ready/", timeout=5) as response:
                            ready = response.status == 200
                    except OSError:
                        ready = False
                    if ready:
                        self.event("cooldown_complete", series=series, deployment=deployment,
                                   users=users, path=str(folder.relative_to(self.output)),
                                   elapsed_s=time.monotonic() - started, ready=True,
                                   idle_epoch_s=idle_epoch)
                        return
            raise RuntimeError("Services did not return to idle within the frozen maximum rest")
        finally:
            self.stop_collectors()

    def restore(self):
        self.stop_collectors()
        self.dc("stop", check=False)
        if self.vm_state("proxy") == "running":
            self.ssh("metier", "if [ -f /opt/intern-mesure17/.measurement-owned ]; then sudo systemctl stop intern-mesure17; sudo rm -f /etc/intern/mesure17.env /etc/systemd/system/intern-mesure17.service; sudo systemctl daemon-reload; sudo systemctl start intern; fi", check=False)
            self.ssh("proxy", "if [ -f /opt/intern-mesure17/.measurement-owned ]; then sudo rm -f /etc/nginx/conf.d/mesure17.conf; sudo nginx -t && sudo systemctl reload nginx; fi", check=False)
            self.ssh("donnees", "if [ -f /opt/intern-mesure17/.measurement-owned ] && [ -f /etc/postgresql/16/main/pg_hba.conf.before-mesure17 ]; then sudo cp /etc/postgresql/16/main/pg_hba.conf.before-mesure17 /etc/postgresql/16/main/pg_hba.conf; sudo systemctl reload postgresql@16-main; fi", check=False)
        self.stop_vm()
        self.run([*self.reference, "up", "-d", "--no-build", "--wait", "--wait-timeout", "180"], timeout=240)
        self.event("reference_restored")

    def main(self):
        try:
            self.run([*self.reference, "stop"])
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
            self.manifest["status"] = "stopped" if isinstance(error, InterruptedError) else "failed"
            self.event("campaigns_stopped" if isinstance(error, InterruptedError) else "campaigns_failed")
            raise
        finally:
            self.restore()


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
    Campaigns(parser.parse_args()).main()


if __name__ == "__main__":
    main()
