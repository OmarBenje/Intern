from django.test import TestCase

from jobboard import models as m
from jobboard.api.dashboard import application_rows, row_data
from jobboard.tests.test_workflow import WorkflowSetup


class DashboardTests(WorkflowSetup, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_authentication_and_account_isolation(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/v1/dashboard/").status_code, 401)
        self.client.force_login(self.other)
        data = self.client.get("/api/v1/dashboard/").json()
        self.assertEqual(data["applications"]["results"], [])
        self.assertEqual(data["counts"], {"applications": 0, "needs_input": 0})
        self.assertEqual(data["full_name"], "")

    def test_rows_show_real_offer_and_latest_documents_even_for_closed_offers(self):
        self.offer.status = "closed"
        self.offer.save()
        data = self.client.get("/api/v1/dashboard/").json()
        row = data["applications"]["results"][0]
        self.assertEqual(row["offer"]["title"], self.offer.title)
        self.assertEqual(row["offer"]["company"]["name"], self.offer.company.name)
        self.assertTrue(row["resume_ready"])
        self.assertFalse(row["cover_letter_ready"])
        self.assertIsNone(row["submitted_at"])
        self.assertEqual(data["offers"], [])
        self.document.status = "quarantined"
        self.document.save()
        self.assertFalse(
            self.client.get("/api/v1/dashboard/").json()["applications"]["results"][0][
                "resume_ready"
            ]
        )

    def test_filter_search_and_bounded_pagination(self):
        self.assertEqual(
            self.client.get("/api/v1/dashboard/?filter=needs_input").json()[
                "applications"
            ]["count"],
            1,
        )
        self.assertEqual(
            self.client.get("/api/v1/dashboard/?filter=active").json()["applications"][
                "count"
            ],
            0,
        )
        self.assertEqual(
            self.client.get("/api/v1/dashboard/?q=EXAMPLE").json()["applications"][
                "count"
            ],
            1,
        )
        self.assertEqual(
            self.client.get("/api/v1/dashboard/?q=no-match").json()["applications"][
                "count"
            ],
            0,
        )
        self.assertEqual(
            self.client.get("/api/v1/dashboard/?filter=invalid").status_code, 400
        )
        self.assertEqual(
            self.client.get("/api/v1/dashboard/?page_size=101").status_code, 400
        )
        self.assertEqual(
            self.client.get("/api/v1/dashboard/?q=" + "a" * 301).status_code, 400
        )

    def test_latest_run_is_used_and_recruitment_status_takes_precedence(self):
        run = m.AgentRun.objects.create(
            application=self.app,
            revision=self.revision,
            user=self.user,
            purpose="prepare",
            status="failed",
            attempt_no=1,
        )
        self.assertEqual(
            self.client.get("/api/v1/dashboard/?filter=failed").json()["applications"][
                "count"
            ],
            1,
        )
        run.status = "cancelled"
        run.save()
        m.AgentRun.objects.create(
            application=self.app,
            revision=self.revision,
            user=self.user,
            purpose="prepare",
            status="running",
            attempt_no=2,
        )
        data = self.client.get("/api/v1/dashboard/?filter=active").json()
        self.assertEqual(
            data["applications"]["results"][0]["workflow_status"], "running"
        )
        self.assertEqual(data["counts"]["needs_input"], 0)
        self.app.status = "withdrawn"
        self.app.save()
        self.assertEqual(
            self.client.get("/api/v1/dashboard/?filter=active").json()["applications"][
                "count"
            ],
            0,
        )
        self.assertEqual(
            self.client.get("/api/v1/dashboard/?filter=skipped").json()["applications"][
                "count"
            ],
            1,
        )

    def test_row_serialization_has_no_per_row_queries_or_mutations(self):
        with self.assertNumQueries(1):
            rows = [row_data(app) for app in application_rows(self.user)]
        self.assertEqual(len(rows), 1)
        before = (
            m.Application.objects.count(),
            m.AgentRun.objects.count(),
            m.SubmissionAuthorization.objects.count(),
        )
        self.client.get("/api/v1/dashboard/")
        self.assertEqual(
            before,
            (
                m.Application.objects.count(),
                m.AgentRun.objects.count(),
                m.SubmissionAuthorization.objects.count(),
            ),
        )
