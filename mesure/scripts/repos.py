"""Decide whether fresh service readings demonstrate a continuous idle window."""

import math

SERVICES = ("proxy", "metier", "donnees")


def service_blocker(service, rows, now, policy):
    def blocked(reason, **fields):
        return dict(service=service, reason=reason, **fields)

    if not rows:
        return blocked("missing_samples")
    age = now - rows[-1]["epoch_s"]
    if not 0 <= age <= policy["fraicheur_s"]:
        return blocked("stale_samples", age_s=age, maximum_s=policy["fraicheur_s"])
    covered = 0
    next_start = None
    for row in reversed(rows):
        interval = row["interval_s"]
        if not math.isfinite(interval) or not 0 < interval <= policy["fraicheur_s"]:
            return blocked("invalid_interval")
        if next_start is not None and abs(next_start - row["epoch_s"]) > 1:
            return blocked("interrupted_window")
        fields = {"cpu_pct": policy["cpu_max_pct"],
                  "read_bytes_per_s": policy["io_max_octets_s"],
                  "write_bytes_per_s": policy["io_max_octets_s"]}
        if service == "donnees":
            fields["db_active_connections"] = policy["connexions_actives_max"]
        for field, maximum in fields.items():
            value = row.get(field)
            if value is None or not math.isfinite(value) or value < 0:
                return blocked("missing_or_invalid_metric", metric=field)
            if value > maximum:
                return blocked("above_limit", metric=field, value=value,
                               maximum=maximum, epoch_s=row["epoch_s"])
        covered += interval
        next_start = row["epoch_s"] - interval
        if covered >= policy["stabilite_s"]:
            return None
    return blocked("short_window", covered_s=covered, required_s=policy["stabilite_s"])


def idle_blockers(samples, now, policy):
    """Explain why the frozen idle rule rejects the supplied readings."""
    return [reason for service in SERVICES
            if (reason := service_blocker(service, samples.get(service, []), now, policy))]


def idle_window(samples, now, policy):
    """Missing readings and interrupted windows never count as idle evidence."""
    return not idle_blockers(samples, now, policy)
