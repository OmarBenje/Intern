"""Small adversarial regression corpus; not the 500-offer production acceptance set."""

from django.test import SimpleTestCase, TestCase

from jobboard.models import (
    Company,
    Location,
    Offer,
    OfferSource,
    SourceBoard,
    SourceRevision,
)
from jobboard.services.engine_quality import enrich_offer, extract_facts


class ExtractionCorpusTests(SimpleTestCase):
    def test_english_intern_role_needs_description_corroboration(self):
        self.assertEqual(
            extract_facts(
                "Intern Deal Operations and Analysis",
                "As a Deal Operations & Analysis Intern, you will manage provisioning.",
            )["classification"],
            "confirmed",
        )
        for title, description in [
            ("Intern Deal Operations", "We support internal operations."),
            ("Internal Auditor", "As an intern you may have learned audit."),
            ("Intern Softwareentwickler", "Diese Stelle wird intern besetzt."),
            ("Intern Analyst", "Experience as an analyst. Mentor an intern."),
        ]:
            with self.subTest(title=title):
                self.assertNotEqual(
                    extract_facts(title, description)["classification"], "confirmed"
                )

    def test_recruitment_events_override_internship_metadata(self):
        for title in [
            "Tax & Legal Talent Class 2026-2027",
            "Women in Tech Pilates - Deloitte Consulting Career Week",
            "Business Course: Future of Energy 2026",
        ]:
            with self.subTest(title=title):
                self.assertEqual(
                    extract_facts(
                        title, "Discover our internships", contract_type="internship"
                    )["classification"],
                    "not_internship",
                )
        self.assertEqual(
            extract_facts(
                "Event Management Internship",
                "Organise a career fair",
                contract_type="internship",
            )["classification"],
            "confirmed",
        )

    def test_explicit_multilingual_internship_forms(self):
        for title in [
            "Pflichtpraktikum im Bereich Marketing",
            "Freiwilliges Praktikum Softwareentwicklung",
            "Stagista ufficio acquisti",
            "Tirocinante risorse umane",
        ]:
            with self.subTest(title=title):
                self.assertEqual(
                    extract_facts(title, "")["classification"], "confirmed"
                )

    def test_french_stage_title_needs_explicit_context(self):
        for description, evidence in [
            ("Au cours de ce stage, vous rejoindrez notre équipe.", "ce stage"),
            ("Votre stage se déroulera dans notre laboratoire.", "Votre stage"),
            ("Une convention de stage est nécessaire.", "convention de stage"),
            ("Nous proposons un stage de 6 mois.", "stage de 6 mois"),
            ("Il s’agit d’un stage de 4 à 6 mois.", "stage de 4 à 6 mois"),
        ]:
            with self.subTest(description=description):
                result = extract_facts("Stage - Assistant achats", description)
                self.assertEqual(result["classification"], "confirmed")
                self.assertEqual(
                    result["facts"]["classification"]["evidence_text"], evidence
                )
        for title in ["Stage production assistant", "Internal auditor"]:
            with self.subTest(title=title):
                self.assertEqual(
                    extract_facts(title, "Join our production team.")["classification"],
                    "uncertain",
                )
        # A description mentioning internships is insufficient without a title
        # signal or structured internship contract. Negative titles still win.
        self.assertEqual(
            extract_facts(
                "Assistant achats", "Une convention de stage est nécessaire."
            )["classification"],
            "uncertain",
        )
        for title in ["Stage Manager", "Working Student Stage", "Stage en alternance"]:
            with self.subTest(title=title):
                self.assertEqual(
                    extract_facts(title, "Votre stage dure 6 mois.")["classification"],
                    "not_internship",
                )

    def test_multilingual_positive_and_false_friends(self):
        cases = [
            ("Software internship", "confirmed"),
            ("Stagiaire marketing", "confirmed"),
            ("Praktikum Maschinenbau", "confirmed"),
            ("Prácticas de finanzas", "confirmed"),
            ("Tirocinio legale", "confirmed"),
            ("Estágio de design", "confirmed"),
            ("Staż w logistyce", "confirmed"),
            ("Stagiair marketing", "confirmed"),
            ("Director of internship programmes", "not_internship"),
            ("Responsable des stages", "not_internship"),
            ("Internship Program Manager", "not_internship"),
            ("Stage lighting technician", "not_internship"),
            ("Graduate trainee", "uncertain"),
            ("Werkstudent", "not_internship"),
            ("Software engineer", "uncertain"),
        ]
        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(extract_facts(title, "")["classification"], expected)

    def test_apprenticeship_titles_override_internship_ats_category(self):
        for title in [
            "Apprenticeships at CERN",
            "Engineering Apprentice",
            "Apprentissage en informatique",
            "Marketing en alternance",
            "Ausbildung Fachinformatiker",
            "Duales Studium Informatik",
        ]:
            with self.subTest(title=title):
                projection = extract_facts(
                    title, "Training programme.", contract_type="internship"
                )
                self.assertEqual(projection["classification"], "not_internship")
                self.assertEqual(
                    projection["facts"]["classification"]["evidence_text"], title
                )

    def test_internship_with_historical_apprenticeship_description_stays_confirmed(
        self,
    ):
        projection = extract_facts(
            "Software Engineering Internship",
            "We have offered apprenticeships and Ausbildung since 2010. This internship is six months.",
            contract_type="internship",
        )
        self.assertEqual(projection["classification"], "confirmed")

    def test_bosch_real_mislabelled_intern_titles(self):
        # BoschGroup public SmartRecruiters summaries, observed during this task.
        # Each of these listings carries typeOfEmployment.id == "intern".
        cases = [
            ("744000152220817", "Working Student Electrical Calibration"),
            ("744000150305534", "Working Student in Sales Planning"),
            ("744000143555199", "Working Student Mechanical Field"),
            ("744000149873136", "Apprenti(e) Magasinier(ière) H/F/N"),
            ("744000146731277", "Apprenti(e) chef(fe) de projet H/F/N"),
            ("744000133901519", "PhD Scholarship in Software and Hardware"),
        ]
        for source_id, title in cases:
            with self.subTest(source_id=source_id):
                self.assertEqual(
                    extract_facts(title, "", contract_type="internship")[
                        "classification"
                    ],
                    "not_internship",
                )

    def test_student_employment_and_graduate_programme_are_not_internships(self):
        for title in [
            "Werkstudent Software",
            "Student Job in Sales",
            "Graduate Programme Engineering",
        ]:
            with self.subTest(title=title):
                self.assertEqual(
                    extract_facts(title, "", contract_type="internship")[
                        "classification"
                    ],
                    "not_internship",
                )

    def test_thesis_and_generic_student_role_need_verification(self):
        for title in [
            "Master Thesis Robotics",
            "Abschlussarbeit Robotik",
            "HR Generalist – Student Position (Romanian speaker)",
            "hbo-afstudeeropdracht: ontwerp remote beheer- en monitoringsoplossing",
        ]:
            with self.subTest(title=title):
                self.assertEqual(
                    extract_facts(title, "", contract_type="internship")[
                        "classification"
                    ],
                    "uncertain",
                )
        for title in [
            "Internship Thesis Robotics",
            "Praktikum und Abschlussarbeit Robotik",
        ]:
            with self.subTest(title=title):
                self.assertEqual(
                    extract_facts(title, "", contract_type="internship")[
                        "classification"
                    ],
                    "confirmed",
                )

    def test_duration_range_units_and_missing(self):
        for text, minimum, maximum, unit in [
            ("Durée : 4 à 6 mois.", 4, 6, "months"),
            ("Dauer: 3-6 Monate.", 3, 6, "months"),
            ("A 12-week internship.", 12, 12, "weeks"),
            ("Duración: 6 meses.", 6, 6, "months"),
            ("Durata: 3 mesi.", 3, 3, "months"),
            ("Duur: 6 maanden.", 6, 6, "months"),
            ("Czas trwania: 3 miesiące.", 3, 3, "months"),
            ("Duração: 6 meses.", 6, 6, "months"),
        ]:
            with self.subTest(text=text):
                fact = extract_facts("Internship", text)["facts"]["duration"]
                self.assertEqual(
                    (
                        fact["value"]["minimum"],
                        fact["value"]["maximum"],
                        fact["value"]["unit"],
                    ),
                    (minimum, maximum, unit),
                )
                self.assertIn(fact["evidence_text"], text)
        self.assertNotIn(
            "duration",
            extract_facts(
                "Internship", "Three years of experience. 6 months of Python."
            )["facts"],
        )
        preferred = extract_facts("Internship", "Duration: 6 months preferred.")[
            "facts"
        ]["duration"]
        self.assertFalse(preferred["required"])

    def test_country_ambiguity_remote_and_multilocation(self):
        for locations, work_mode, expected in [
            ([{"name": "Paris, France"}], "onsite", "in_scope"),
            ([{"name": "Cambridge"}], "onsite", "unknown"),
            ([{"name": "London", "country_code": "GB"}], "remote", "unknown"),
            ([{"name": "US", "country_code": "US"}], "onsite", "out_of_scope"),
            (
                [{"name": "US", "country_code": "US"}, {"name": "France"}],
                "onsite",
                "in_scope",
            ),
            ([{"name": "Russia", "country_code": "RU"}], "onsite", "unknown"),
        ]:
            with self.subTest(locations=locations, work_mode=work_mode):
                self.assertEqual(
                    extract_facts(
                        "Internship", "", locations=locations, work_mode=work_mode
                    )["europe_status"],
                    expected,
                )

    def test_no_language_or_sponsorship_inference(self):
        facts = extract_facts(
            "Internship", "This description is written in English. French preferred."
        )["facts"]
        self.assertNotIn("required_languages", facts)
        self.assertNotIn("sponsorship_available", facts)
        required = extract_facts(
            "Internship", "French required. German is not required."
        )["facts"]["required_languages"]
        self.assertEqual([x["code"] for x in required["value"]], ["fr"])
        facts = extract_facts("Internship", "Visa sponsorship is not available.")[
            "facts"
        ]
        self.assertIs(facts["sponsorship_available"]["value"], False)

    def test_preferred_start_does_not_exclude_candidate(self):
        from types import SimpleNamespace

        from jobboard.services.engine_matching import evaluate_match

        for description in [
            "Preferred start date: 2027-05-01.",
            "Start: 2027-05-01, flexible.",
            "Début: 2027-05-01 à titre indicatif.",
        ]:
            with self.subTest(description=description):
                projection = extract_facts("Internship", description)
                fact = projection["facts"]["start_date"]
                fact["source_revision_id"] = 1
                self.assertFalse(fact["required"])
                offer = SimpleNamespace(
                    status="open",
                    enrichment=SimpleNamespace(
                        **projection,
                        content_version=1,
                        extractor_version="rules-2",
                    ),
                )
                match = evaluate_match(offer, {"available_from": "2027-06-01"})
                self.assertEqual(match["compatibility"], "needs_verification")
                self.assertIn("start_date", match["unknown_fields"])

    def test_no_fabricated_dates(self):
        for description in ["Start: summer 2027", "Start: 2027-02-31"]:
            self.assertNotIn(
                "start_date", extract_facts("Internship", description)["facts"]
            )
        self.assertEqual(
            extract_facts("Internship", "Start: 2027-05-01")["facts"]["start_date"][
                "value"
            ],
            "2027-05-01",
        )


class PersistedQualityTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Example")
        self.offer = Offer.objects.create(
            company=self.company,
            title="Marketing internship",
            description="Duration: 6 months. Start: 2027-05-01.",
        )
        self.offer.locations.add(
            Location.objects.create(name="Paris, France", canonical_key="quality-fr")
        )
        self.board = SourceBoard.objects.create(
            company=self.company,
            provider="greenhouse",
            board_key="quality",
            base_url="https://example.com",
        )
        self.source = OfferSource.objects.create(
            offer=self.offer,
            board=self.board,
            external_id="1",
            origin_url="https://example.com/1",
            apply_url="https://example.com/1",
            content_hash="a" * 64,
        )
        self.revision = SourceRevision.objects.create(
            source=self.source,
            raw_hash="a" * 64,
            semantic_hash="b" * 64,
            payload={"title": self.offer.title, "description": self.offer.description},
        )

    def test_idempotent_and_preserves_revision_evidence(self):
        first = enrich_offer(self.offer)
        self.assertEqual(first.content_version, 1)
        self.assertEqual(
            first.facts["duration"]["source_revision_id"], self.revision.pk
        )
        second = enrich_offer(self.offer)
        self.assertEqual(second.content_version, 1)
        self.offer.description = "Duration: 4 months."
        self.offer.save()
        third = enrich_offer(self.offer)
        self.assertEqual(third.content_version, 2)
        self.assertIsNone(third.facts["duration"]["source_revision_id"])
        self.revision.refresh_from_db()
        self.assertIn("6 months", self.revision.payload["description"])

    def test_formatting_is_not_a_new_semantic_version(self):
        enrich_offer(self.offer)
        self.offer.title = "MARKETING  INTERNSHIP"
        self.offer.description = "<p>Duration: 6 months. Start: 2027-05-01.</p>"
        self.offer.save()
        self.assertEqual(enrich_offer(self.offer).content_version, 1)


