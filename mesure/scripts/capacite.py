"""Adaptive capacity search on isolated deployments, with conservative conclusions."""

import csv
import json
import math
import statistics
import subprocess
import time
import sys
import urllib.error
import urllib.request

from campagnes17 import Campaigns, SERVICES
from etalonnage import ROOT, digest, save, memory_blockers, machine_snapshot


class CalibrationRejected(RuntimeError):
    """Completed calibration with insufficient or invalid measurement evidence."""


def acceptable(sample, policy):
    return (sample.get("plateau_valid", False)
            and sample["p95_ms"] is not None and sample["p95_ms"] <= policy["p95_max_ms"]
            and sample["error_pct"] <= policy["erreurs_max_pct"])


def bracket(samples, policy):
    good, bad = 0, None
    for users, sample in sorted(samples.items()):
        if acceptable(sample, policy):
            if bad is not None:
                raise RuntimeError("Non-monotonic service thresholds; stabilize and repeat the campaign")
            good = users
        elif bad is None:
            bad = users
    return good, bad


def refinement(good, bad, step):
    if bad is None or bad - good <= step or bad - good <= 1:
        return None
    return good + (bad - good) // 2


def variation(a, b):
    return abs(a - b) / ((a + b) / 2) * 100 if a + b else 0


def sustained_cpu_max(rows, field, window_s):
    """Maximum time-weighted CPU over a fully observed contiguous window.

    Each reading describes the interval ending at its timestamp. Gaps longer
    than five seconds cannot establish a sustained CPU condition.
    """
    intervals = []
    for previous, current in zip(rows, rows[1:]):
        start, end = float(previous["epoch_s"]), float(current["epoch_s"])
        value = float(current[field])
        if not all(math.isfinite(v) for v in (start, end, value)) or end <= start or value < 0:
            return None
        if end - start <= 5:
            intervals.append((start, end, value))
    candidates = {end for _, end, _ in intervals}
    candidates.update(start + window_s for start, _, _ in intervals)
    maximum = None
    for end in candidates:
        duration, total = 0, 0
        for start, stop, value in intervals:
            overlap = max(0, min(stop, end) - max(start, end - window_s))
            duration += overlap
            total += value * overlap
        if math.isclose(duration, window_s, abs_tol=1e-6):
            average = total / window_s
            maximum = average if maximum is None else max(maximum, average)
    return maximum


def cpu_assessment(rows, policy):
    window = policy.get("cpu_soutenu_s")
    if window is None:
        return {}  # Frozen legacy protocols retain their maximum-sample rule.
    result = {field: sustained_cpu_max(rows, field, window)
              for field in ("injector_cpu_pct", "host_busy_pct")}
    cores = policy.get("injecteur_cpu_capacite_coeurs", 1)
    if result["injector_cpu_pct"] is not None:
        result["injector_cpu_pct"] /= cores
    return result


