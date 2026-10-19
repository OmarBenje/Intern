"""Verify capacity search inputs and export cautious conclusions, charts and a PDF."""

import argparse
import csv
import json
import os
from pathlib import Path
import tempfile

from etalonnage import ROOT, analyse, digest, save
from capacite import acceptable, bracket, variation, injector_blockers


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def load_runs(root, manifest):
    return {(r["series"], r["deployment"], r["users"]):
            json.loads((root / r["path"] / "synthese.json").read_text()) for r in manifest["runs"]}


def validate_design(root, manifest, protocol):
    policy = protocol["capacite"]
    blocks = manifest["blocks"]
    keys = [(b["series"], b["deployment"]) for b in blocks]
    require(keys in ([(1, "vm"), (1, "docker"), (2, "docker"), (2, "vm")],
                     [(1, "vm"), (1, "docker"), (2, "docker"), (1, "vm"), (2, "vm")]),
            "Capacity deployment order differs")
    require(all(b["completed"] and b["targets"] for b in blocks), "Incomplete capacity blocks")
    runs = load_runs(root, manifest)
    require(len(runs) == len(manifest["runs"]), "Duplicate capacity runs")
    with (root / "comptes.csv").open() as stream:
        accounts = list(csv.DictReader(stream))
    require(len(accounts) >= max(protocol["paliers_utilisateurs"])
            and len({r["username"] for r in accounts}) == len(accounts)
            and len({r["application_id"] for r in accounts}) == len(accounts), "Insufficient distinct candidate fixtures")
    all_levels = {n for _, _, n in runs}
    for dep in ("vm", "docker"):
        first = {n: sample for (s, d, n), sample in runs.items() if s == 1 and d == dep}
        second = {n: sample for (s, d, n), sample in runs.items() if s == 2 and d == dep}
        good, bad = bracket(first, policy)
        require(first and all(0 < n <= len(accounts) for n in first), "Invalid capacity loads")
        require(set(second) == {n for n in first if bad is None or n <= bad}, "Capacity bounds not confirmed")
        require(all(n in first for n in all_levels if bad is None or n < bad),
                "Comparable safe levels missing between deployments")
        # Coarse exploration reaches its bound or records a rejected coarse plateau.
        coarse = protocol["paliers_utilisateurs"]
        coarse_bad = next((n for n in coarse if n in first and not acceptable(first[n], policy)), None)
        require(all(n in first for n in coarse if coarse_bad is None or n <= coarse_bad), "Exploration stopped without a breach")
        require(bad is None or bad - good <= max(1, policy["affinement_pas"]), "Capacity bracket not refined")


def verify_calibration(root, manifest, protocol):
    from reprendre17 import checked_protocol_hashes
    allowed_protocols = checked_protocol_hashes(root, manifest)
    hashes = {}
    checks = {(r["deployment"], r["users"]) for r in manifest["runs"]}
    for dep, users in sorted(checks):
        folder = root / f"etalonnage/{dep}/{users}"
        config = json.loads((folder / "configuration.json").read_text())
        profile = protocol["statique"]
        require(config["mode"] == "static" and config["users"] == users and config["exit_code"] == 0
                and config["protocol_sha256"] in allowed_protocols
                and config["source_plan_sha256"] == manifest["source_plan_sha256"]
                and config["accounts_sha256"] == manifest["accounts_sha256"]
                and config["run_plan_sha256"] == digest(folder / "plan.jmx")
                and config["ramp_s"] == profile["montee_s"]
                and config["warmup_s"] == profile["stabilisation_s"]
                and config["plateau_s"] == profile["plateau_s"], "Static calibration configuration differs")
        sample = analyse(folder / "brut.csv", users, config["ramp_s"], config["warmup_s"], config["plateau_s"],
                         capacity=True, boundary_activity=config.get('plateau_activity_version', 1) == 2)
        saved = json.loads((folder / "synthese.json").read_text())
        require(all(saved[k] == v for k, v in sample.items()), "Static raw evidence differs")
        require(sample["plateau_valid"] and sample["all_errors"] == 0
                and sample["successful_throughput_rps"] >= users * protocol["capacite"]["marge_statique_min"],
                "Insufficient calibrated injector/proxy margin")
        require(not (folder / "arret-securite.json").exists(), "Calibration safety interruption")
        require(not injector_blockers(folder, protocol["capacite"], check_cpu=False), "Calibration resource readings invalid")
        for name in ("brut.csv", "configuration.json", "synthese.json", "plan.jmx", "ressources.csv", "console.txt"):
            hashes[str((folder / name).relative_to(root))] = digest(folder / name)
    return hashes


