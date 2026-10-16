"""Recalculate campaign evidence and plot both repetitions without pooling p95."""

import csv
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "intern-matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from etalonnage import ROOT, digest, save
from verifier17 import main as verify


def main():
    if len(sys.argv) != 1:
        raise SystemExit("This analysis uses the archived step 17 campaign")
    verify(argv=[], write_outputs=False)
    source = ROOT / "resultats/etape17"
    output = ROOT / "resultats/etape18"
    charts = ROOT / "docs/courbes"
    output.mkdir(exist_ok=True)
    charts.mkdir(parents=True, exist_ok=True)
    protocol = json.loads((ROOT / "protocole.json").read_text())
    users = protocol["paliers_utilisateurs"]
    runs = {(s, dep, n): json.loads((source / f"serie-{s}/{dep}/{n}/synthese.json").read_text())
            for s in (1, 2) for dep in ("vm", "docker") for n in users}
    rows = []
    for n in users:
        vm, docker = ([runs[s, dep, n] for s in (1, 2)] for dep in ("vm", "docker"))
        vr, dr = (statistics.mean(r["successful_throughput_rps"] for r in group) for group in (vm, docker))
        rows.append(dict(users=n, vm_mean_rps=vr, docker_mean_rps=dr,
                         docker_throughput_gain_pct=(dr / vr - 1) * 100,
                         vm_p95_s1_ms=vm[0]["p95_ms"], vm_p95_s2_ms=vm[1]["p95_ms"],
                         docker_p95_s1_ms=docker[0]["p95_ms"], docker_p95_s2_ms=docker[1]["p95_ms"],
                         docker_p95_reduction_s1_pct=(1 - docker[0]["p95_ms"] / vm[0]["p95_ms"]) * 100,
                         docker_p95_reduction_s2_pct=(1 - docker[1]["p95_ms"] / vm[1]["p95_ms"]) * 100))
    with (output / "comparaison.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    styles = {"vm": ("#2563a6", "o", "VM"), "docker": ("#ce6a13", "s", "Docker")}
    metrics = (("successful_throughput_rps", "Débit réussi (consultations/s)", "debit"),
               ("p95_ms", "Latence au 95e centile (ms)", "latence-p95"),
               ("error_pct", "Erreurs dans la fenêtre stable (%)", "erreurs"))
    fig, axes = plt.subplots(3, 1, figsize=(8.1, 8.6), layout="constrained")

    def plot(ax, metric, label):
        for dep, (color, marker, name) in styles.items():
            for series in (1, 2):
                ax.plot(users, [runs[series, dep, n][metric] for n in users], color=color,
                        marker=marker, markerfacecolor=color if series == 1 else "white",
                        linestyle="-" if series == 1 else "--", label=f"{name}, série {series}")
        if metric == "successful_throughput_rps":
            ax.plot(users, users, color="#64748b", linestyle=":", label="Plafond du profil : U / 1 s")
        if metric == "error_pct":
            ax.set_ylim(-0.1, 1)
        else:
            ax.set_ylim(bottom=0)
        ax.set(xlabel="Utilisateurs simultanés", ylabel=label, xticks=users)
        ax.grid(alpha=.2)
        ax.annotate("Saturation non observée (1 à 20 utilisateurs)", xy=(.02, .96),
                    xycoords="axes fraction", va="top", fontsize=8,
                    bbox=dict(facecolor="white", alpha=.85, edgecolor="none"))
        ax.legend(fontsize=7, loc="lower right" if metric != "error_pct" else "upper right")

    for ax, (metric, label, name) in zip(axes, metrics):
        plot(ax, metric, label)
        standalone, standalone_ax = plt.subplots(figsize=(8, 4.4), layout="constrained")
        plot(standalone_ax, metric, label)
        for extension in ("png", "svg"):
            path = charts / f"{name}.{extension}"
            standalone.savefig(path, dpi=180)
            if extension == "svg":
                path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
        plt.close(standalone)
    fig.savefig(charts / "ensemble.png", dpi=180)
    fig.savefig(charts / "ensemble.pdf")
    plt.close(fig)
    startup = {}
    for dep, path in (("vm", ROOT.parent / "deploiement/docs/mesures-etape10.json"),
                      ("docker", ROOT.parent / "docker/docs/mesures-etape14.json")):
        values = json.loads(path.read_text())
        startup[dep] = {"startup_s": values["medians"]["startup_s"],
                        "idle_rss_mib": values["medians"]["rss_bytes"] / 2**20,
                        "source_sha256": digest(path)}
    save(output / "analyse.json", dict(comparison=rows, startup_and_idle=startup,
                                       saturation_observed=False, tested_users=users,
                                       saturation_assessment="Manual interpretation for the archived inputs; see docs/rapport-charge.md",
                                       p95_aggregation="Separate repetitions; no average or pooled p95",
                                       input_hashes={name: digest(source / name) for name in
                                                     ("manifest.json", "journal.jsonl", "releve-paliers.csv", "releve-serveurs.csv")},
                                       incident="Docker stopped after first VM campaign; campaign resumed"))
    print(json.dumps({"at_twenty_users": rows[-1], "startup_and_idle": startup}, indent=2))


if __name__ == "__main__":
    main()
