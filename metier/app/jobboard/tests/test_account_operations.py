import json
import zipfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from jobboard import models as m
from jobboard.api.core import APIError
from jobboard.services.accounts import export_account, purge_account, request_deletion


class AccountOperationsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="owner", email="owner@example.test", password="correct-password"
        )
        self.other = get_user_model().objects.create_user(
            username="other", email="other@example.test"
        )
        self.profile = m.CandidateProfile.objects.create(
            user=self.user, full_name="Owner"
        )
        m.Experience.objects.create(
            profile=self.profile, company_name="Private history", title="Engineer"
        )
        company = m.Company.objects.create(name="Company")
        offer = m.Offer.objects.create(
            company=company, title="Engineer", description="Python"
        )
        board = m.SourceBoard.objects.create(
            provider="test", board_key="board", base_url="https://example.test"
        )
        source = m.OfferSource.objects.create(
            offer=offer,
            board=board,
            external_id="1",
            origin_url="https://example.test/1",
            apply_url="https://example.test/apply",
            content_hash="a" * 64,
        )
        self.application = m.Application.objects.create(
            user=self.user, offer=offer, source=source
        )
        self.revision = m.ApplicationRevision.objects.create(
            application=self.application,
            user=self.user,
            revision_no=1,
            profile_snapshot={"name": "Owner"},
            offer_snapshot={},
            form_snapshot={},
            answers=[],
        )
        self.document = m.Document.objects.create(
            owner=self.user,
            kind="resume",
            origin="upload",
            bucket="private",
            object_key="private/object",
            original_name="../../danger.pdf",
            mime_type="application/pdf",
            byte_size=8,
            sha256="a" * 64,
            status="ready",
        )
        self.profile.current_resume = self.document
        self.profile.save()
        m.RevisionDocument.objects.create(
            revision=self.revision,
            user=self.user,
            document=self.document,
            purpose="resume",
        )
        self.authorization = m.SubmissionAuthorization.objects.create(
            revision=self.revision,
            application=self.application,
            user=self.user,
            approved_hash="a" * 64,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.run = m.AgentRun.objects.create(
            application=self.application,
            user=self.user,
            revision=self.revision,
            authorization=self.authorization,
            purpose="submit",
            attempt_no=1,
        )
        m.ApplicationEvent.objects.create(
            application=self.application,
            run=self.run,
            kind="test",
            origin="system",
            happened_at=timezone.now(),
        )
        m.ApplicationTask.objects.create(
            application=self.application, title="Follow up"
        )
        m.Interview.objects.create(
            application=self.application, title="Interview", starts_at=timezone.now()
        )
        m.OutboxMessage.objects.create(
            owner=self.user,
            topic="submission",
            dedupe_key="test",
            payload={"run_id": self.run.pk},
        )

    @patch("jobboard.services.documents.read_document", return_value=b"%PDF-ok\n")
    def test_export_is_complete_and_private(self, read):
        with (
            export_account(self.user) as exported,
            zipfile.ZipFile(exported) as archive,
        ):
            data = json.loads(archive.read("data.json"))
            self.assertEqual(data["account"]["email"], "owner@example.test")
            self.assertEqual(data["experiences"][0]["company_name"], "Private history")
            self.assertEqual(len(data["revisions"]), 1)
            self.assertEqual(len(data["tasks"]), 1)
            self.assertEqual(len(data["interviews"]), 1)
            self.assertNotIn("password", data["account"])
            self.assertNotIn("worker_token", data["runs"][0])
            self.assertNotIn("object_key", data["documents"][0])
            self.assertNotIn("other@example.test", archive.read("data.json").decode())
            self.assertEqual(
                archive.read(f"documents/{self.document.pk}.pdf"), b"%PDF-ok\n"
            )
        read.assert_called_once()

    @patch("jobboard.services.accounts.MAX_EXPORT_BYTES", 4)
    def test_export_limit_precedes_storage_access(self):
        with (
            patch("jobboard.services.documents.read_document") as read,
            self.assertRaises(APIError) as error,
        ):
            export_account(self.user)
        self.assertEqual(error.exception.status, 413)
        read.assert_not_called()

    def test_wrong_password_does_not_deactivate(self):
        with self.assertRaises(APIError):
            request_deletion(self.user, "incorrect")
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertFalse(m.DeletionRequest.objects.exists())

    @patch("jobboard.services.documents.delete_document_blob")
    def test_purge_deletes_in_foreign_key_order_and_retains_anonymous_receipt(
        self, delete_blob
    ):
        deletion = request_deletion(self.user, "correct-password")
        self.run.refresh_from_db()
        self.authorization.refresh_from_db()
        self.assertEqual(self.run.status, "cancelled")
        self.assertIsNotNone(self.authorization.revoked_at)
        self.assertEqual(purge_account(deletion.pk), "completed")
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.other.pk).exists())
        self.assertFalse(m.Application.objects.exists())
        self.assertFalse(m.Document.objects.exists())
        deletion.refresh_from_db()
        self.assertIsNone(deletion.user_id)
        self.assertIsNotNone(deletion.completed_at)
        self.assertEqual(purge_account(deletion.pk), "completed")
        delete_blob.assert_called_once()

    @patch("jobboard.services.documents.delete_document_blob")
    def test_failed_storage_purge_is_resumable(self, delete_blob):
        deletion = request_deletion(self.user, "correct-password")
        delete_blob.side_effect = OSError("secret-storage-path")
        self.assertEqual(purge_account(deletion.pk), "failed")
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, "deleting")
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())
        deletion.refresh_from_db()
        self.assertEqual(deletion.last_error_code, "purge_failed")
        delete_blob.side_effect = None
        self.assertEqual(purge_account(deletion.pk), "completed")

    @patch("jobboard.services.documents.delete_document_blob")
    def test_live_or_uncertain_runs_block_storage_deletion(self, delete_blob):
        self.run.status = "running"
        self.run.phase = "submitting"
        self.run.lease_expires_at = timezone.now() - timedelta(minutes=1)
        self.run.save()
        deletion = request_deletion(self.user, "correct-password")
        self.assertEqual(purge_account(deletion.pk), "pending")
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "running")
        self.run.status = "uncertain"
        self.run.save()
        self.assertEqual(purge_account(deletion.pk), "pending")
        delete_blob.assert_not_called()

    @patch("jobboard.services.documents.delete_document_blob")
    def test_active_preparation_waits_for_lease_but_expired_preparation_can_stop(
        self, delete_blob
    ):
        self.run.status = "running"
        self.run.lease_expires_at = timezone.now() + timedelta(minutes=1)
        self.run.save()
        deletion = request_deletion(self.user, "correct-password")
        self.assertEqual(purge_account(deletion.pk), "pending")
        delete_blob.assert_not_called()
        self.run.lease_expires_at = timezone.now() - timedelta(minutes=1)
        self.run.save()
        self.assertEqual(purge_account(deletion.pk), "completed")

    @override_settings(ROOT_URLCONF="jobboard.api.accounts")
    def test_api_requires_session_and_password_and_logs_out(self):
        self.assertEqual(self.client.get("/account/export/").status_code, 401)
        self.client.force_login(self.user)
        response = self.client.post(
            "/account/delete/",
            data=json.dumps({"password": "correct-password"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.client.get("/account/export/").status_code, 401)

    def test_export_is_withheld_if_account_is_disabled_during_storage_read(self):
        def disable(document):
            get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
            return b"%PDF-ok\n"

        with (
            patch("jobboard.services.documents.read_document", side_effect=disable),
            self.assertRaises(APIError) as error,
        ):
            export_account(self.user)
        self.assertEqual(error.exception.status, 401)

    @patch("jobboard.services.documents.delete_document_blob")
    def test_upload_in_flight_blocks_purge_until_writer_finishes(self, delete_blob):
        self.document.status = "pending"
        self.document.save(update_fields=["status"])
        deletion = request_deletion(self.user, "correct-password")
        self.assertEqual(purge_account(deletion.pk), "pending")
        delete_blob.assert_not_called()
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, "pending")
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())
        # Upload handler has returned from PUT and persisted its cleanup state.
        self.document.status = "deleting"
        self.document.save(update_fields=["status"])
        self.assertEqual(purge_account(deletion.pk), "completed")

    def test_recovery_requires_exact_old_documents_on_inactive_deleting_account(self):
        from jobboard.services.accounts import recover_stopped_uploads

        self.document.status = "pending"
        self.document.save(update_fields=["status"])
        with self.assertRaises(APIError):
            recover_stopped_uploads([self.document.pk])
        request_deletion(self.user, "correct-password")
        with self.assertRaises(APIError):
            recover_stopped_uploads([self.document.pk])
        m.Document.objects.filter(pk=self.document.pk).update(
            created_at=timezone.now() - timedelta(days=2)
        )
        self.assertEqual(recover_stopped_uploads([self.document.pk]), 1)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, "deleting")

    def test_recovery_command_requires_explicit_operator_confirmation(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("purge_accounts", recover_pending=[self.document.pk])
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, "ready")
