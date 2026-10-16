"""Decide whether fresh service readings demonstrate a continuous idle window."""

import math

SERVICES = ("proxy", "metier", "donnees")


def idle_window(samples, now, policy):
    """Missing readings and interrupted windows never count as idle evidence."""
    for service in SERVICES:
        rows = samples.get(service, [])
        if not rows or not 0 <= now - rows[-1]["epoch_s"] <= policy["fraicheur_s"]:
            return False
        covered = 0
        next_start = None
        for row in reversed(rows):
            interval = row["interval_s"]
            if not math.isfinite(interval) or not 0 < interval <= policy["fraicheur_s"]:
                return False
            if next_start is not None and abs(next_start - row["epoch_s"]) > 1:
                return False
            fields = {"cpu_pct": policy["cpu_max_pct"],
                      "read_bytes_per_s": policy["io_max_octets_s"],
                      "write_bytes_per_s": policy["io_max_octets_s"]}
            if service == "donnees":
                fields["db_active_connections"] = policy["connexions_actives_max"]
            for field, maximum in fields.items():
                value = row.get(field)
                if value is None or not math.isfinite(value) or not 0 <= value <= maximum:
                    return False
            covered += interval
            next_start = row["epoch_s"] - interval
            if covered >= policy["stabilite_s"]:
                break
        if covered < policy["stabilite_s"]:
            return False
    return True
