"""Verify saved campaigns and export per-plateau client and server readings.

Reads raw evidence; never starts a deployment or changes a database.
"""

import argparse
import csv
import json
import math
from pathlib import Path
import statistics

from etalonnage import ROOT, analyse, digest, save, saved_protocol
from repos import idle_window


SERVICES = ("proxy", "metier", "donnees")
FIELDS = ("cpu_pct", "rss_bytes", "memory_cgroup_bytes", "read_bytes_per_s",
          "write_bytes_per_s", "db_connections", "db_active_connections")
REQUIRED = ("brut.csv", "configuration.json", "plan.jmx", "ressources.csv",
            "synthese.json", "serveurs.json", *(f"serveur-{s}.jsonl" for s in SERVICES))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def export(path, rows):
    with path.open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None, write_outputs=True):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "resultats/etape17")
    parser.add_argument("--runtime", type=Path)
    args = parser.parse_args(argv)
    root = args.output.resolve()
    require(root.is_relative_to(ROOT), "Results must stay inside mesure/")
    manifest = json.loads((root / "manifest.json").read_text())
    protocol = saved_protocol(manifest["protocol_sha256"], root)
    capacity = manifest.get("kind") == "capacity"
    require(manifest["status"] == "complete", "Campaigns are incomplete")
    require(manifest["source_plan_sha256"] == digest(ROOT / "plan.jmx"), "Source plan changed")
    require(manifest["accounts_sha256"] == digest(root / "comptes.csv" if capacity else ROOT / "comptes.csv"), "Accounts changed")
    expected = [(series, deployment, users) for series, deployments in
                ((1, ("vm", "docker")), (2, ("docker", "vm")))
                for deployment in deployments for users in protocol["paliers_utilisateurs"]]
    if capacity:
        from analyser_capacite import validate_design
        validate_design(root, manifest, protocol)
        expected = [(block["series"], block["deployment"], n)
                    for block in manifest["blocks"] for n in block["targets"]]
    observed = [(r["series"], r["deployment"], r["users"]) for r in manifest["runs"]]
    require(observed == expected, "Missing, duplicate or out-of-order plateaus")
    events = [json.loads(line) for line in (root / "journal.jsonl").read_text().splitlines()]
    require(events[-1]["action"] == "reference_restored", "Restoration event missing")
    starts = [(e["series"], e["deployment"], e["users"]) for e in events if e["action"] == "palier_start"]
    require(starts == expected, "Unexpected raw execution order")
    resets = [e for e in events if e["action"] == "database_restored"]
    expected_resets = [block["deployment"] for block in manifest["blocks"]] if capacity else ["vm", "docker", "docker", "vm"]
    require([e["deployment"] for e in resets] == expected_resets, "Unexpected resets")
    require(all(e["snapshot_sha256"] == manifest["snapshot_sha256"] for e in resets), "SQL snapshots differ")
    for i, event in enumerate(events):
        if event["action"] == "cooldown":
            next_start = next(e for e in events[i + 1:] if e["action"] == "palier_start")
            require(next_start["epoch_s"] >= event["until_epoch_s"], "Rest shortened")
            require(event["until_epoch_s"] - event["epoch_s"] >= 899.9, "Rest duration changed")
    if args.runtime:
        require(digest(args.runtime / "base.sql") == manifest["snapshot_sha256"], "Private SQL export changed")
        require(digest(args.runtime / "sources.tar") == manifest["sources_sha256"], "Private sources changed")

    hashes = {name: digest(root / name) for name in ("manifest.json", "journal.jsonl")}
    if "repos_dynamique" in protocol:
        checks = [e for e in events if e["action"] == "login_rate_limit_checked"]
        require([e["deployment"] for e in checks] == expected_resets
                and all(e["enabled"] is False for e in checks), "Measurement login settings differ")
        expected_rests = [(s, d, u) for s, d, u in expected
                          if u != protocol["paliers_utilisateurs"][-1]]
        if capacity:
            expected_rests = [(e["series"], e["deployment"], e["users"]) if e["action"] == "palier_complete"
                              else (f"etalonnage-{e['deployment']}", e["deployment"], e["users"])
                              for e in events if e["action"] in ("palier_complete", "calibration_complete")]
        for action in ("cooldown_start", "cooldown_complete"):
            require([(e["series"], e["deployment"], e["users"]) for e in events
                     if e["action"] == action] == expected_rests, "Missing or out-of-order rest evidence")
        for i, event in enumerate(events):
            if event["action"] != "cooldown_start":
                continue
            finish = events[i + 1]
            require(finish["action"] == "cooldown_complete" and finish["path"] == event["path"],
                    "Incomplete adaptive rest")
            policy = protocol["repos_dynamique"]
            elapsed = finish["epoch_s"] - event["epoch_s"]
            require(policy["minimum_s"] <= elapsed <= policy["maximum_s"] + 10,
                    "Adaptive rest outside frozen bounds")
            require(finish.get("ready") is True, "Readiness check missing")
            idle_epoch = finish["idle_epoch_s"]
            require(event["epoch_s"] <= idle_epoch <= finish["epoch_s"]
                    and finish["epoch_s"] - idle_epoch <= policy["fraicheur_s"],
                    "Idle decision missing or stale")
            if not capacity:
                next_start = events[i + 2]
                require(next_start["action"] == "palier_start" and next_start["epoch_s"] >= finish["epoch_s"],
                        "Next plateau began before rest finished")
            folder = (root / finish["path"]).resolve()
            require(folder.is_relative_to(root), "Rest evidence outside results")
            samples = {}
            for service in SERVICES:
                path = folder / f"serveur-{service}.jsonl"
                hashes[str(path.relative_to(root))] = digest(path)
                # Readings collected after the decision do not justify that decision.
                samples[service] = [row for line in path.read_text().splitlines()
                                    if (row := json.loads(line))["epoch_s"] <= idle_epoch]
            require(idle_window(samples, idle_epoch, policy), "Services were not idle at restart")
    if capacity:
        from analyser_capacite import verify_calibration
        hashes.update(verify_calibration(root, manifest, protocol))
        for name in ("comptes.csv", "protocole.json"):
            hashes[name] = digest(root / name)
    clients, servers, common, plans = [], [], {}, {}
    for run in manifest["runs"]:
        folder = root / run["path"]
        for name in REQUIRED:
            path = folder / name
            require(path.is_file() and path.stat().st_size > 0, f"Missing evidence: {run['path']}/{name}")
            hashes[f"{run['path']}/{name}"] = digest(path)
        config = json.loads((folder / "configuration.json").read_text())
        frozen = dict(mode="application", ramp_s=protocol["montee_s"],
                      warmup_s=protocol["stabilisation_s"], plateau_s=protocol["plateau_s"],
                      reflection_ms=protocol["reflexion_ms"],
                      protocol_sha256=manifest["protocol_sha256"],
                      source_plan_sha256=manifest["source_plan_sha256"],
                      accounts_sha256=manifest["accounts_sha256"])
        require(all(config[key] == value for key, value in frozen.items()), "Frozen parameters differ")
        for key in ("mode", "ramp_s", "warmup_s", "plateau_s", "duration_s", "port", "reflection_ms",
                    "source_plan_sha256", "accounts_sha256", "sql_schema_sha256", "sql_data_sha256",
                    "seed_script_sha256", "protocol_sha256", "host"):
            if key not in common:
                common[key] = config[key]
            require(config[key] == common[key], f"Configuration differs: {run['path']} {key}")
        require(config["exit_code"] == 0 and config["users"] == run["users"], "Runner failed or users differ")
        require(config["run_plan_sha256"] == digest(folder / "plan.jmx"), "Generated plan changed")
        users = run["users"]
        plans.setdefault(users, config["run_plan_sha256"])
        require(plans[users] == config["run_plan_sha256"], "Plans differ for the same plateau")
        recalculated = analyse(folder / "brut.csv", users, config["ramp_s"], config["warmup_s"], config["plateau_s"], capacity=capacity)
        saved = json.loads((folder / "synthese.json").read_text())
        require(all(saved[k] == v for k, v in recalculated.items()), f"Client summary differs: {run['path']}")
        require(run["errors"] == saved["all_errors"], "Manifest error count differs")
        if capacity:
            from capacite import injector_blockers
            require(not injector_blockers(folder, protocol["capacite"]), "Injector/host limiting")
            require(not (folder / "arret-securite.json").exists(), "Safety interruption present")
            hashes[f"{run['path']}/injecteur.json"] = digest(folder / "injecteur.json")
        clients.append(dict(series=run["series"], deployment=run["deployment"], users=users,
                            **{k: saved[k] for k in ("total_samples", "requests", "all_errors",
                               "successful_throughput_rps", "p50_ms", "p95_ms", "p99_ms")}))
        summary = json.loads((folder / "serveurs.json").read_text())
        for service in SERVICES:
            raw = [json.loads(line) for line in (folder / f"serveur-{service}.jsonl").read_text().splitlines()]
            stable = [r for r in raw if r["epoch_s"] - r["interval_s"] >= saved["window_start_ms"] / 1000
                      and r["epoch_s"] <= saved["window_end_ms"] / 1000]
            require(len(stable) >= 15 and len(stable) == summary[service]["samples"], "Insufficient server samples")
            methods = sorted({r["cpu_io_method"] for r in stable})
            require(methods == summary[service]["cpu_io_methods"], "Collector methods differ")
            record = dict(series=run["series"], deployment=run["deployment"], users=users,
                          service=service, samples=len(stable), cpu_io_methods=";".join(methods))
            for field in FIELDS:
                values = [r[field] for r in stable if r.get(field) is not None]
                for suffix, fn in (("mean", statistics.mean), ("max", max)):
                    key = field + "_" + suffix
                    value = fn(values) if values else None
                    require((value is None and key not in summary[service]) or
                            (value is not None and math.isclose(value, summary[service][key], rel_tol=1e-9)),
                            f"Server summary differs: {run['path']} {service} {key}")
                    record[key] = value
            servers.append(record)
    if write_outputs:
        export(root / "releve-paliers.csv", clients)
        export(root / "releve-serveurs.csv", servers)
    for name in ("releve-paliers.csv", "releve-serveurs.csv", "restauration.json"):
        if (root / name).exists():
            hashes[name] = digest(root / name)
    verification = dict(status="verified", plateaus=len(clients), server_readings=len(servers),
                        total_jmeter_samples=sum(r["total_samples"] for r in clients),
                        stable_requests=sum(r["requests"] for r in clients),
                        all_errors=sum(r["all_errors"] for r in clients),
                        minimum_stable_server_samples=min(r["samples"] for r in servers),
                        restoration_event_present=True, private_snapshot_checked=bool(args.runtime),
                        incidents=[e for e in events if e["action"] == "campaigns_failed"],
                        raw_files_sha256=hashes)
    if write_outputs:
        save(root / "verification.json", verification)
        (root / "SHA256SUMS").write_text("".join(f"{value}  {name}\n" for name, value in sorted(hashes.items())))
    print(json.dumps({k: v for k, v in verification.items() if k != "raw_files_sha256"}, indent=2))
    return verification


if __name__ == "__main__":
    main()
