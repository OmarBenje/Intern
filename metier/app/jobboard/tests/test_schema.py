from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from jobboard import models as m


class DatabaseSchemaTests(TestCase):
    def test_application_prevents_duplicate_candidate_offer(self):
        from jobboard.models import Company, Offer, Role

        application_model = apps.get_model("jobboard", "Application")
        board_model = apps.get_model("jobboard", "SourceBoard")
        source_model = apps.get_model("jobboard", "OfferSource")
        user = get_user_model().objects.create_user(username="candidate")
        company = Company.objects.create(name="Company")
        role = Role.objects.create(name="Engineer", slug="engineer")
        offer = Offer.objects.create(
            company=company, role=role, title="Engineer", description="Python"
        )
        board = board_model.objects.create(
            provider="test", board_key="company", base_url="https://example.com"
        )
        source = source_model.objects.create(
            offer=offer,
            board=board,
            external_id="1",
            origin_url="https://example.com/job",
            apply_url="https://example.com/apply",
            content_hash="a" * 64,
        )
        application_model.objects.create(user=user, offer=offer, source=source)
        with self.assertRaises(IntegrityError), transaction.atomic():
            application_model.objects.create(user=user, offer=offer, source=source)


class CatalogueTests(TestCase):
    def test_unknown_defaults_and_generated_full_text_search(self):
        from django.contrib.postgres.search import SearchQuery

        from jobboard.models import Company, Offer

        company = Company.objects.create(name="Company")
        offer = Offer.objects.create(
            company=company, title="Engineer", description="PostgreSQL Django"
        )
        self.assertEqual(offer.contract_type, "unknown")
        self.assertEqual(offer.work_mode, "unknown")
        self.assertEqual(
            list(
                Offer.objects.filter(
                    search_vector=SearchQuery("Django", config="simple")
                )
            ),
            [offer],
        )


class ProfileTests(TestCase):
    def test_current_experience_cannot_have_an_end_date(self):
        from datetime import date

        from jobboard.models import CandidateProfile, Experience

        user = get_user_model().objects.create_user(username="profile-test")
        profile = CandidateProfile.objects.create(user=user, full_name="Candidate")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Experience.objects.create(
                profile=profile,
                company_name="Company",
                title="Engineer",
                is_current=True,
                end_date=date(2026, 1, 1),
            )


