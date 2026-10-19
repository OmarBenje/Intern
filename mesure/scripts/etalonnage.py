"""Prepare timed JMeter plans, record host/injector resources and analyse stable windows."""

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import signal
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    # Readers must see either the previous complete document or the new one.
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="." + path.name + "-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def private_jmeter_log(requested=None):
    if requested is None:
        descriptor, name = tempfile.mkstemp(prefix="intern-jmeter-", suffix=".log")
        os.close(descriptor)
        return Path(name)
    path = requested.resolve()
    if path.is_relative_to(ROOT.parent):
        raise RuntimeError("Keep private Java logs outside the application repository")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    return path


def make_plan(output, mode, users, ramp, duration):
    tree = ET.parse(ROOT / "plan.jmx")
    group = tree.find(".//ThreadGroup")
    for name, value in {
        "ThreadGroup.num_threads": users,
        "ThreadGroup.ramp_time": ramp,
        "ThreadGroup.duration": duration,
        "ThreadGroup.scheduler": "true",
        "LoopController.loops": -1,
    }.items():
        node = group.find(f'.//*[@name="{name}"]')
        node.text = str(value)
    # No graphical listener or response bodies during measurement.
    for parent in tree.iter("hashTree"):
        children = list(parent)
        for index, child in enumerate(children):
            if child.tag == "ResultCollector":
                parent.remove(child)
                parent.remove(children[index + 1])
    if mode == "static":
        children = tree.find(".//ThreadGroup/../hashTree")
        sampler = children.find("HTTPSamplerProxy")
        sampler.set("testname", "Statique Nginx")
        sampler.find('.//*[@name="HTTPSampler.path"]').text = "${__P(ressource,/static/admin/css/base.css)}"
        children.clear()
        children.append(sampler)
        checks = ET.SubElement(children, "hashTree")
        for name, field, pattern in [
            ("HTTP 200", "Assertion.response_code", "200"),
            ("Feuille CSS réelle", "Assertion.response_data", "body"),
        ]:
            assertion = ET.SubElement(
                checks, "ResponseAssertion", guiclass="AssertionGui",
                testclass="ResponseAssertion", testname=name, enabled="true",
            )
            patterns = ET.SubElement(assertion, "collectionProp", name="Asserion.test_strings")
            ET.SubElement(patterns, "stringProp", name="0").text = pattern
            ET.SubElement(assertion, "stringProp", name="Assertion.test_field").text = field
            ET.SubElement(assertion, "boolProp", name="Assertion.assume_success").text = "false"
            ET.SubElement(assertion, "intProp", name="Assertion.test_type").text = "16"
            ET.SubElement(checks, "hashTree")
    ET.indent(tree)
    tree.write(output, encoding="UTF-8", xml_declaration=True)


def process_snapshot(pid):
    """CPU ticks for the launched process and its current descendants."""
    processes = {}
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = path.read_text().rsplit(")", 1)[1].split()
            processes[int(path.parent.name)] = (
                int(fields[1]), int(fields[11]) + int(fields[12]),
                int(fields[21]) * os.sysconf("SC_PAGE_SIZE"),
            )
        except (OSError, ValueError, IndexError):
            continue
    selected = {pid}
    while True:
        descendants = {key for key, value in processes.items() if value[0] in selected}
        if descendants <= selected:
            break
        selected |= descendants
    return {key: processes[key] for key in selected if key in processes}


