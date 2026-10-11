import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from pypdf import PdfWriter

from jobboard import models as m
from jobboard.api.core import APIError
from jobboard.integrations.submission import SubmissionResult, basic_form, fingerprint
from jobboard.services import applications as service
from jobboard.services import worker
from jobboard.services.documents import set_resume, upload_document


def form():
    result = basic_form()
    result["fields"] = [f for f in result["fields"] if f["key"] != "resume"]
    result["fields"].append(
        {
            "key": "resume",
            "label": "Resume",
            "type": "file",
            "required": True,
            "options": [],
        }
    )
    result["supported"] = True
    result["form_fingerprint"] = fingerprint(result)
    return result


class FakeAdapter:
    version = "test-v1"
    result = SubmissionResult("succeeded", receipt="provider-receipt-123")
    calls = 0

    def ensure_enabled(self):
        pass

    def fetch_form(self):
        return form()

    def submit(self, revision, documents):
        type(self).calls += 1
        assert documents["resume"][1].startswith(b"%PDF")
        return self.result


class WorkflowSetup:
    def setUp(self):
        super().setUp()
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(
            PRIVATE_STORAGE_BACKEND="local",
            PRIVATE_STORAGE_ROOT=self.directory.name,
            PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        FakeAdapter.result = SubmissionResult(
            "succeeded", receipt="provider-receipt-123"
        )
        FakeAdapter.calls = 0
        for target, value in [
            ("jobboard.services.applications.fetch_form", form()),
            ("jobboard.services.applications.get_adapter", FakeAdapter()),
            ("jobboard.services.worker.get_adapter", FakeAdapter()),
        ]:
            mock = patch(target, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)
        self.user = get_user_model().objects.create_user(
            username="workflow", password="secret", email="candidate@example.com"
        )
        self.other = get_user_model().objects.create_user(
            username="other", password="secret"
        )
        self.profile = m.CandidateProfile.objects.create(
            user=self.user,
            full_name="Ada Example",
            first_name="Ada",
            last_name="Example",
        )
        writer, content = PdfWriter(), io.BytesIO()
        writer.add_blank_page(width=100, height=100)
        writer.write(content)
        self.document = upload_document(
            self.user,
            SimpleUploadedFile(
                "resume.pdf", content.getvalue(), content_type="application/pdf"
            ),
            "resume",
        )
        set_resume(self.user, self.document.pk)
        company = m.Company.objects.create(name="Example")
        self.offer = m.Offer.objects.create(
            company=company, title="Engineer", description="Python"
        )
        self.board = m.SourceBoard.objects.create(
            provider="test",
            board_key="example",
            base_url="https://example.com",
            company=company,
        )
        self.source = m.OfferSource.objects.create(
            offer=self.offer,
            board=self.board,
            external_id="1",
            origin_url="https://example.com/job",
            apply_url="https://example.com/apply",
            content_hash="a" * 64,
        )
        self.app = service.create_application(self.user, self.offer.pk, self.source.pk)
        self.revision = service.prepare(self.user, self.app.pk)

    def approve(self, key=None):
        return service.approve(
            self.user,
            self.app.pk,
            self.revision.pk,
            self.revision.content_hash,
            key or uuid.uuid4(),
        )


class WorkflowTests(WorkflowSetup, TestCase):
    def test_create_and_approve_are_idempotent(self):
        self.assertEqual(
            service.create_application(self.user, self.offer.pk, self.source.pk).pk,
            self.app.pk,
        )
        key = uuid.uuid4()
        first = self.approve(key)
        self.assertEqual(first.pk, self.approve(key).pk)
        self.assertEqual(m.AgentRun.objects.count(), 1)
        self.assertEqual(
            m.OutboxMessage.objects.filter(topic="application.submit").count(), 1
        )
        with self.assertRaises(APIError):
            self.approve()

    def test_revision_snapshots_and_hash_immutable_and_stale_approval_rejected(self):
        original = self.revision.profile_snapshot
        self.profile.first_name = "Changed"
        self.profile.save()
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.profile_snapshot, original)
        answers = [
            {**a, "value": "New name" if a["field_key"] == "first_name" else a["value"]}
            for a in self.revision.answers
        ]
        new = service.revise(self.user, self.app.pk, answers, [self.document.pk])
        self.assertNotEqual(new.content_hash, self.revision.content_hash)
        with self.assertRaisesMessage(APIError, "latest dossier"):
            self.approve()
        self.assertEqual(
            service.content_hash(self.revision), self.revision.content_hash
        )

    def test_missing_answer_and_foreign_document_rejected(self):
        new = service.revise(self.user, self.app.pk, [], [self.document.pk])
        with self.assertRaises(APIError) as caught:
            service.approve(
                self.user, self.app.pk, new.pk, new.content_hash, uuid.uuid4()
            )
        self.assertEqual(caught.exception.code, "missing_answers")
        with self.assertRaises(APIError):
            service.checked_documents(self.other, [self.document.pk])

    def test_source_change_and_document_tampering_block_approval(self):
        self.source.apply_url = "https://example.com/new"
        self.source.save()
        with self.assertRaises(APIError) as caught:
            self.approve()
        self.assertEqual(caught.exception.code, "source_changed")
        self.source.apply_url = "https://example.com/apply"
        self.source.save()
        m.Document.objects.filter(pk=self.document.pk).update(sha256="b" * 64)
        with self.assertRaises(APIError):
            self.approve()
        self.assertFalse(m.AgentRun.objects.exists())

    def test_success_updates_run_application_event_and_outbox_once(self):
        run = self.approve()
        self.assertTrue(worker.process_one())
        run.refresh_from_db()
        self.app.refresh_from_db()
        self.assertEqual(run.status, "succeeded")
        self.assertEqual(self.app.status, "submitted")
        self.assertIsNotNone(self.app.submitted_at)
        self.assertEqual(self.app.events.filter(kind="submission_confirmed").count(), 1)
        self.assertIsNotNone(m.OutboxMessage.objects.get().processed_at)
        self.assertFalse(worker.process_one())
        self.assertEqual(FakeAdapter.calls, 1)

    def test_expired_authorization_fails_before_send(self):
        run = self.approve()
        m.SubmissionAuthorization.objects.filter(pk=run.authorization_id).update(
            granted_at=timezone.now() - timedelta(days=2),
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(worker.process_one())
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertEqual(FakeAdapter.calls, 0)

    def test_revoke_fences_running_worker_before_submit(self):
        run = self.approve()
        pk, token = worker.claim()
        service.revoke(self.user, self.app.pk)
        with self.assertRaises(APIError):
            worker.begin_submission(
                pk, token, self.revision.form_snapshot["form_fingerprint"]
            )
        run.refresh_from_db()
        self.assertEqual(run.status, "cancelled")

    def test_form_change_stops_worker_before_send(self):
        run = self.approve()
        with patch.object(
            FakeAdapter, "fetch_form", return_value={"form_fingerprint": "changed"}
        ):
            worker.process_one()
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.error_code, "form_changed")
        self.assertEqual(FakeAdapter.calls, 0)

    def test_uncertain_never_retried_and_requires_explicit_resolution(self):
        FakeAdapter.result = SubmissionResult("uncertain", error_code="timeout")
        run = self.approve()
        worker.process_one()
        self.assertFalse(worker.process_one())
        self.assertEqual(FakeAdapter.calls, 1)
        with self.assertRaises(APIError):
            self.approve()
        with self.assertRaises(APIError):
            service.resolve(self.user, self.app.pk, "submitted", "receipt")
        m.AgentRun.objects.filter(pk=run.pk).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )
        service.resolve(self.user, self.app.pk, "submitted", "verified-reference")
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, "submitted")
        self.assertEqual(self.app.events.get(kind="submission_resolved").origin, "user")

    def test_expired_submitting_lease_becomes_uncertain_stale_worker_cannot_finish(
        self,
    ):
        run = self.approve()
        pk, token = worker.claim()
        worker.begin_submission(
            pk, token, self.revision.form_snapshot["form_fingerprint"]
        )
        m.AgentRun.objects.filter(pk=run.pk).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )
        worker.recover_expired()
        run.refresh_from_db()
        self.assertEqual(run.status, "uncertain")
        with self.assertRaises(APIError):
            worker.finish(pk, token, SubmissionResult("succeeded", "late-receipt"))
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, "draft")

    def test_disable_account_blocks_before_side_effect_but_allows_inflight_receipt(
        self,
    ):
        run = self.approve()
        pk, token = worker.claim()
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        with self.assertRaises(APIError):
            worker.begin_submission(
                pk, token, self.revision.form_snapshot["form_fingerprint"]
            )
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=True)
        worker.begin_submission(
            pk, token, self.revision.form_snapshot["form_fingerprint"]
        )
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        worker.finish(pk, token, SubmissionResult("succeeded", "inflight-receipt"))
        run.refresh_from_db()
        self.assertEqual(run.status, "succeeded")

    def test_http_ownership_status_and_related_validation(self):
        self.client.force_login(self.other)
        for suffix in ["", "tasks/", "interviews/"]:
            self.assertEqual(
                self.client.get(
                    f"/api/v1/applications/{self.app.pk}/{suffix}"
                ).status_code,
                404,
            )
        self.client.force_login(self.user)
        endpoint = f"/api/v1/applications/{self.app.pk}/interviews/"
        invalid = self.client.post(
            endpoint,
            {
                "title": "Meet",
                "starts_at": "2026-10-02T12:00:00Z",
                "ends_at": "2026-10-01T12:00:00Z",
            },
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 400, invalid.content)
        valid = self.client.post(
            endpoint,
            {
                "title": "Meet",
                "starts_at": "2026-10-02T12:00:00Z",
                "display_timezone": "Europe/Paris",
            },
            content_type="application/json",
        )
        self.assertEqual(valid.status_code, 200, valid.content)
        task = self.client.post(
            f"/api/v1/applications/{self.app.pk}/tasks/",
            {"title": "Follow up"},
            content_type="application/json",
        )
        self.assertEqual(task.status_code, 200, task.content)

    def test_deleted_run_is_a_stale_worker_not_an_uncaught_exception(self):
        pk, token = 999999, uuid.uuid4()
        with self.assertRaises(APIError) as caught:
            worker.begin_submission(pk, token, self.revision.form_snapshot['form_fingerprint'])
        self.assertEqual(caught.exception.code, 'stale_worker')
        with self.assertRaises(APIError):
            worker.finish(pk, token, SubmissionResult('succeeded', 'late'))

    def test_json_field_types_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(
            f"/api/v1/applications/{self.app.pk}/status/",
            {"status": {}, "reason": "test"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            "/api/v1/applications/",
            {"offer_id": True, "source_id": self.source.pk},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class WorkflowConcurrencyTests(WorkflowSetup, TransactionTestCase):
    def test_concurrent_approvals_share_one_run(self):
        key = uuid.uuid4()

        def submit(_):
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=self.user.pk)
                return service.approve(
                    user, self.app.pk, self.revision.pk, self.revision.content_hash, key
                ).pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(submit, range(2)))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(m.AgentRun.objects.count(), 1)
        self.assertEqual(m.OutboxMessage.objects.count(), 1)

    def test_concurrent_workers_claim_once(self):
        self.approve()

        def take(_):
            close_old_connections()
            try:
                return worker.claim()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(take, range(2)))
        self.assertEqual(sum(claim is not None for claim in claims), 1)