class OwnershipTests(TestCase):
    def test_current_resume_cannot_belong_to_another_user(self):
        from jobboard.models import CandidateProfile, Document

        owner = get_user_model().objects.create_user(username="owner")
        other = get_user_model().objects.create_user(username="other")
        document = Document.objects.create(
            owner=other,
            kind="resume",
            origin="upload",
            bucket="private",
            object_key="other-resume",
            mime_type="application/pdf",
            byte_size=10,
            sha256="a" * 64,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            CandidateProfile.objects.create(
                user=owner, full_name="Owner", current_resume=document
            )


class WorkflowConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from datetime import timedelta

        from django.utils import timezone

        from jobboard import models as m

        cls.owner = get_user_model().objects.create_user(username="workflow-owner")
        cls.other = get_user_model().objects.create_user(username="workflow-other")
        cls.company = m.Company.objects.create(name="Company")
        cls.offer = m.Offer.objects.create(
            company=cls.company, title="Engineer", description="Python"
        )
        cls.other_offer = m.Offer.objects.create(
            company=cls.company, title="Designer", description="Design"
        )
        cls.board = m.SourceBoard.objects.create(
            provider="test", board_key="company", base_url="https://example.com"
        )
        cls.source = m.OfferSource.objects.create(
            offer=cls.offer,
            board=cls.board,
            external_id="1",
            origin_url="https://example.com/1",
            apply_url="https://example.com/1/apply",
            content_hash="a" * 64,
        )
        cls.application = m.Application.objects.create(
            user=cls.owner, offer=cls.offer, source=cls.source
        )
        cls.revision = m.ApplicationRevision.objects.create(
            application=cls.application,
            user=cls.owner,
            revision_no=1,
            profile_snapshot={},
            offer_snapshot={},
            form_snapshot={},
        )
        cls.document = m.Document.objects.create(
            owner=cls.owner,
            kind="resume",
            origin="upload",
            bucket="private",
            object_key="owner.pdf",
            mime_type="application/pdf",
            byte_size=10,
            sha256="b" * 64,
        )
        cls.foreign_document = m.Document.objects.create(
            owner=cls.other,
            kind="resume",
            origin="upload",
            bucket="private",
            object_key="other.pdf",
            mime_type="application/pdf",
            byte_size=10,
            sha256="c" * 64,
        )
        cls.authorization = m.SubmissionAuthorization.objects.create(
            application=cls.application,
            revision=cls.revision,
            user=cls.owner,
            approved_hash="a" * 64,
            expires_at=timezone.now() + timedelta(hours=1),
        )

    def run_values(self, **overrides):
        return dict(
            application=self.application,
            user=self.owner,
            revision=self.revision,
            purpose="submit",
            authorization=self.authorization,
            attempt_no=1,
            **overrides,
        )

    def test_source_from_another_offer_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Application.objects.create(
                user=self.other, offer=self.other_offer, source=self.source
            )

    def test_salary_source_must_match_offer(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.CompensationBand.objects.create(
                offer=self.other_offer,
                source=self.source,
                minimum=10,
                currency="EUR",
                period="hour",
            )

    def test_last_seen_import_must_belong_to_same_board(self):
        board = m.SourceBoard.objects.create(
            provider="test", board_key="other", base_url="https://example.com"
        )
        run = m.ImportRun.objects.create(board=board)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.OfferSource.objects.filter(pk=self.source.pk).update(last_seen_run=run)

    def test_revision_owner_cannot_differ_from_application(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.ApplicationRevision.objects.create(
                application=self.application,
                user=self.other,
                revision_no=2,
                profile_snapshot={},
                offer_snapshot={},
                form_snapshot={},
            )

    def test_revision_rejects_foreign_document(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.RevisionDocument.objects.create(
                revision=self.revision,
                user=self.owner,
                document=self.foreign_document,
                purpose="resume",
            )

    def test_revision_rejects_document_with_wrong_purpose(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.RevisionDocument.objects.create(
                revision=self.revision,
                user=self.owner,
                document=self.document,
                purpose="cover_letter",
            )

    def test_document_derivation_cannot_cross_owners(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Document.objects.filter(pk=self.document.pk).update(
                derived_from=self.foreign_document
            )

    def test_resume_link_accepts_correct_owner_and_kind(self):
        profile = m.CandidateProfile.objects.create(
            user=self.owner, full_name="Owner", current_resume=self.document
        )
        link = m.RevisionDocument.objects.create(
            revision=self.revision,
            user=self.owner,
            document=self.document,
            purpose="resume",
        )
        self.assertEqual(profile.current_resume, link.document)

    def test_run_cannot_use_authorization_for_another_revision(self):
        revision = m.ApplicationRevision.objects.create(
            application=self.application,
            user=self.owner,
            revision_no=2,
            profile_snapshot={},
            offer_snapshot={},
            form_snapshot={},
        )
        values = self.run_values()
        values["revision"] = revision
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.AgentRun.objects.create(**values)

    def test_only_one_unrevoked_authorization_per_revision(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.SubmissionAuthorization.objects.create(
                application=self.application,
                revision=self.revision,
                user=self.owner,
                approved_hash="a" * 64,
                expires_at=self.authorization.expires_at,
            )

    def test_uncertain_run_blocks_retry(self):
        m.AgentRun.objects.create(**self.run_values(status="uncertain"))
        values = self.run_values()
        values["attempt_no"] = 2
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.AgentRun.objects.create(**values)

    def test_terminal_run_allows_another_attempt(self):
        m.AgentRun.objects.create(**self.run_values(status="failed"))
        values = self.run_values()
        values["attempt_no"] = 2
        retry = m.AgentRun.objects.create(**values)
        self.assertEqual(retry.attempt_no, 2)

    def test_submission_without_authorization_is_rejected(self):
        values = self.run_values()
        values["authorization"] = None
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.AgentRun.objects.create(**values)

    def test_evidence_cannot_belong_to_another_user(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.AgentRun.objects.create(
                **self.run_values(evidence_document=self.foreign_document)
            )

    def test_event_cannot_reference_run_in_another_application(self):
        from django.utils import timezone

        run = m.AgentRun.objects.create(**self.run_values())
        other_application = m.Application.objects.create(
            user=self.other, offer=self.offer, source=self.source
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.ApplicationEvent.objects.create(
                application=other_application,
                run=run,
                kind="submission_confirmed",
                origin="agent",
                happened_at=timezone.now(),
            )

    def test_confirmation_event_is_deduplicated(self):
        from django.utils import timezone

        values = dict(
            application=self.application,
            kind="submission_confirmed",
            origin="agent",
            happened_at=timezone.now(),
            dedupe_key="receipt:123",
        )
        m.ApplicationEvent.objects.create(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.ApplicationEvent.objects.create(**values)

    def test_json_answers_must_be_an_array(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.ApplicationRevision.objects.filter(pk=self.revision.pk).update(answers={})

    def test_json_snapshot_must_be_an_object(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.ApplicationRevision.objects.filter(pk=self.revision.pk).update(
                profile_snapshot=[]
            )

    def test_sealed_revision_requires_content_hash(self):
        from django.utils import timezone

        with self.assertRaises(IntegrityError), transaction.atomic():
            m.ApplicationRevision.objects.filter(pk=self.revision.pk).update(
                sealed_at=timezone.now()
            )

    def test_negative_and_inverted_salary_ranges_are_rejected(self):
        for lower, upper in [(-1, 10), (20, 10)]:
            with (
                self.subTest(lower=lower, upper=upper),
                self.assertRaises(IntegrityError),
                transaction.atomic(),
            ):
                m.CompensationBand.objects.create(
                    offer=self.offer,
                    source=self.source,
                    minimum=lower,
                    maximum=upper,
                    currency="EUR",
                    period="hour",
                )

    def test_salary_preference_requires_currency_and_period(self):
        profile = m.CandidateProfile.objects.create(user=self.owner, full_name="Owner")
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.SearchPreference.objects.create(profile=profile, minimum_salary=100)

    def test_outbox_deduplicates_commands(self):
        m.OutboxMessage.objects.create(
            topic="submit",
            dedupe_key="submit:1",
            payload={"run_id": 1},
            owner=self.owner,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.OutboxMessage.objects.create(
                topic="submit",
                dedupe_key="submit:1",
                payload={"run_id": 1},
                owner=self.owner,
            )

    def test_company_deletion_preserves_existing_applications(self):
        from django.db.models.deletion import ProtectedError

        with self.assertRaises(ProtectedError):
            self.company.delete()
        self.assertTrue(m.Application.objects.filter(pk=self.application.pk).exists())

    def test_same_external_id_is_allowed_in_different_boards(self):
        board = m.SourceBoard.objects.create(
            provider="test", board_key="other", base_url="https://example.com"
        )
        source = m.OfferSource.objects.create(
            offer=self.offer,
            board=board,
            external_id="1",
            origin_url="https://example.com/1",
            apply_url="https://example.com/1/apply",
            content_hash="a" * 64,
        )
        self.assertNotEqual(self.source.pk, source.pk)