def host_snapshot():
    cpu = [int(value) for value in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
    # guest times are already included in user/nice.
    return sum(cpu[:8]), cpu[3] + cpu[4]


def percentile(values, fraction):
    values = sorted(values)
    index = (len(values) - 1) * fraction
    low = int(index)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (index - low)


def analyse(csv_path, users, ramp, warmup, plateau, capacity=False, boundary_activity=False):
    with csv_path.open() as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise RuntimeError("No JMeter samples")
    first = min(int(row["timeStamp"]) for row in rows)
    start = first + (ramp + warmup) * 1000
    end = start + plateau * 1000
    window = [row for row in rows if int(row["timeStamp"]) >= start
              and int(row["timeStamp"]) + int(row["elapsed"]) <= end]
    issues = []
    if not window:
        issues.append("Empty stable window")
    effective = sorted({int(row["allThreads"]) for row in window})
    if effective != [users]:
        issues.append(f"Expected {users} active users throughout plateau, observed {effective}")
    threads = {row["threadName"] for row in window}
    if len(threads) != users:
        issues.append("Missing users in the stable window")
    for thread in threads:
        # A request spanning a boundary is evidence of an active user even
        # though it is excluded from the fully contained latency window.
        samples = [row for row in (rows if boundary_activity else window)
                   if row["threadName"] == thread and int(row["timeStamp"]) <= end
                   and int(row["timeStamp"]) + int(row["elapsed"]) >= start]
        if min(int(row["timeStamp"]) for row in samples) > start + 5000:
            issues.append("A user entered the plateau late")
        if max(int(row["timeStamp"]) + int(row["elapsed"]) for row in samples) < end - 5000:
            issues.append("A user left the plateau early")
    if issues and not capacity:
        raise RuntimeError(issues[0])
    latency = [int(row["elapsed"]) for row in window]
    errors = [row for row in window if row["success"] != "true"]
    result = {
        "window_start_ms": start, "window_end_ms": end, "plateau_s": plateau,
        "users": users, "effective_users": effective,
        "requests": len(window), "errors": len(errors),
        "error_pct": len(errors) / len(window) * 100 if window else 100,
        "throughput_rps": len(window) / plateau,
        "successful_throughput_rps": (len(window) - len(errors)) / plateau,
        "p50_ms": percentile(latency, .5) if latency else None, "p90_ms": percentile(latency, .9) if latency else None,
        "p95_ms": percentile(latency, .95) if latency else None, "p99_ms": percentile(latency, .99) if latency else None,
        "total_samples": len(rows),
        "all_errors": sum(row["success"] != "true" for row in rows),
        "request_types": {},
    }
    for label in sorted({row["label"] for row in rows}):
        samples = [row for row in rows if row["label"] == label]
        result["request_types"][label] = {
            "samples": len(samples), "errors": sum(row["success"] != "true" for row in samples),
        }
    if capacity:
        result["plateau_valid"] = not issues
        result["plateau_issues"] = sorted(set(issues))
        if boundary_activity:
            crossing = [row for row in rows if int(row['timeStamp']) < end
                        and int(row['timeStamp']) + int(row['elapsed']) > start
                        and (int(row['timeStamp']) < start or
                             int(row['timeStamp']) + int(row['elapsed']) > end)]
            result['boundary_activity_version'] = 2
            result['boundary_crossing_requests'] = len(crossing)
            result['max_elapsed_ms'] = max(int(row['elapsed']) for row in rows)
        for label, record in result["request_types"].items():
            samples = [row for row in window if row["label"] == label]
            record["stable_samples"] = len(samples)
            record["stable_errors"] = sum(row["success"] != "true" for row in samples)
            record["stable_error_pct"] = record["stable_errors"] / len(samples) * 100 if samples else None
    return result


def machine_snapshot():
    memory = {key: int(value.split()[0]) * 1024 for key, value in
              (line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())}
    vm = dict(line.split() for line in Path("/proc/vmstat").read_text().splitlines())
    network = [line.split(":", 1)[1].split() for line in Path("/proc/net/dev").read_text().splitlines()[2:]]
    pressure = Path("/proc/pressure/memory")
    fields = dict(item.split("=") for item in pressure.read_text().splitlines()[0].split()[1:]) if pressure.exists() else {}
    return dict(host_memory_total_bytes=memory["MemTotal"],
                host_memory_available_bytes=memory["MemAvailable"],
                host_swap_used_bytes=memory["SwapTotal"] - memory["SwapFree"],
                host_swap_pages=int(vm["pswpin"]) + int(vm["pswpout"]),
                host_oom_kills=int(vm.get("oom_kill", 0)),
                host_memory_pressure_pct=float(fields.get("avg10", 0)),
                host_network_rx_bytes=sum(int(row[0]) for row in network),
                host_network_tx_bytes=sum(int(row[8]) for row in network))


def memory_blockers(snapshot, previous, policy):
    fields = ("host_memory_total_bytes", "host_memory_available_bytes", "host_swap_pages",
              "host_oom_kills", "host_memory_pressure_pct")
    values = [snapshot.get(field) for field in fields]
    values += [previous.get(field) for field in ("host_swap_pages", "host_oom_kills")]
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in values):
        return ["invalid_host_memory_readings"]
    if snapshot["host_memory_total_bytes"] == 0:
        return ["invalid_host_memory_readings"]
    if any(snapshot[field] < previous[field] for field in ("host_swap_pages", "host_oom_kills")):
        return ["host_counters_reset"]
    minimum = max(policy["memoire_disponible_min_octets"],
                  snapshot["host_memory_total_bytes"] * policy["memoire_disponible_min_pct"] / 100)
    reasons = []
    if snapshot["host_memory_available_bytes"] < minimum:
        reasons.append("host_memory_low")
    if snapshot["host_oom_kills"] > previous["host_oom_kills"]:
        reasons.append("host_oom")
    if snapshot["host_memory_pressure_pct"] > policy["pression_memoire_max_pct"]:
        reasons.append("host_memory_pressure")
    if snapshot["host_swap_pages"] > previous["host_swap_pages"]:
        # Swapping (including compressed RAM swap) alone does not establish
        # memory pressure. Archived protocols retain their strict activity rule.
        if not policy.get("swap_avec_pression_uniquement", False) or reasons:
            reasons.append("host_swapping")
    return reasons


