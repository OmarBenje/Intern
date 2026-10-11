from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from jobboard.models import ApplicationRevision, CandidateProfile, Document


class PrivateAdminTests(TestCase):
    def test_regular_staff_cannot_browse_candidate_documents(self):
        from django.contrib.auth.models import Permission

        staff = get_user_model().objects.create_user(username="staff", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="view_document"))
        self.client.force_login(staff)
        response = self.client.get(reverse("admin:jobboard_document_changelist"))
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_inspect_but_cannot_edit_private_records(self):
        user = get_user_model().objects.create_superuser(
            username="super", email="super@example.com", password="test-only"
        )
        profile = CandidateProfile.objects.create(user=user, full_name="Original")
        self.client.force_login(user)
        detail = reverse("admin:jobboard_candidateprofile_change", args=[profile.pk])
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(
            self.client.post(detail, {"full_name": "Changed"}).status_code, 403
        )
        profile.refresh_from_db()
        self.assertEqual(profile.full_name, "Original")

    def test_superuser_can_open_catalogue_and_private_lists(self):
        user = get_user_model().objects.create_superuser(
            username="super", email="super@example.com", password="test-only"
        )
        self.client.force_login(user)
        for model in (Document, ApplicationRevision):
            with self.subTest(model=model.__name__):
                self.assertEqual(
                    self.client.get(
                        reverse(f"admin:jobboard_{model._meta.model_name}_changelist")
                    ).status_code,
                    200,
                )
        self.assertEqual(
            self.client.get(reverse("admin:jobboard_offer_add")).status_code, 200
        )