def conclusions(root, manifest, protocol):
    runs = load_runs(root, manifest)
    policy = protocol["capacite"]
    result = {}
    for dep in ("vm", "docker"):
        levels = sorted(n for s, d, n in runs if s == 2 and d == dep)
        divergence, good, bad, saturation = [], 0, None, []
        for n in levels:
            pair = [runs[s, dep, n] for s in (1, 2)]
            for field in ("successful_throughput_rps", "p95_ms"):
                a, b = (p[field] for p in pair)
                if a is None or b is None:
                    # Missing plateaus are rejected measurements, never a valid capacity.
                    if a != b:
                        divergence.append(dict(users=n, metric=field, reason="missing_plateau"))
                else:
                    delta = variation(a, b)
                    if delta > policy["ecart_repetitions_max_pct"]:
                        divergence.append(dict(users=n, metric=field, variation_pct=delta))
            if all(acceptable(p, policy) for p in pair) and bad is None:
                good = n
            elif bad is None:
                bad = n
        for low, high in zip(levels, levels[1:]):
            evidence = []
            for series in (1, 2):
                a, b = (runs[series, dep, n] for n in (low, high))
                if not a["plateau_valid"] or not b["plateau_valid"] or a["successful_throughput_rps"] <= 0 or not a["p95_ms"]:
                    break
                gain = (b["successful_throughput_rps"] / a["successful_throughput_rps"] - 1) * 100
                latency = (b["p95_ms"] / a["p95_ms"] - 1) * 100
                if abs(gain) > policy["debit_plafond_gain_max_pct"] or latency < policy["latence_hausse_min_pct"]:
                    break
                evidence.append(dict(series=series, throughput_gain_pct=gain, p95_rise_pct=latency))
            if len(evidence) == 2:
                servers = {str(s): {str(n): json.loads((root / f"serie-{s}/{dep}/{n}/serveurs.json").read_text())
                                   for n in (low, high)} for s in (1, 2)}
                saturation.append(dict(lower_users=low, upper_users=high, client=evidence, servers=servers,
                                       cause="À déterminer en croisant CPU, mémoire, E/S et connexions PostgreSQL ; CPU seul insuffisant."))
        valid = not divergence and good > 0
        if divergence:
            text = "Capacité non retenue : répétitions divergentes de plus de 10 % ; stabiliser l’hôte et recommencer."
        elif not good:
            text = "Aucun palier ne respecte les seuils dans les deux séries."
        elif bad is None:
            text = f"Au moins {good} utilisateurs testés, limite non atteinte, avec ce scénario et cette configuration."
        else:
            text = f"{good} utilisateurs simultanés validés, premier dépassement à {bad}, avec ce scénario et cette configuration."
        result[dep] = dict(valid=valid, validated_users=good if valid else None, first_rejected_users=bad,
                           tested_users=levels, divergence=divergence, saturation=saturation, conclusion=text,
                           next_action="Étendre les paliers après vérification des ressources et nouvel étalonnage."
                           if bad is None else "Interpréter les relevés serveur pour établir la cause du goulot.")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.source.resolve()
    require(root.is_relative_to(ROOT / "resultats"), "Capacity evidence must stay under mesure/resultats/")
    manifest = json.loads((root / "manifest.json").read_text())
    require(manifest.get("kind") == "capacity", "This is not a capacity search")
    from verifier17 import main as verify
    verification = verify(["--output", str(root)], write_outputs=True)
    protocol = json.loads((root / "protocole.json").read_text())
    result = conclusions(root, manifest, protocol)
    output = root / "analyse"
    output.mkdir(exist_ok=True)
    save(output / "capacite.json", dict(deployments=result, protocol=protocol,
                                        verification_sha256=digest(root / "verification.json")))
    runs = load_runs(root, manifest)
    records = []
    for (series, dep, users), sample in runs.items():
        for label, row in sample["request_types"].items():
            records.append(dict(series=series, deployment=dep, users=users, request=label, **row))
    with (output / "erreurs-par-requete.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "intern-matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    report = ["Capacité maximale : VM et Docker", ""]
    for dep, value in result.items():
        report += [dep.upper(), value["conclusion"], value["next_action"],
                   "Saturation : " + ("signal observé, cause à interpréter" if value["saturation"] else "non démontrée"), ""]
    report += [f"Seuils choisis : p95 ≤ {protocol['capacite']['p95_max_ms']} ms, erreurs ≤ {protocol['capacite']['erreurs_max_pct']} % ; réflexion 1 s.",
               "Montée 30 s, stabilisation 15 s, plateau 120 s.",
               f"{verification['plateaus']} paliers vérifiés. Les p95 des séries restent séparés.",
               "Les charges au-delà d’un palier refusé ne sont pas rejouées.",
               "Ce résultat dépend du parcours, des données et des ressources allouées.",
               "Détails et corrélations serveur : capacite.json ; erreurs-par-requete.csv."]
    (output / "rapport.md").write_text("\n\n".join(report) + "\n")
    metrics = (("successful_throughput_rps", "Débit réussi (requêtes/s)", "debit"),
               ("p95_ms", "Latence p95 (ms)", "p95"), ("error_pct", "Erreurs stables (%)", "erreurs"))
    with PdfPages(output / "rapport.pdf") as pdf:
        fig = plt.figure(figsize=(8.3, 11.7))
        import textwrap
        fig.text(.08, .94, "\n\n".join(textwrap.fill(line, 90) for line in report), va="top", fontsize=10)
        pdf.savefig(fig)
        plt.close(fig)
        for metric, label, name in metrics:
            fig, ax = plt.subplots(figsize=(8, 4.5), layout="constrained")
            for dep, color in (("vm", "#2563a6"), ("docker", "#ce6a13")):
                for series in (1, 2):
                    points = sorted((n, r[metric]) for (s, d, n), r in runs.items() if s == series and d == dep and r[metric] is not None)
                    ax.plot([p[0] for p in points], [p[1] for p in points], marker="o", color=color,
                            linestyle="-" if series == 1 else "--", label=f"{dep}, série {series}")
            if metric in ("p95_ms", "error_pct"):
                ax.axhline(protocol["capacite"]["p95_max_ms" if metric == "p95_ms" else "erreurs_max_pct"], color="red", linestyle=":", label="Seuil de service")
            ax.set(xlabel="Utilisateurs simultanés", ylabel=label, ylim=(0, None))
            ax.grid(alpha=.2)
            ax.legend()
            fig.savefig(output / f"{name}.png", dpi=180)
            fig.savefig(output / f"{name}.svg")
            pdf.savefig(fig)
            plt.close(fig)
    (output / "SHA256SUMS").write_text("".join(f"{digest(path)}  {path.name}\n" for path in sorted(output.iterdir()) if path.is_file() and path.name != "SHA256SUMS"))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