PERFORMANCE_PROTOCOL = ROOT / "protocole-performance.json"


def saved_protocol(expected_digest, campaign_root=None):
    # Historical evidence retains its original fixed-rest protocol.
    paths = [PERFORMANCE_PROTOCOL, ROOT / "protocole.json"]
    if campaign_root is not None:
        paths.insert(0, campaign_root / "protocole.json")
    for path in paths:
        if not path.is_file():
            continue
        if digest(path) == expected_digest:
            return json.loads(path.read_text())
    raise RuntimeError("Unknown or changed campaign protocol")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["static", "application"])
    parser.add_argument("--jmeter", required=True)
    parser.add_argument("--users", type=int, required=True)
    parser.add_argument("--ramp", type=int)
    parser.add_argument("--warmup", type=int)
    parser.add_argument("--plateau", type=int)
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--accounts", type=Path, default=ROOT / "comptes.csv")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=PERFORMANCE_PROTOCOL)
    parser.add_argument("--capacity-guard", action="store_true")
    parser.add_argument("--private-log", type=Path)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    profile = protocol["statique"] if args.mode == "static" else protocol
    if args.ramp is None:
        args.ramp = profile["montee_s"]
    if args.warmup is None:
        args.warmup = profile.get("stabilisation_s", 0)
    if args.plateau is None:
        args.plateau = profile["plateau_s"]
    if args.users < 1 or args.ramp < 1 or args.warmup < 0 or args.plateau < 60:
        parser.error("Positive users/ramp, nonnegative warmup and plateau >= 60 seconds required")
    if args.mode == "application":
        with args.accounts.open() as stream:
            accounts = list(csv.DictReader(stream))
        if len(accounts) < args.users or len({row["username"] for row in accounts}) != len(accounts):
            parser.error("Not enough distinct accounts")
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        parser.error("Store results inside mesure/")
    output.mkdir(parents=True, exist_ok=False)
    plan = output / "plan.jmx"
    make_plan(plan, args.mode, args.users, args.ramp,
              args.ramp + args.warmup + args.plateau + 5)
    csv_path = output / "brut.csv"
    command = [args.jmeter, "-n", "-t", str(plan.relative_to(ROOT)), "-l", str(csv_path.relative_to(ROOT)),
               "-j", str((output / "jmeter.log").relative_to(ROOT)), f"-Jport={args.port}",
               f"-Jcomptes={args.accounts.resolve()}"]
    # Paths in the Java log can contain local context; keep that log outside deliverables.
    java_log = private_jmeter_log(args.private_log)
    command[command.index("-j") + 1] = str(java_log)
    metadata = {
        "mode": args.mode, "users": args.users, "ramp_s": args.ramp,
        "private_java_log": str(java_log),
        "warmup_s": args.warmup, "plateau_s": args.plateau,
        "duration_s": args.ramp + args.warmup + args.plateau + 5,
        "port": args.port, "reflection_ms": 1000 if args.mode == "application" else 0,
        "source_plan_sha256": digest(ROOT / "plan.jmx"), "run_plan_sha256": digest(plan),
        "accounts_sha256": digest(args.accounts),
        "sql_schema_sha256": digest(ROOT.parent / "donnees/schema.sql"),
        "sql_data_sha256": digest(ROOT.parent / "donnees/data.sql"),
        "seed_script_sha256": digest(ROOT / "scripts/preparer_comptes.py"),
        "protocol_sha256": digest(args.protocol),
        "host": {"system": platform.system(), "release": platform.release(), "logical_cpus": os.cpu_count()},
        "cpu_units": "100 percent injector CPU = one logical CPU; host busy percent = all CPUs",
        "started_epoch_s": time.time(),
        "plateau_activity_version": 2,
    }
    save(output / "configuration.json", metadata)
    with (output / "console.txt").open("w") as console, (output / "ressources.csv").open("w") as resources:
        machine_before = machine_snapshot()
        blockers = memory_blockers(machine_before, machine_before, protocol["capacite"]) if args.capacity_guard else []
        if blockers:
            save(output / "arret-securite.json", dict(reasons=blockers, snapshot=machine_before))
            raise RuntimeError("Host memory unsafe before load")
        process = subprocess.Popen(command, cwd=ROOT, stdout=console, stderr=subprocess.STDOUT,
                                   start_new_session=args.capacity_guard)

        def stop_injector():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()

        def interrupted(signum, frame):
            stop_injector()
            metadata.update(finished_epoch_s=time.time(), exit_code=process.returncode, interrupted=True)
            save(output / "configuration.json", metadata)
            raise SystemExit(128 + signum)

        if args.capacity_guard:
            signal.signal(signal.SIGTERM, interrupted)
            signal.signal(signal.SIGINT, interrupted)
        try:
            writer = csv.writer(resources)
            extra_fields = list(machine_before)
            writer.writerow(["epoch_s", "injector_cpu_pct", "injector_rss_bytes", "host_busy_pct", "load1", *extra_fields])
            before = process_snapshot(process.pid)
            host_before = host_snapshot()
            last = time.monotonic()
            while process.poll() is None:
                time.sleep(2)
                now = time.monotonic()
                current = process_snapshot(process.pid)
                host_now = host_snapshot()
                ticks = sum(max(0, data[1] - before[pid][1]) for pid, data in current.items() if pid in before)
                cpu = ticks / os.sysconf("SC_CLK_TCK") / (now - last) * 100
                total = host_now[0] - host_before[0]
                busy = (1 - (host_now[1] - host_before[1]) / total) * 100 if total else 0
                machine = machine_snapshot()
                writer.writerow([time.time(), cpu, sum(data[2] for data in current.values()), busy, os.getloadavg()[0],
                                 *(machine[field] for field in extra_fields)])
                resources.flush()
                if args.capacity_guard:
                    blockers = memory_blockers(machine, machine_before, protocol["capacite"])
                    if blockers:
                        save(output / "arret-securite.json", dict(reasons=blockers, snapshot=machine))
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=20)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()
                        raise RuntimeError("Unsafe host resources: " + ", ".join(blockers))
                before, host_before, last, machine_before = current, host_now, now, machine
        finally:
            if args.capacity_guard:
                stop_injector()
    metadata["finished_epoch_s"] = time.time()
    metadata["exit_code"] = process.returncode
    save(output / "configuration.json", metadata)
    if process.returncode:
        raise RuntimeError("JMeter failed; inspect console.txt")
    result = analyse(csv_path, args.users, args.ramp, args.warmup, args.plateau,
                     capacity=args.capacity_guard, boundary_activity=True)
    with (output / "ressources.csv").open() as stream:
        samples = [row for row in csv.DictReader(stream)
                   if result["window_start_ms"] / 1000 <= float(row["epoch_s"]) <= result["window_end_ms"] / 1000]
    for field in ("injector_cpu_pct", "injector_rss_bytes", "host_busy_pct"):
        values = [float(row[field]) for row in samples]
        if not values:
            raise RuntimeError("Missing stable injector samples")
        result[field + "_mean"] = statistics.mean(values)
        result[field + "_max"] = max(values)
    save(output / "synthese.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
