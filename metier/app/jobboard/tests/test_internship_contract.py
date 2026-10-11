import json
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from jobboard.services.engine_quality import extract_facts


class ContractReviewTests(SimpleTestCase):
    def classify(self, title, description="", contract="internship"):
        return extract_facts(title, description, contract_type=contract)

    def test_source_label_alone_is_not_enough(self):
        result = self.classify(
            "Customer Service Specialist",
            "Previous experience in an internship is welcome.",
        )
        self.assertEqual(result["classification"], "uncertain")
        self.assertEqual(
            result["facts"]["classification"]["reason"], "uncorroborated_ats_contract"
        )

    def test_explicit_contract_conflicts(self):
        for title, text, expected in [
            (
                "Développeur Python",
                "Type de contrat : CDI\n4 ans minimum",
                "not_internship",
            ),
            ("HRIS Consultant", "Een contract van onbepaalde duur.", "not_internship"),
            (
                "Software Internship",
                "This internship. Permanent contract.",
                "uncertain",
            ),
            ("Stage marketing", "Contrat CDI", "uncertain"),
        ]:
            with self.subTest(title=title):
                result = self.classify(title, text)
                self.assertEqual(result["classification"], expected)
                self.assertEqual(
                    result["facts"]["classification"]["reason"], "contract_conflict"
                )

    def test_conversion_and_other_employees_do_not_conflict(self):
        for description in [
            "Ce stage offre des opportunités de CDI à la clé.",
            "Après le stage, possibilité d'embauche en CDI.",
            "Assurer le suivi des collaborateurs en CDD.",
            "This internship may lead to a permanent position after graduation.",
        ]:
            with self.subTest(description=description):
                self.assertEqual(
                    self.classify("Stage RH", description)["classification"],
                    "confirmed",
                )

    def test_roles_and_event_exclusions(self):
        for title in [
            "_Alternant Conseiller",
            "Red Bull Student Marketeer",
            "YFN X EU Hackaton",
        ]:
            self.assertEqual(self.classify(title)["classification"], "not_internship")
        self.assertEqual(
            self.classify("Hackathon Operations Internship")["classification"],
            "confirmed",
        )

    def test_mixed_contract_title_is_uncertain(self):
        result = self.classify("Software Engineer - Stagiaire/Alternant")
        self.assertEqual(result["classification"], "uncertain")
        self.assertEqual(
            result["facts"]["classification"]["reason"], "mixed_contract_title"
        )

    def test_hungarian_title_remains_corroborated(self):
        self.assertEqual(
            self.classify("Logisztikai gyakornok")["classification"], "confirmed"
        )

    def test_real_lot27_regression_corpus(self):
        cases = json.loads(
            (
                Path(__file__).parent / "fixtures/internship_contract_cases.json"
            ).read_text()
        )
        for case in cases:
            with self.subTest(id=case["id"], title=case["title"]):
                classification = self.classify(
                    case["title"], case["description"], case["contract_type"]
                )["classification"]
                if case["expected"] == "not_confirmed":
                    self.assertNotEqual(classification, "confirmed")
                else:
                    self.assertEqual(classification, case["expected"])


class ContractAuditTests(TestCase):
    def test_preview_does_not_mutate_and_apply_preserves_lifecycle(self):
        import tempfile
        from io import StringIO

        from django.core.management import call_command

        from jobboard.models import Company, Offer
        from jobboard.tests.engine_fixtures import publishable

        offer = publishable(
            Offer.objects.create(
                company=Company.objects.create(name="Audit"),
                title="Customer Service Specialist",
                description="Support our customers.",
                contract_type="internship",
            )
        )
        offer.enrichment.classification = "confirmed"
        offer.enrichment.save()
        with tempfile.TemporaryDirectory() as directory:
            call_command(
                "audit_internship_contracts",
                report=f"{directory}/preview.json",
                stdout=StringIO(),
            )
            offer.enrichment.refresh_from_db()
            self.assertEqual(offer.enrichment.classification, "confirmed")
            call_command(
                "audit_internship_contracts",
                apply=True,
                report=f"{directory}/applied.json",
                stdout=StringIO(),
            )
            offer.refresh_from_db()
            self.assertEqual(offer.status, "open")
            self.assertEqual(offer.enrichment.classification, "uncertain")
            self.assertEqual(
                offer.enrichment.facts["classification"]["reason"],
                "uncorroborated_ats_contract",
            )
            self.assertEqual(
                json.loads(Path(f"{directory}/applied.json").read_text())[
                    "removed_visible_ids"
                ],
                [offer.pk],
            )
