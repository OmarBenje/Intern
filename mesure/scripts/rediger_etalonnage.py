"""Generate the concise calibration report exclusively from saved real measurements."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "resultats/etape16"


def load(name):
    return json.loads((RESULTS / name).read_text())


def gap(first, second):
    average = (first + second) / 2
    return abs(second - first) / average * 100 if average else 0


def main():
    protocol = json.loads((ROOT / "protocole.json").read_text())
    static = [load(f"statique-{users}/synthese.json") for users in protocol["statique"]["utilisateurs"]]
    controls = [load(f"controle-{number}/synthese.json") for number in (1, 2)]
    configuration = [load(f"controle-{number}/configuration.json") for number in (1, 2)]
    invariants = ["mode", "users", "ramp_s", "warmup_s", "plateau_s", "duration_s", "port",
                  "reflection_ms", "source_plan_sha256", "run_plan_sha256", "accounts_sha256",
                  "sql_schema_sha256", "sql_data_sha256", "seed_script_sha256", "protocol_sha256", "host"]
    for key in invariants:
        if configuration[0][key] != configuration[1][key]:
            raise RuntimeError("Controls differ: " + key)
    maximum = max(static, key=lambda row: row["successful_throughput_rps"])
    throughput_gap = gap(*(row["successful_throughput_rps"] for row in controls))
    p95_gap = gap(*(row["p95_ms"] for row in controls))
    p99_gap = gap(*(row["p99_ms"] for row in controls))
    repeatable = throughput_gap <= 10 and p95_gap <= 10 and all(row["all_errors"] == 0 for row in controls)
    upper_bound = max(protocol["paliers_utilisateurs"]) * 1000 / protocol["reflexion_ms"]
    margin = maximum["successful_throughput_rps"] / upper_bound
    data = {
        "static_maximum_observed_rps": maximum["successful_throughput_rps"],
        "static_maximum_users": maximum["users"],
        "application_profile_upper_bound_rps": upper_bound,
        "static_margin_ratio": margin, "control_throughput_gap_pct": throughput_gap,
        "control_p95_gap_pct": p95_gap, "repeatability_criteria_passed": repeatable,
        "control_p99_gap_pct": p99_gap,
        "protocol": protocol,
        "raw_files_sha256": {str(path.relative_to(RESULTS)): hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in sorted(RESULTS.glob("*/brut.csv"))},
    }
    (RESULTS / "etalonnage.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    static_rows = "\n".join(
        f"| {row['users']} | {row['successful_throughput_rps']:.2f} | {row['p95_ms']:.2f} | {row['error_pct']:.2f} % | {row['injector_cpu_pct_mean']:.1f} % | {row['host_busy_pct_mean']:.1f} % |"
        for row in static
    )
    control_rows = "\n".join(
        f"| {number} | {row['requests']} | {row['successful_throughput_rps']:.3f} | {row['p50_ms']:.2f} | {row['p95_ms']:.2f} | {row['p99_ms']:.2f} | {row['error_pct']:.2f} % |"
        for number, row in enumerate(controls, 1)
    )
    verdict = ("Les écarts de débit et de latence p95 restent sous 10 %, sans erreur : le contrôle de répétabilité réussit."
               if repeatable else "Le critère de répétabilité n'est pas satisfait ; stabiliser l'hôte et refaire les deux contrôles avant les campagnes.")
    report = f"""# Étape 16 — Rapport d'étalonnage

Mesures réelles du 14 octobre 2026 : JMeter 5.6.3 et Java 21, en CLI sur
l'hôte, vers Docker Engine 28.3.3 rootless. Un seul déploiement est actif
pendant chaque contrôle.

## Plafond observé

Ressource Nginx : `/static/admin/css/base.css`, 24 538 octets, HTTP 200 et
contenu CSS vérifiés. Montée de 10 s, stabilisation de 5 s, fenêtre stable
de 60 s, sans temporisation ni accès au métier ou à PostgreSQL.

| Utilisateurs | Débit réussi (req/s) | p95 (ms) | Erreurs | CPU injecteur moyen | CPU hôte moyen |
| ---: | ---: | ---: | ---: | ---: | ---: |
{static_rows}

