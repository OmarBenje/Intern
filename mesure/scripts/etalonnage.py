"""Prepare timed JMeter plans, record host/injector resources and analyse stable windows."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


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


def analyse(csv_path, users, ramp, warmup, plateau):
    with csv_path.open() as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise RuntimeError("No JMeter samples")
    first = min(int(row["timeStamp"]) for row in rows)
    start = first + (ramp + warmup) * 1000
    end = start + plateau * 1000
    window = [row for row in rows if int(row["timeStamp"]) >= start
              and int(row["timeStamp"]) + int(row["elapsed"]) <= end]
    if not window:
        raise RuntimeError("Empty stable window")
    effective = sorted({int(row["allThreads"]) for row in window})
    if effective != [users]:
        raise RuntimeError(f"Expected {users} active users throughout plateau, observed {effective}")
    threads = {row["threadName"] for row in window}
    if len(threads) != users:
        raise RuntimeError("Missing users in the stable window")
    for thread in threads:
        samples = [row for row in window if row["threadName"] == thread]
        if min(int(row["timeStamp"]) for row in samples) > start + 5000:
            raise RuntimeError("A user entered the plateau late")
        if max(int(row["timeStamp"]) + int(row["elapsed"]) for row in samples) < end - 5000:
            raise RuntimeError("A user left the plateau early")
    latency = [int(row["elapsed"]) for row in window]
    errors = [row for row in window if row["success"] != "true"]
    result = {
        "window_start_ms": start, "window_end_ms": end, "plateau_s": plateau,
        "users": users, "effective_users": effective,
        "requests": len(window), "errors": len(errors),
        "error_pct": len(errors) / len(window) * 100,
        "throughput_rps": len(window) / plateau,
        "successful_throughput_rps": (len(window) - len(errors)) / plateau,
        "p50_ms": percentile(latency, .5), "p90_ms": percentile(latency, .9),
        "p95_ms": percentile(latency, .95), "p99_ms": percentile(latency, .99),
        "total_samples": len(rows),
        "all_errors": sum(row["success"] != "true" for row in rows),
        "request_types": {},
    }
    for label in sorted({row["label"] for row in rows}):
        samples = [row for row in rows if row["label"] == label]
        result["request_types"][label] = {
            "samples": len(samples), "errors": sum(row["success"] != "true" for row in samples),
        }
    return result


def main():
    protocol = json.loads((ROOT / "protocole.json").read_text())
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
    args = parser.parse_args()
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
    command[command.index("-j") + 1] = str(Path("/tmp") / ("intern-jmeter-" + output.name + ".log"))
    metadata = {
        "mode": args.mode, "users": args.users, "ramp_s": args.ramp,
        "warmup_s": args.warmup, "plateau_s": args.plateau,
        "duration_s": args.ramp + args.warmup + args.plateau + 5,
        "port": args.port, "reflection_ms": 1000 if args.mode == "application" else 0,
        "source_plan_sha256": digest(ROOT / "plan.jmx"), "run_plan_sha256": digest(plan),
        "accounts_sha256": digest(args.accounts),
        "sql_schema_sha256": digest(ROOT.parent / "donnees/schema.sql"),
        "sql_data_sha256": digest(ROOT.parent / "donnees/data.sql"),
        "seed_script_sha256": digest(ROOT / "scripts/preparer_comptes.py"),
        "protocol_sha256": digest(ROOT / "protocole.json"),
        "host": {"system": platform.system(), "release": platform.release(), "logical_cpus": os.cpu_count()},
        "cpu_units": "100 percent injector CPU = one logical CPU; host busy percent = all CPUs",
        "started_epoch_s": time.time(),
    }
    save(output / "configuration.json", metadata)
    with (output / "console.txt").open("w") as console, (output / "ressources.csv").open("w") as resources:
        process = subprocess.Popen(command, cwd=ROOT, stdout=console, stderr=subprocess.STDOUT)
        writer = csv.writer(resources)
        writer.writerow(["epoch_s", "injector_cpu_pct", "injector_rss_bytes", "host_busy_pct", "load1"])
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
            writer.writerow([time.time(), cpu, sum(data[2] for data in current.values()), busy, os.getloadavg()[0]])
            resources.flush()
            before, host_before, last = current, host_now, now
    metadata["finished_epoch_s"] = time.time()
    metadata["exit_code"] = process.returncode
    save(output / "configuration.json", metadata)
    if process.returncode:
        raise RuntimeError("JMeter failed; inspect console.txt")
    result = analyse(csv_path, args.users, args.ramp, args.warmup, args.plateau)
    with (output / "ressources.csv").open() as stream:
        samples = [row for row in csv.DictReader(stream)
                   if result["window_start_ms"] / 1000 <= float(row["epoch_s"]) <= result["window_end_ms"] / 1000]
    for field in ("injector_cpu_pct", "injector_rss_bytes", "host_busy_pct"):
        values = [float(row[field]) for row in samples]
        result[field + "_mean"] = statistics.mean(values)
        result[field + "_max"] = max(values)
    save(output / "synthese.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
