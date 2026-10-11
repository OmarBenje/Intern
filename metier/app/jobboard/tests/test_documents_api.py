from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import include, path
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject

from jobboard.api.core import APIError
from jobboard.integrations.storage import read_object, write_object
from jobboard.models import (
    Application,
    ApplicationRevision,
    Company,
    Document,
    Offer,
    OfferSource,
    RevisionDocument,
    SourceBoard,
)
from jobboard.services.documents import delete_document, read_document

urlpatterns = [path("api/v1/", include("jobboard.api.profiles"))]


def pdf_bytes(active=False):
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    if active:
        writer.add_js('app.alert("test")')
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


@override_settings(
    ROOT_URLCONF=__name__,
    PRIVATE_STORAGE_BACKEND="local",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class DocumentAPITests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(
            PRIVATE_STORAGE_ROOT=self.directory.name
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = get_user_model().objects.create_user(
            username="alice", password="password"
        )
        self.other = get_user_model().objects.create_user(
            username="bob", password="password"
        )
        self.client.force_login(self.user)

    def upload(self, data=None):
        return self.client.post(
            "/api/v1/documents/",
            {
                "kind": "resume",
                "file": SimpleUploadedFile(
                    "cv.pdf", data or pdf_bytes(), content_type="application/pdf"
                ),
            },
        )

    def test_upload_download_private_and_referenced_deletion(self):
        data = pdf_bytes()
        response = self.upload(data)
        self.assertEqual(response.status_code, 200, response.content)
        pk = response.json()["id"]
        self.assertNotIn("object_key", response.json())
        response = self.client.get(f"/api/v1/documents/{pk}/download/")
        self.assertEqual(b"".join(response.streaming_content), data)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(
            self.client.put(
                "/api/v1/profile/resume/",
                {"document_id": pk},
                content_type="application/json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.delete(f"/api/v1/documents/{pk}/").status_code, 409
        )
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(f"/api/v1/documents/{pk}/download/").status_code, 404
        )
        self.assertEqual(
            self.client.delete(f"/api/v1/documents/{pk}/").status_code, 404
        )

    def test_bad_active_oversized_pdf(self):
        self.assertEqual(self.upload(b"not PDF").status_code, 400)
        self.assertEqual(self.upload(pdf_bytes(active=True)).status_code, 400)
        with override_settings(MAX_DOCUMENT_BYTES=20):
            self.assertEqual(self.upload().status_code, 413)
        self.assertEqual(Document.objects.count(), 0)

    def test_passive_opening_destination_is_accepted(self):
        for indirect in (False, True):
            with self.subTest(indirect=indirect):
                writer = PdfWriter()
                page = writer.add_blank_page(width=100, height=100)
                destination = ArrayObject([page.indirect_reference, NameObject("/Fit")])
                writer.root_object[NameObject("/OpenAction")] = (
                    writer._add_object(destination) if indirect else destination
                )
                stream = BytesIO()
                writer.write(stream)
                response = self.upload(stream.getvalue())
                self.assertEqual(response.status_code, 200, response.content)

    def test_opening_actions_and_malformed_destinations_are_rejected(self):
        for action in ("/JavaScript", "/Launch", "/URI", "/GoTo"):
            with self.subTest(action=action):
                writer = PdfWriter()
                writer.add_blank_page(width=100, height=100)
                writer.root_object[NameObject("/OpenAction")] = DictionaryObject(
                    {
                        NameObject("/S"): NameObject(action),
                    }
                )
                stream = BytesIO()
                writer.write(stream)
                self.assertEqual(self.upload(stream.getvalue()).status_code, 400)
        writer = PdfWriter()
        page = writer.add_blank_page(width=100, height=100)
        writer.root_object[NameObject("/OpenAction")] = ArrayObject(
            [
                page.indirect_reference,
                NameObject("/Fit"),
                TextStringObject("unexpected"),
            ]
        )
        stream = BytesIO()
        writer.write(stream)
        self.assertEqual(self.upload(stream.getvalue()).status_code, 400)

    def test_integrity_check_and_delete_storage(self):
        pk = self.upload().json()["id"]
        document = Document.objects.get(pk=pk)
        with (
            patch("jobboard.services.documents.read_object", return_value=b"changed"),
            self.assertRaises(APIError),
        ):
            read_document(document)
        self.assertEqual(
            self.client.delete(f"/api/v1/documents/{pk}/").status_code, 204
        )
        self.assertFalse(Document.objects.filter(pk=pk).exists())
        with self.assertRaises(FileNotFoundError):
            read_object(document.bucket, document.object_key)

    def test_failed_storage_retains_recoverable_deleting_row(self):
        with patch(
            "jobboard.services.documents.write_object",
            side_effect=OSError("unavailable"),
        ):
            self.assertEqual(self.upload().status_code, 503)
        document = Document.objects.get()
        self.assertEqual(document.status, "deleting")
        self.assertEqual(
            self.client.delete(f"/api/v1/documents/{document.pk}/").status_code, 204
        )

    def test_storage_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            write_object("local", "../outside.pdf", b"bad")

    def test_historical_resume_is_retained_after_replacement(self):
        old_id = self.upload().json()["id"]
        company = Company.objects.create(name="Example")
        offer = Offer.objects.create(
            company=company, title="Intern", description="Role"
        )
        board = SourceBoard.objects.create(
            provider="greenhouse", board_key="example", base_url="https://example.com"
        )
        source = OfferSource.objects.create(
            offer=offer,
            board=board,
            external_id="1",
            origin_url="https://example.com",
            apply_url="https://example.com",
            content_hash="a" * 64,
        )
        application = Application.objects.create(
            user=self.user, offer=offer, source=source
        )
        revision = ApplicationRevision.objects.create(
            application=application,
            user=self.user,
            revision_no=1,
            profile_snapshot={},
            offer_snapshot={},
            form_snapshot={},
        )
        RevisionDocument.objects.create(
            revision=revision, user=self.user, document_id=old_id, purpose="resume"
        )
        new_id = self.upload().json()["id"]
        self.client.put(
            "/api/v1/profile/resume/",
            {"document_id": new_id},
            content_type="application/json",
        )
        self.assertEqual(
            self.client.delete(f"/api/v1/documents/{old_id}/").status_code, 409
        )
        self.assertEqual(Document.objects.get(pk=old_id).status, "ready")

    @override_settings(PRIVATE_STORAGE_BACKEND="r2", R2_BUCKET="private-bucket")
    def test_r2_private_storage_contract(self):
        with patch("jobboard.integrations.storage._client") as factory:
            client = factory.return_value
            client.get_object.return_value = {"Body": BytesIO(pdf_bytes())}
            response = self.upload()
            self.assertEqual(response.status_code, 200, response.content)
            document = Document.objects.get(pk=response.json()["id"])
            request = client.put_object.call_args.kwargs
            self.assertEqual(request["Bucket"], "private-bucket")
            self.assertNotIn("ACL", request)
            self.assertEqual(read_document(document), pdf_bytes())
            self.assertEqual(
                self.client.delete(f"/api/v1/documents/{document.pk}/").status_code, 204
            )
            client.delete_object.assert_called_once_with(
                Bucket="private-bucket", Key=document.object_key
            )

    def test_pending_upload_cannot_be_deleted_during_write(self):
        from jobboard.integrations.storage import write_object as real_write

        def write_while_delete_attempted(bucket, key, data):
            document = Document.objects.get(object_key=key)
            self.assertEqual(document.status, "pending")
            with self.assertRaises(APIError) as rejected:
                delete_document(self.user, document.pk)
            self.assertEqual(rejected.exception.code, "upload_in_progress")
            self.assertTrue(Document.objects.filter(pk=document.pk).exists())
            real_write(bucket, key, data)

        with patch(
            "jobboard.services.documents.write_object",
            side_effect=write_while_delete_attempted,
        ):
            response = self.upload()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Document.objects.get().status, "ready")

    def test_upload_cleanup_can_finish_after_account_deactivation(self):
        from jobboard.integrations.storage import write_object as real_write

        def deactivate_after_write(bucket, key, data):
            real_write(bucket, key, data)
            get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)

        with patch(
            "jobboard.services.documents.write_object",
            side_effect=deactivate_after_write,
        ):
            response = self.upload()
        self.assertEqual(response.status_code, 403, response.content)
        document = Document.objects.get()
        self.assertEqual(document.status, "deleting")
        with self.assertRaises(FileNotFoundError):
            read_object(document.bucket, document.object_key)

    def test_failed_write_and_cleanup_keep_recovery_key(self):
        with (
            patch(
                "jobboard.services.documents.write_object",
                side_effect=OSError("failed"),
            ),
            patch(
                "jobboard.services.documents.delete_document_blob",
                side_effect=OSError("failed"),
            ),
            self.assertLogs("jobboard.services.documents", level="ERROR"),
        ):
            response = self.upload()
        self.assertEqual(response.status_code, 503, response.content)
        document = Document.objects.get()
        self.assertEqual(document.status, "deleting")
        self.assertTrue(document.object_key.endswith(".pdf"))