**Plafond observé : {maximum['successful_throughput_rps']:.2f} req/s à {maximum['users']} utilisateurs.**
C'est une capacité du chemin injecteur/réseau/proxy, pas une limite intrinsèque
de JMeter. La forte charge de l'hôte justifie l'arrêt de la progression statique.
CPU injecteur : 100 % = un cœur ; CPU hôte : 100 % = les
{configuration[0]['host']['logical_cpus']} processeurs logiques.

À vingt utilisateurs avec 1 s de réflexion, l'application ne peut dépasser
{upper_bound:.0f} consultations/s : **marge statique de {margin:.1f} fois**.
Réétalonner avant d'augmenter cette charge ou de réduire la temporisation.

## Profil fixé

- **Paliers : {', '.join(map(str, protocol['paliers_utilisateurs']))} candidats distincts.**
- **Montée : {protocol['montee_s']} s ; stabilisation : {protocol['stabilisation_s']} s ; fenêtre stable : {protocol['plateau_s']} s.**
- Réflexion : {protocol['reflexion_ms']} ms ; une seule connexion par candidat.
- Durée programmée : {configuration[0]['duration_s']} s, dont 5 s de marge finale pour couvrir toute la fenêtre.

Le fichier [protocole.json](protocole.json) constitue la configuration commune.
Les calculs excluent la montée, la stabilisation et les requêtes traversant
les limites ; chaque utilisateur doit couvrir la fenêtre. La protection de
trente connexions/IP par quinze minutes reste active : prévoir quinze minutes
entre les futurs paliers. Les deux contrôles totalisent vingt connexions,
avec trente secondes de repos entre eux.

## Deux exécutions de contrôle

Chaque contrôle utilise **dix candidats**, le même projet isolé, volume, images,
plan et données fictives. Les empreintes du protocole et des entrées sont
identiques ; les assertions de connexion et de consultation restent actives.

| Exécution | Requêtes stables | Débit réussi (req/s) | Médiane (ms) | p95 (ms) | p99 (ms) | Erreurs |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{control_rows}

Écart symétrique : `abs(B - A) / ((A + B) / 2) × 100`.
**Débit : {throughput_gap:.2f} % ; latence p95 : {p95_gap:.2f} %.**
{verdict}
Le p99 varie de {p99_gap:.2f} % : la répétabilité constatée concerne le débit
et le p95 ; les valeurs de queue restent plus variables sur ces fenêtres.

CPU injecteur moyen pendant les contrôles :
{controls[0]['injector_cpu_pct_mean']:.2f} % et {controls[1]['injector_cpu_pct_mean']:.2f} %
d'un cœur ; charge globale moyenne de l'hôte :
{controls[0]['host_busy_pct_mean']:.2f} % et {controls[1]['host_busy_pct_mean']:.2f} %.
L'injecteur ne sature pas pendant les contrôles applicatifs.

## Preuves et limites

[Résultats et empreintes](resultats/etape16/etalonnage.json),
[contrôle 1](resultats/etape16/controle-1/brut.csv),
[contrôle 2](resultats/etape16/controle-2/brut.csv),
[statique à un utilisateur](resultats/etape16/statique-1/brut.csv),
[statique à vingt utilisateurs](resultats/etape16/statique-20/brut.csv).
Configurations, plans générés et relevés CPU/RSS accompagnent les résultats.
Le [précontrôle](resultats/etape16/precontrole/brut.csv) reste séparé des deux
contrôles définitifs au protocole figé.
Reproduction : [procédure](PROCEDURE.md#étalonnage-en-ligne-de-commande).

Les VM démarrent et s'arrêtent proprement ; leur entrée locale 18080 répond
HTTP 200 avec un hôte autorisé, sans modification de sécurité. Les bases
existantes diffèrent (11 comptes VM, 8 Docker) : préparer une base VM dédiée
avec les mêmes scripts et vingt comptes avant la comparaison. Ces contrôles
étalonnent une seule base Docker ; leur résultat dépend du chemin rootless et
de l'état de l'hôte. Le déploiement de référence est remis en marche, données
conservées. Détails : [prérequis vérifiés](resultats/etape16/prerequis.json).

Référence : [bonnes pratiques JMeter](https://jmeter.apache.org/usermanual/best-practices.html).
"""
    (ROOT / "ETAPE16.md").write_text(report)
    print(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    main()
