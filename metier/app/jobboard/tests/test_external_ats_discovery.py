from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import AtsProbe, Company, DiscoveryResult, SourceCandidate
from jobboard.services.external_ats_discovery import discover_external


class ExternalDiscoveryTests(TestCase):
    def lead(self, **changes):
        return dict(
            company="New Employer",
            country="FI",
            url="https://jobs.lever.co/new-employer",
            evidence_url="https://jobs.lever.co/new-employer/123",
            title="Internship",
            excerpt="Internship in Finland",
            reviewed_at=timezone.localdate().isoformat(),
            **changes,
        )

    def test_preview_then_apply_and_idempotence(self):
        self.assertEqual(len(discover_external([self.lead()])["enrolled"]), 1)
        self.assertFalse(SourceCandidate.objects.exists())
        result = discover_external([self.lead()], apply=True)
        probe = AtsProbe.objects.get(pk=result["enrolled"][0]["probe_id"])
        probe.state = "error"
        probe.next_attempt_at = timezone.now() + timedelta(days=4)
        probe.save()
        deadline = probe.next_attempt_at
        self.assertEqual(
            discover_external([self.lead()], apply=True)["skipped"][0]["reason"],
            "already_queued",
        )
        probe.refresh_from_db()
        self.assertEqual(probe.next_attempt_at, deadline)
        self.assertEqual(probe.state, "error")
        self.assertFalse(DiscoveryResult.objects.get().query.enabled)

    def test_entire_manifest_validated_before_writes(self):
        bad = self.lead()
        bad["country"] = "US"
        with self.assertRaises(ValueError):
            discover_external([self.lead(), bad], apply=True)
        self.assertFalse(AtsProbe.objects.exists())

    def test_known_employer_and_conflict_excluded(self):
        Company.objects.create(name="NEW EMPLOYER")
        self.assertEqual(
            discover_external([self.lead()], apply=True)["skipped"][0]["reason"],
            "known_employer",
        )
        Company.objects.all().delete()
        SourceCandidate.objects.create(
            url="https://jobs.lever.co/new-employer",
            provider="lever",
            instance="global",
            board_key="new-employer",
            company_name="Different company",
        )
        self.assertEqual(
            discover_external([self.lead()], apply=True)["skipped"][0]["reason"],
            "conflicting_employer_identity",
        )
        self.assertFalse(AtsProbe.objects.exists())

    def test_invalid_proof_and_budget(self):
        for field, value in [
            ("reviewed_at", "2000-01-01"),
            ("evidence_url", "https://jobs.lever.co/other/123"),
            ("url", "https://user:password@jobs.lever.co/new-employer"),
        ]:
            lead = self.lead()
            lead[field] = value
            with (
                self.subTest(field=field),
                self.assertRaises((ValueError, CatalogueImportError)),
            ):
                discover_external([lead], apply=True)
        with self.assertRaises(ValueError):
            discover_external([self.lead()] * 101)
        self.assertFalse(AtsProbe.objects.exists())

    def test_batch_deduplicated(self):
        result = discover_external([self.lead(), self.lead()], apply=True)
        self.assertEqual(len(result["enrolled"]), 1)
        self.assertEqual(result["skipped"][0]["reason"], "duplicate_in_batch")

    def test_existing_case_alias_reused(self):
        candidate = SourceCandidate.objects.create(
            url="https://jobs.lever.co/NEW-EMPLOYER",
            provider="lever",
            instance="global",
            board_key="NEW-EMPLOYER",
            company_name="New Employer",
        )
        result = discover_external([self.lead()], apply=True)
        self.assertEqual(result["enrolled"][0]["candidate_id"], candidate.pk)
        self.assertEqual(SourceCandidate.objects.count(), 1)

    def test_known_board_excluded_even_with_different_label(self):
        from jobboard.models import SourceBoard

        company = Company.objects.create(name="Employer group")
        SourceBoard.objects.create(
            provider="lever",
            instance="global",
            board_key="NEW-EMPLOYER",
            company=company,
            base_url="https://jobs.lever.co/NEW-EMPLOYER",
        )
        self.assertEqual(
            discover_external([self.lead()], apply=True)["skipped"][0]["reason"],
            "known_board",
        )
        self.assertFalse(AtsProbe.objects.exists())