def injector_blockers(folder, policy, check_cpu=True):
    sample = json.loads((folder / "synthese.json").read_text())
    reasons = []
    with (folder / "ressources.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    stable = [row for row in rows if sample["window_start_ms"] / 1000 <= float(row["epoch_s"]) <= sample["window_end_ms"] / 1000]
    if not stable:
        return reasons + ["missing_injector_readings"]
    if check_cpu:
        assessment = cpu_assessment(stable, policy)
        for field, limit in (("injector_cpu_pct", policy["injecteur_cpu_max_pct"]),
                             ("host_busy_pct", policy["hote_cpu_max_pct"])):
            if "cpu_soutenu_s" in policy:
                value = assessment[field]
                if value is None:
                    reasons.append("missing_sustained_cpu_readings")
                elif value >= limit:
                    reasons.append(field + "_sustained")
            elif sample[field + "_max"] >= limit:
                reasons.append(field + "_max")
    for field in ("injector_cpu_pct", "injector_rss_bytes", "host_busy_pct"):
        values = [float(row[field]) for row in stable]
        if not all(math.isfinite(v) and v >= 0 for v in values):
            reasons.append("invalid_injector_readings")
            continue
        for suffix, function in (("mean", statistics.mean), ("max", max)):
            if not math.isclose(sample[field + "_" + suffix], function(values), rel_tol=1e-9):
                reasons.append("injector_summary_mismatch")
    previous = {key: float(value) for key, value in rows[0].items()}
    for row in stable:
        current = {key: float(value) for key, value in row.items()}
        reasons.extend(memory_blockers(current, previous, policy))
        previous = current
    return sorted(set(reasons))


class CapacityCampaign(Campaigns):
    def __init__(self, args):
        protocol = json.loads(args.capacity_protocol.read_text())
        levels = protocol["paliers_utilisateurs"]
        if not levels or any(type(n) is not int or n < 1 for n in levels) or levels != sorted(set(levels)):
            raise RuntimeError("Capacity levels must be distinct increasing positive integers")
        if (protocol["montee_s"], protocol["stabilisation_s"], protocol["plateau_s"], protocol["reflexion_ms"]) != (30, 15, 120, 1000):
            raise RuntimeError("Capacity timing must remain 30/15/120 seconds with 1 second reflection")
        policy = protocol["capacite"]
        if type(policy.get("swap_avec_pression_uniquement", False)) is not bool:
            raise RuntimeError("swap_avec_pression_uniquement must be a boolean")
        if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
               for key, v in policy.items() if key != "swap_avec_pression_uniquement"):
            raise RuntimeError("Capacity policy thresholds must be finite positive numbers")
        if policy["affinement_pas"] != int(policy["affinement_pas"]):
            raise RuntimeError("Refinement step must be an integer")
        if "cpu_soutenu_s" in policy and not 2 <= policy["cpu_soutenu_s"] <= protocol["plateau_s"] / 2:
            raise RuntimeError("Sustained CPU window must be between 2 seconds and half the plateau")
        # Freeze a copy, including thresholds, before any infrastructure is changed.
        output = args.output.resolve()
        if not output.is_relative_to(ROOT / "resultats") or output == ROOT / "resultats/etape17":
            raise RuntimeError("Use a distinct capacity output under mesure/resultats/")
        if (output / "manifest.json").exists():
            raise RuntimeError("Capacity campaigns are immutable; use a fresh runtime and output after interruption")
        if (args.runtime / "base.sql").exists():
            raise RuntimeError("Capacity search requires a fresh private runtime")
        output.mkdir(parents=True, exist_ok=True)
        frozen = output / "protocole.json"
        if frozen.exists() and frozen.read_bytes() != args.capacity_protocol.read_bytes():
            raise RuntimeError("Frozen capacity protocol differs")
        frozen.write_bytes(args.capacity_protocol.read_bytes())
        args.capacity_protocol = frozen
        super().__init__(args)
        self.policy = self.protocol["capacite"]
        self.manifest.update(kind="capacity", accounts_file="comptes.csv", blocks=[])
        self.health_failures = 0
        self.previous_machine = machine_snapshot()
        self.calibrated = set()

    def check_capacity_health(self, folder):
        self.check_collectors(folder)
        timeout = self.policy.get("disponibilite_timeout_s", 2)
        probe = dict(epoch_s=time.time(), timeout_s=timeout, status=None, error=None)
        started = time.monotonic()
        try:
            with urllib.request.urlopen("http://127.0.0.1:8081/health/ready/", timeout=timeout) as response:
                probe["status"] = response.status
                ready = response.status == 200
        except OSError as error:
            if isinstance(error, urllib.error.HTTPError):
                probe["status"] = error.code
            probe["error"] = dict(type=type(error).__name__, message=str(error))
            ready = False
        self.health_failures = 0 if ready else self.health_failures + 1
        probe.update(elapsed_s=time.monotonic() - started, ready=ready,
                     consecutive_failures=self.health_failures)
        with (folder / "disponibilite.jsonl").open("a") as stream:
            stream.write(json.dumps(probe) + "\n")
        if self.health_failures >= 3:
            save(folder / "arret-securite.json", dict(reasons=["service_unavailable"], last_probe=probe))
            raise RuntimeError("Service unavailable; escalation stopped")
        current = machine_snapshot()
        reasons = memory_blockers(current, self.previous_machine, self.policy)
        previous = self.previous_machine
        self.previous_machine = current
        for service in SERVICES:
            path = folder / f"serveur-{service}.jsonl"
            lines = path.read_text().splitlines() if path.exists() else []
            for line in reversed(lines):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("memory_oom_events", 0):
                    reasons.append(f"{service}_oom")
                if row.get("host_memory_available_pct", 100) < self.policy["memoire_disponible_min_pct"]:
                    reasons.append(f"{service}_memory_low")
                break
        if reasons:
            save(folder / "arret-securite.json", dict(reasons=reasons, snapshot=current, previous_snapshot=previous))
            raise RuntimeError("Memory pressure; escalation stopped: " + ", ".join(reasons))

    def samples(self, deployment, series):
        return {run["users"]: json.loads((self.output / run["path"] / "synthese.json").read_text())
                for run in self.manifest["runs"] if run["deployment"] == deployment and run["series"] == series}

    def calibrate(self, deployment, users):
        key = (deployment, users)
        if key in self.calibrated:
            return
        prefix = getattr(self, "calibration_prefix", "")
        folder = self.output / prefix / f"etalonnage/{deployment}/{users}"
        self.event("calibration_start", deployment=deployment, users=users)
        command = [sys.executable, str(ROOT / "scripts/etalonnage.py"), "static",
                   "--jmeter", self.args.jmeter, "--users", str(users), "--output", str(folder),
                   "--accounts", str(self.accounts), "--protocol", str(self.protocol_path),
                   "--private-log", str(self.runtime / "jmeter" / prefix / f"etalonnage/{deployment}/{users}/jmeter.log"),
                   "--capacity-guard"]
        console_path = (self.runtime / 'jmeter' / prefix / f'etalonnage/{deployment}/{users}/console.log'
                        if prefix else self.runtime / 'calibration.log')
        console_path.parent.mkdir(parents=True, exist_ok=True)
        with console_path.open("w") as console:
            process = subprocess.Popen(command, stdout=console, stderr=console, env=self.env, start_new_session=True)
            try:
                deadline = time.monotonic() + 120
                while process.poll() is None:
                    self.check_stop()
                    if time.monotonic() >= deadline:
                        raise RuntimeError(f"Calibration timed out; inspect {console_path}")
                    time.sleep(2)
                if process.returncode:
                    safety_path = folder / "arret-securite.json"
                    if safety_path.exists():
                        safety = json.loads(safety_path.read_text())
                        reasons = safety.get("reasons", [])
                        self.manifest["calibration_failure"] = dict(deployment=deployment, users=users,
                            reasons=reasons, path=str(safety_path.relative_to(self.output)))
                        self.event("calibration_failed", **self.manifest["calibration_failure"])
                        raise RuntimeError("Calibration stopped by resource guard: " + ", ".join(reasons))
                    raise RuntimeError(f"Calibration failed; inspect {console_path}")
            finally:
                self.terminate_runner(process)
        sample = json.loads((folder / "synthese.json").read_text())
        reasons = []
        if not sample['plateau_valid']:
            reasons.extend(sample['plateau_issues'])
        if sample['all_errors']:
            reasons.append(f"HTTP/assertion errors: {sample['all_errors']}")
        minimum = users * self.policy['marge_statique_min']
        if sample['successful_throughput_rps'] < minimum:
            reasons.append(f"Static throughput {sample['successful_throughput_rps']:.2f} < {minimum:.2f} req/s")
        if reasons:
            rejection = dict(deployment=deployment, users=users, reasons=reasons,
                             path=str(folder.relative_to(self.output)),
                             successful_throughput_rps=sample['successful_throughput_rps'],
                             minimum_throughput_rps=minimum)
            save(folder / 'rejet.json', rejection)
            self.manifest['calibration_failure'] = rejection
            self.event('calibration_rejected', **rejection)
            raise CalibrationRejected('Static calibration rejected: ' + '; '.join(reasons))
        if sample.get('max_elapsed_ms', 0) > 5000:
            warning = dict(deployment=deployment, users=users, path=str(folder.relative_to(self.output)),
                           max_elapsed_ms=sample['max_elapsed_ms'],
                           boundary_crossing_requests=sample.get('boundary_crossing_requests', 0))
            self.manifest.setdefault('calibration_warnings', []).append(warning)
            self.event('calibration_slow_requests', **warning)
        self.event("calibration_complete", deployment=deployment, users=users,
                   successful_throughput_rps=sample["successful_throughput_rps"])
        self.cooldown(deployment, f"etalonnage-{deployment}" + ("-" + prefix.replace("/", "-") if prefix else ""), users)
        self.calibrated.add(key)

    def measure(self, deployment, series, users):
        self.check_stop()
        self.calibrate(deployment, users)
        self.health_failures = 0
        # Cumulative host counters must describe this load, not VM preparation
        # or the preceding static calibration and cooldown.
        self.previous_machine = machine_snapshot()
        self.run_plateau(deployment, series, users)
        folder = self.output / f"serie-{series}/{deployment}/{users}"
        blockers = injector_blockers(folder, self.policy)
        with (folder / "ressources.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        sample = json.loads((folder / "synthese.json").read_text())
        stable = [row for row in rows if sample["window_start_ms"] / 1000 <= float(row["epoch_s"]) <= sample["window_end_ms"] / 1000]
        save(folder / "injecteur.json", dict(valid=not blockers, blockers=blockers,
             cpu_capacity_cores=self.policy.get("injecteur_cpu_capacite_coeurs", 1),
             cpu_window_s=self.policy.get("cpu_soutenu_s"), cpu_sustained_max=cpu_assessment(stable, self.policy)))
        if blockers:
            raise RuntimeError("Injector/host limiting; no deployment capacity conclusion: " + ", ".join(blockers))
        # Include a verified return to idle even after the final or rejected plateau.
        self.cooldown(deployment, series, users)

    def campaign(self, deployment, series):
        self.check_stop()
        self.reset(deployment)
        block = next((b for b in self.manifest["blocks"] if getattr(self, "resuming", False)
                      and b["deployment"] == deployment and b["series"] == series
                      and not b["completed"]), None)
        if block is None:
            block = dict(deployment=deployment, series=series, targets=[], completed=False)
            self.manifest["blocks"].append(block)
        self.event("capacity_block_start", deployment=deployment, series=series)

        def measure(users):
            if getattr(self, "resuming", False) and users in self.samples(deployment, series):
                return
            block["targets"].append(users)
            self.event("capacity_target", deployment=deployment, series=series, users=users)
            self.measure(deployment, series, users)

        if series == 1:
            shared = set(self.protocol["paliers_utilisateurs"])
            shared.update(run["users"] for run in self.manifest["runs"])
            for users in sorted(shared):
                measure(users)
                if not acceptable(self.samples(deployment, 1)[users], self.policy):
                    break
            while True:
                good, bad = bracket(self.samples(deployment, 1), self.policy)
                users = refinement(good, bad, self.policy["affinement_pas"])
                if users is None:
                    break
                measure(users)
        else:
            previous = self.samples(deployment, 1)
            # Docker may have introduced new refinement levels after the VM pass.
            # Add the comparable safe levels to VM series 1 before confirmation.
            _, first_bad = bracket(previous, self.policy)
            missing = sorted({run["users"] for run in self.manifest["runs"]}
                             - set(previous))
            missing = [n for n in missing if first_bad is None or n < first_bad]
            if missing:
                supplemental = dict(deployment=deployment, series=1, targets=missing, completed=False)
                self.manifest["blocks"].append(supplemental)
                for users in missing:
                    self.measure(deployment, 1, users)
                supplemental["completed"] = True
                self.reset(deployment)
                previous = self.samples(deployment, 1)
                bracket(previous, self.policy)
            # Insert the confirmation block after any supplemental series 1 block.
            self.manifest["blocks"].remove(block)
            self.manifest["blocks"].append(block)
            _, confirmed_bad = bracket(previous, self.policy)
            targets = sorted(n for n in previous if confirmed_bad is None or n <= confirmed_bad)
            for users in targets:
                measure(users)
                if not acceptable(self.samples(deployment, series)[users], self.policy) and users != targets[-1]:
                    raise RuntimeError("Earlier threshold breach in confirmation; stabilize host and repeat")
        block["completed"] = True
        self.event("capacity_block_complete", deployment=deployment, series=series)