class PublicationPolicyTests(TestCase):
    def test_reenrichment_publishes_only_confirmed_european_internships(self):
        from io import StringIO

        from django.core.management import call_command

        from jobboard.services.engine_quality import published_offers

        company = Company.objects.create(name="Publication policy")
        france = Location.objects.create(
            name="Paris, France", country_code="FR", canonical_key="policy-fr"
        )
        usa = Location.objects.create(
            name="New York, USA", country_code="US", canonical_key="policy-us"
        )
        cases = [
            ("Marketing internship", france),
            ("Director of marketing", france),
            ("Marketing internship", usa),
            ("Marketing internship", None),
            ("Graduate trainee", france),
        ]
        offers = []
        for title, location in cases:
            offer = Offer.objects.create(company=company, title=title)
            if location:
                offer.locations.add(location)
            offers.append(offer)
        output = StringIO()
        call_command("re_enrich_catalogue", limit=1, stdout=output)
        self.assertIn("Processed 1 offers", output.getvalue())
        self.assertEqual(
            list(published_offers(Offer.objects.all()).values_list("pk", flat=True)),
            [offers[0].pk],
        )
        call_command("re_enrich_catalogue", all=True, limit=2, stdout=StringIO())
        self.assertEqual(
            list(published_offers(Offer.objects.all()).values_list("pk", flat=True)),
            [offers[0].pk],
        )
        self.assertEqual(Offer.objects.filter(status="open").count(), 5)
        self.assertEqual(Offer.objects.count(), 5)
        self.assertEqual(offers[0].enrichment.content_version, 1)
