"""Read-only source attribution audit; imported rows are not the upstream market."""

from collections import Counter, defaultdict

from django.utils import timezone

from jobboard.api.catalogue import open_offers
from jobboard.models import BoardSchedule, ImportRun, OfferSource, SourceBoard
from jobboard.services.engine_filters import fresh_sources


def audit_sources():
    now = timezone.now()
    visible = set(open_offers().values_list("pk", flat=True))
    fresh = set(fresh_sources(now).values_list("pk", flat=True))
    schedules = {s.board_id: s for s in BoardSchedule.objects.all()}
    runs = {}
    for run in ImportRun.objects.order_by("board_id", "-started_at", "-pk").distinct(
        "board_id"
    ):
        runs[run.board_id] = run
    boards = {}
    samples = defaultdict(list)
    for board in SourceBoard.objects.filter(enabled=True).select_related("company"):
        schedule, run = schedules.get(board.pk), runs.get(board.pk)
        boards[board.pk] = {
            "board_id": board.pk,
            "provider": board.provider,
            "company": board.company.name if board.company else None,
            "url": board.base_url,
            "paused": schedule.paused if schedule else None,
            "last_error": schedule.last_error_code if schedule else None,
            "next_run_at": schedule.next_run_at.isoformat() if schedule else None,
            "collection_checkpoint": schedule.collection_checkpoint if schedule else {},
            "last_success_at": board.last_success_at.isoformat()
            if board.last_success_at
            else None,
            "last_run": {
                "id": run.pk,
                "status": run.status,
                "normalized_seen": run.seen_count,
                "full": run.is_full_snapshot,
                "diagnostics": run.diagnostics,
            }
            if run
            else None,
            "buckets": Counter(),
            "internship_confirmed": 0,
            "europe_confirmed": 0,
        }
    for source in (
        OfferSource.objects.filter(board_id__in=boards)
        .values(
            "pk",
            "board_id",
            "offer_id",
            "source_status",
            "offer__status",
            "offer__title",
            "offer__expires_at",
            "offer__enrichment__classification",
            "offer__enrichment__europe_status",
        )
        .iterator()
    ):
        row = boards[source["board_id"]]
        cls, geo = (
            source["offer__enrichment__classification"],
            source["offer__enrichment__europe_status"],
        )
        row["internship_confirmed"] += cls == "confirmed"
        row["europe_confirmed"] += geo == "in_scope"
        if source["source_status"] != "active":
            bucket = "source_inactive"
        elif source["pk"] not in fresh:
            bucket = "source_not_fresh"
        elif source["offer__status"] != "open":
            bucket = "offer_not_open"
        elif cls == "not_internship":
            bucket = "not_internship"
        elif cls != "confirmed":
            bucket = "internship_uncertain"
        elif geo == "out_of_scope":
            bucket = "outside_europe"
        elif geo != "in_scope":
            bucket = "geography_uncertain"
        elif source["offer__expires_at"] and source["offer__expires_at"] <= now:
            bucket = "expired"
        elif source["offer_id"] in visible:
            bucket = "published"
        else:
            bucket = "other_publication_rule"
        row["buckets"][bucket] += 1
        if (
            bucket in {"internship_uncertain", "geography_uncertain"}
            and len(samples[source["board_id"]]) < 10
        ):
            samples[source["board_id"]].append(
                {
                    "source_id": source["pk"],
                    "offer_id": source["offer_id"],
                    "title": source["offer__title"],
                    "bucket": bucket,
                }
            )
    totals = Counter()
    for pk, row in boards.items():
        row["imported_source_rows"] = sum(row["buckets"].values())
        row["review_candidates"] = sum(
            row["buckets"][k] for k in ("internship_uncertain", "geography_uncertain")
        )
        row["samples"] = samples[pk]
        totals.update(row["buckets"])
    return {
        "measured_at": now.isoformat(),
        "visible_offer_ids": sorted(visible),
        "totals": dict(totals),
        "counting_note": "Buckets partition persisted source rows on enabled boards. Sources overlap by offer; last normalized snapshot is not raw upstream count. Uncertainty is not proof of a missed internship.",
        "boards": sorted(
            boards.values(),
            key=lambda row: (-row["review_candidates"], row["board_id"]),
        ),
    }
