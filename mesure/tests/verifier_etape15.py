"""Check actual JMeter CSV samples, including the intentional failed assertion."""

import csv
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "resultats" / "etape15"


def verify(success_file, failure_file):
    with success_file.open() as stream:
        success = list(csv.DictReader(stream))
    with failure_file.open() as stream:
        failure = list(csv.DictReader(stream))
    expected = ["00 — CSRF", "01 — Connexion", "02 — Mes candidatures"]
    assert [row["label"] for row in success] == expected
    assert all(row["responseCode"] == "200" and row["success"] == "true" for row in success)
    assert [row["label"] for row in failure] == expected[:2]
    assert failure[0]["responseCode"] == "200" and failure[0]["success"] == "true"
    assert failure[1]["responseCode"] == "401" and failure[1]["success"] == "false"
    assert "HTTP 401" in failure[1]["failureMessage"]
    assert all(row["allThreads"] == "1" for row in success + failure)


if __name__ == "__main__":
    verify(RESULTS / "reussite.csv", RESULTS / "echec.csv")
    print("CLI : parcours réussi et refus HTTP 401 détecté par l'assertion.")
    if (RESULTS / "gui-reussite.csv").exists() or (RESULTS / "gui-echec.csv").exists():
        verify(RESULTS / "gui-reussite.csv", RESULTS / "gui-echec.csv")
        print("GUI : parcours réussi et refus HTTP 401 détecté par l'assertion.")
    multiple = RESULTS / "deux-utilisateurs.csv"
    if multiple.exists():
        with multiple.open() as stream:
            rows = list(csv.DictReader(stream))
        threads = {row["threadName"] for row in rows}
        assert len(threads) == 2 and len(rows) == 8
        assert all(row["success"] == "true" for row in rows)
        for thread in threads:
            assert [row["label"] for row in rows if row["threadName"] == thread] == [
                "00 — CSRF", "01 — Connexion", "02 — Mes candidatures", "02 — Mes candidatures"
            ]
        print("Deux candidats : une connexion et deux consultations réussies chacun.")
