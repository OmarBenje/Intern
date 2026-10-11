"""Adversarial source/precision regressions, not a catalogue-wide accuracy score."""

from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from jobboard.models import (
    Company,
    Location,
    Offer,
    OfferSource,
    SourceBoard,
    SourceRevision,
)
from jobboard.services.engine_filters import filter_catalogue
from jobboard.services.engine_matching import evaluate_match
from jobboard.services.engine_quality import enrich_offer, extract_facts, semantic_hash
from jobboard.services.offer_content import block_texts, build_content, html_blocks
from jobboard.services.stage_details import merge_structured, structured_facts


class ContentParsingTests(SimpleTestCase):
    def test_html_structure_order_nested_lists_and_bold_headings(self):
        blocks = html_blocks(
            '<p><strong>About the role</strong></p><p>A &amp; B</p><h2>Requirements</h2><ul><li>Python or Java<ol><li>One project</li></ol></li><li>English required</li></ul><script>throw Error("unsafe")</script><style>body{display:none}</style>'
        )
        self.assertEqual(
            [block["kind"] for block in blocks],
            ["heading", "paragraph", "heading", "bullet_list"],
        )
        self.assertEqual(blocks[1]["text"], "A & B")
        self.assertEqual(blocks[-1]["items"][0]["children"][0]["kind"], "ordered_list")
        self.assertEqual(
            list(block_texts(blocks[-1])),
            ["Python or Java", "One project", "English required"],
        )

    def test_source_selection_requires_current_text_not_just_latest_revision(self):
        current = "Requirements\nPython or Java\nEnglish required"
        old = SimpleNamespace(
            pk=1,
            payload={
                "content": "<h2>Requirements</h2><ul><li>Python or Java</li><li>English required</li></ul>"
            },
        )
        divergent = SimpleNamespace(
            pk=2,
            payload={"content": "<h2>Requirements</h2><p>Ten years of experience</p>"},
        )
        content, _ = build_content(current, [divergent, old])
        self.assertEqual(content["source_revision_id"], 1)
        self.assertEqual(content["blocks"][1]["kind"], "bullet_list")
        fallback, _ = build_content("Different current description", [old])
        self.assertIsNone(fallback["source_revision_id"])
        self.assertEqual(fallback["blocks"][0]["text"], "Different current description")

    def test_lever_lists_and_unclassified_sections_are_retained(self):
        payload = {
            "description": "<h2>About the role</h2><p>Build tools</p>",
            "descriptionPlain": "About the role\nBuild tools",
            "lists": [
                {
                    "text": "Requirements",
                    "content": "<li>Python or Java</li><li>React preferred</li><li>French not required</li>",
                }
            ],
            "additionalPlain": "Original footer",
        }
        current = "About the role\nBuild tools\nRequirements\nPython or Java\nReact preferred\nFrench not required\nOriginal footer"
        content, _ = build_content(current, [SimpleNamespace(pk=3, payload=payload)])
        self.assertEqual(content["source_revision_id"], 3)
        requirements = content["requirements"]
        self.assertTrue(requirements[0]["alternative"])
        self.assertEqual(
            [r["modality"] for r in requirements[:3]],
            ["required", "preferred", "optional"],
        )
        self.assertIn(
            "Original footer",
            [text for block in content["blocks"] for text in block_texts(block)],
        )

    def test_workday_html_is_found_only_at_known_path(self):
        revision = SimpleNamespace(
            pk=4,
            payload={
                "jobPostingInfo": {
                    "jobDescription": "<h2>Vos missions</h2><ul><li>Tester</li></ul>"
                }
            },
        )
        content, _ = build_content("Vos missions\nTester", [revision])
        self.assertEqual(content["sections"][0]["kind"], "responsibilities")
        self.assertEqual(content["source_revision_id"], 4)

    def test_negation_does_not_hide_a_required_clause(self):
        content, _ = build_content(
            "Requirements\nEnglish required, French not required.\nNo experience required."
        )
        self.assertEqual(
            [item["modality"] for item in content["requirements"]],
            ["mixed"],
        )
        optional, _ = build_content("Requirements\nNo experience required.")
        self.assertEqual(optional["requirements"][0]["modality"], "optional")

    def test_technology_punctuation_does_not_match_a_divergent_revision(self):
        content, _ = build_content(
            "Requirements\nC++ required",
            [
                SimpleNamespace(
                    pk=9, payload={"content": "<h2>Requirements</h2><p>C required</p>"}
                )
            ],
        )
        self.assertIsNone(content["source_revision_id"])


class StagePrecisionTests(SimpleTestCase):
    def facts(self, text):
        return extract_facts("Software engineering internship", text)["facts"]

    def test_weekly_attendance_is_not_internship_duration(self):
        for text in [
            "Hybrid with an availability to be on site 1-2 days per week-Warsaw",
            "Availability of minimum 2 days per week to work on sight, in our Warsaw office",
            "Internship requires at least 3 days a week in the office.",
            "Stage : minimum 2 jours par semaine en présentiel.",
            "Stage : 2 jours/semaine sur site.",
            "Praktikum: mindestens 2 Tage pro Woche im Büro.",
            "Internship: at least 2 days on site each week.",
        ]:
            with self.subTest(text=text):
                facts = self.facts(text)
                self.assertNotIn("duration", facts)
                self.assertNotIn("preferred_duration", facts)

    def test_attendance_does_not_conflict_with_real_duration(self):
        for text in [
            "Internship duration: 6 months, minimum 2 days per week on site.",
            "Stage de 6 mois, avec au moins 2 jours par semaine sur site.",
            "Internship: 6 months; ideally 3 days a week in the office.",
        ]:
            with self.subTest(text=text):
                facts = self.facts(text)
                self.assertEqual(facts["duration"]["status"], "explicit")
                self.assertEqual(facts["duration"]["value"]["minimum"], 6)
                self.assertEqual(facts["duration"]["value"]["unit"], "months")
                self.assertNotIn("preferred_duration", facts)

    def test_short_explicit_internship_durations_are_preserved(self):
        for text, unit in [
            ("Internship duration: 10 days.", "days"),
            ("Durée du stage : 3 semaines.", "weeks"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(self.facts(text)["duration"]["value"]["unit"], unit)

    def test_elided_french_start_preserves_month_and_source_wording(self):
        for phrase in [
            "à partir d'octobre 2026",
            "à partir d’octobre 2026",
            "A partir d' avril 2027",
        ]:
            with self.subTest(phrase=phrase):
                facts = self.facts(
                    f"Rejoignez notre équipe pour un stage de 6 mois {phrase}."
                )
                self.assertIn("start_period", facts)
                start = facts["start_period"]
                self.assertEqual(
                    start["value"],
                    {
                        "precision": "month",
                        "value": "2027-04" if "avril" in phrase else "2026-10",
                        "relation": "from",
                    },
                )
                self.assertEqual(start["evidence_text"], phrase)
                self.assertNotIn("start_date", facts)

    def test_named_dates_partial_periods_ambiguity_and_invalid_days(self):
        for text, field, expected in [
            ("Starting June 2, 2027", "start_date", "2027-06-02"),
            ("Début : 2 juin 2027", "start_date", "2027-06-02"),
            ("Beginn: Juni 2027", "start_period", "2027-06"),
            ("À partir de mai 2027", "start_period", "2027-05"),
            ("Start: Summer 2027", "start_period", "summer"),
            ("Start: 02/03/2027", "start_period", "02/03/2027"),
        ]:
            with self.subTest(text=text):
                facts = self.facts(text)
                value = facts[field]["value"]
                self.assertEqual(
                    value.get("value") if isinstance(value, dict) else value, expected
                )
                if field == "start_period":
                    self.assertNotIn("start_date", facts)
        self.assertNotIn("start_date", self.facts("Start: February 31, 2027"))
        self.assertEqual(
            self.facts("Starting ASAP")["start_period"]["value"]["precision"],
            "immediate",
        )

    def test_minimum_preferred_and_upper_bounds_do_not_conflate(self):
        facts = self.facts("Minimum 3 months, ideally 6 months. Start date flexible.")
        self.assertEqual(facts["duration"]["value"]["minimum"], 3)
        self.assertIsNone(facts["duration"]["value"]["maximum"])
        self.assertTrue(facts["duration"]["required"])
        self.assertFalse(facts["preferred_duration"]["required"])
        self.assertEqual(facts["preferred_duration"]["value"]["minimum"], 6)
        self.assertIsNone(
            self.facts("Duration: up to 6 months")["duration"]["value"]["minimum"]
        )
        self.assertNotIn(
            "duration", self.facts("Minimum 6 months of experience with Python.")
        )
        bounded = self.facts("Duration: minimum 3 months, maximum 6 months.")
        self.assertEqual(bounded["duration"]["value"]["minimum"], 3)
        self.assertEqual(bounded["duration"]["value"]["maximum"], 6)
        self.assertFalse(
            self.facts("Preferred duration: 6 months")["duration"]["required"]
        )
        self.assertEqual(
            self.facts("Duration: 3 months with possible extension of 6 months")[
                "duration"
            ]["value"]["minimum"],
            3,
        )

    def test_actual_french_month_window_and_exact_program_range(self):
        facts = self.facts("A partir de : janvier à mars 2027")
        self.assertEqual(
            facts["start_period"]["value"],
            {"precision": "month_range", "earliest": "2027-01", "latest": "2027-03"},
        )
        self.assertNotIn("start_date", facts)
        facts = self.facts("The internship runs from June 2, 2027 to August 11, 2027.")
        self.assertEqual(facts["start_date"]["value"], "2027-06-02")
        self.assertEqual(facts["end_date"]["value"]["value"], "2027-08-11")
        self.assertEqual(facts["duration"]["value"]["unit"], "days")
        self.assertNotIn(
            "start_date",
            self.facts(
                "The internship application window is from June 2, 2027 to August 11, 2027."
            ),
        )

    def test_conflicts_are_not_matching_rejections(self):
        facts = self.facts(
            "Duration: 3 months. Duration: 6 months. Start: 2027-05-01. Start: 2027-06-01."
        )
        self.assertEqual(facts["duration"]["status"], "conflict")
        self.assertEqual(facts["start_period"]["status"], "conflict")
        self.assertNotIn("start_date", facts)
        offer = SimpleNamespace(
            status="open",
            enrichment=SimpleNamespace(
                facts=facts,
                classification="confirmed",
                europe_status="in_scope",
                country_codes=["FR"],
                content_version=1,
                extractor_version="rules-9",
            ),
        )
        self.assertEqual(
            evaluate_match(offer, {}, {"duration_max_months": 4})["compatibility"],
            "needs_verification",
        )

    def test_deadline_and_required_language_are_not_lost(self):
        facts = self.facts(
            "Applications close February 15, 2027 at 23:59 ET. English fluent, French preferred."
        )
        self.assertNotIn("start_date", facts)
        self.assertEqual(facts["application_deadline"]["value"]["value"], "2027-02-15")
        self.assertIn("ET", facts["application_deadline"]["value"]["time_text"])
        self.assertEqual(
            [value["code"] for value in facts["required_languages"]["value"]], ["en"]
        )

    def test_native_language_and_preference_are_separate(self):
        facts = self.facts(
            "French native speaker, fluent in English, and German skills are a plus"
        )
        self.assertEqual(
            [item["code"] for item in facts["required_languages"]["value"]],
            ["fr", "en"],
        )
        self.assertEqual(
            [item["code"] for item in facts["preferred_languages"]["value"]], ["de"]
        )
        self.assertFalse(facts["preferred_languages"]["required"])

    def test_language_groups_and_mixed_conjunctions_keep_their_modality(self):
        for text, required, preferred in [
            ("French required and German preferred", ["fr"], ["de"]),
            ("Fluent in English and French. German is a plus.", ["en", "fr"], ["de"]),
            (
                "English required, French appreciated and German preferred",
                ["en"],
                ["fr", "de"],
            ),
            ("French required and German not required", ["fr"], []),
            ("We publish content in French and German. English documentation.", [], []),
        ]:
            with self.subTest(text=text):
                facts = self.facts(text)
                self.assertEqual(
                    [
                        item["code"]
                        for item in facts.get("required_languages", {}).get("value", [])
                    ],
                    required,
                )
                self.assertEqual(
                    [
                        item["code"]
                        for item in facts.get("preferred_languages", {}).get(
                            "value", []
                        )
                    ],
                    preferred,
                )

    def test_structured_dates_conflicts_and_duration_units(self):
        facts = self.facts("Start: 2027-05-01. Duration: 3 months.")
        incoming = structured_facts(
            {
                "jobStartDate": "2027-06-01",
                "jobDuration": "P6M",
                "publishedAt": "2026-10-01T12:00:00Z",
            },
            "rules-9",
        )
        merge_structured(facts, incoming, "rules-9")
        self.assertEqual(facts["start_date"]["status"], "conflict")
        self.assertEqual(facts["duration"]["status"], "conflict")
        self.assertEqual(facts["publication_date"]["json_path"], "publishedAt")

    def test_language_enumerations_alternatives_levels_and_conflicts(self):
        for text in [
            "English, French and German required",
            "Fluent in English, French and German",
        ]:
            with self.subTest(text=text):
                facts = self.facts(text)
                self.assertEqual(
                    [item["code"] for item in facts["required_languages"]["value"]],
                    ["en", "fr", "de"],
                )
        alternative = self.facts("French or German required")
        self.assertNotIn("required_languages", alternative)
        self.assertEqual(
            alternative["language_alternatives"]["value"][0]["codes"], ["fr", "de"]
        )
        conflict = self.facts(
            "French required. French is not required. English required."
        )
        self.assertEqual(conflict["language_conflicts"]["value"], ["fr"])
        self.assertEqual(
            [item["code"] for item in conflict["required_languages"]["value"]], ["en"]
        )
        level = self.facts(
            "English B2. Swedish language documentation. You must polish your code."
        )
        self.assertNotIn("required_languages", level)
        self.assertEqual(level["language_requirements"]["value"][0]["level_text"], "B2")
        native = self.facts(
            "Native French speaker. Fließende Deutschkenntnisse erforderlich. Anglais souhaité."
        )
        self.assertEqual(
            [item["code"] for item in native["required_languages"]["value"]],
            ["fr", "de"],
        )
        self.assertEqual(
            [item["code"] for item in native["preferred_languages"]["value"]], ["en"]
        )
        dedup = self.facts("English required. English fluent. English preferred.")
        self.assertEqual(len(dedup["required_languages"]["value"]), 1)
        self.assertNotIn("preferred_languages", dedup)
        wrapped = self.facts(
            "Professional fluency in\n \nEnglish and German (both written and spoken)"
        )
        self.assertEqual(
            [item["code"] for item in wrapped["required_languages"]["value"]],
            ["en", "de"],
        )
        nationality = self.facts(
            "We are a French company requiring fluent English. Native Japanese speaker. Mandarin Chinese preferred."
        )
        self.assertEqual(
            [item["code"] for item in nationality["required_languages"]["value"]],
            ["en", "ja"],
        )
        self.assertEqual(
            [item["code"] for item in nationality["preferred_languages"]["value"]],
            ["zh"],
        )
        for text, expected in [
            ("Speak\nfluent German\nand\nEnglish\n.", ["de", "en"]),
            ("Fluent\nin\nFrench\nand\nEnglish, Italian is a plus.", ["fr", "en"]),
            ("Parlez anglais couramment (C1/C2).", ["en"]),
            ("Parlez couramment anglais et français.", ["en", "fr"]),
            (
                "Spanish\n(spoken and written) must be flawless and fluent English will be necessary.",
                ["es", "en"],
            ),
        ]:
            with self.subTest(text=text):
                self.assertEqual(
                    [
                        item["code"]
                        for item in self.facts(text)["required_languages"]["value"]
                    ],
                    expected,
                )
        desired = self.facts("Fluent in Dutch OR French desired")
        self.assertNotIn("required_languages", desired)
        self.assertEqual(
            [item["code"] for item in desired["preferred_languages"]["value"]],
            ["nl", "fr"],
        )
        for text, expected in [
            ("Excellent verbal and written communication skills in English", ["en"]),
            (
                "Languages: very good in written and spoken English and German",
                ["en", "de"],
            ),
            ("Sehr gute Deutschkenntnisse und Englischkenntnisse", ["de", "en"]),
        ]:
            with self.subTest(text=text):
                self.assertEqual(
                    [
                        item["code"]
                        for item in self.facts(text)["required_languages"]["value"]
                    ],
                    expected,
                )


class ContentPersistenceTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name="Content example")
        self.offer = Offer.objects.create(
            company=company,
            title="Software engineering internship",
            description="About the role\nBuild tools\nRequirements\nPython or Java\nMinimum 3 months, ideally 6 months. Start from May 2027.",
        )
        self.offer.locations.add(
            Location.objects.create(
                name="Paris, France", country_code="FR", canonical_key="content-fr"
            )
        )
        board = SourceBoard.objects.create(
            company=company,
            provider="ashby",
            board_key="content",
            base_url="https://example.test",
        )
        self.source = OfferSource.objects.create(
            offer=self.offer,
            board=board,
            external_id="content",
            origin_url="https://example.test/content",
            apply_url="https://example.test/content",
            content_hash="a" * 64,
        )

    def revision(self, payload, raw_hash="a" * 64):
        return SourceRevision.objects.create(
            source=self.source,
            raw_hash=raw_hash,
            semantic_hash="b" * 64,
            payload=payload,
        )

    def test_backfill_idempotence_and_format_changes_without_semantic_change(self):
        revision = self.revision(
            {
                "descriptionHtml": "<h2>About the role</h2><p>Build tools</p><h2>Requirements</h2><ul><li>Python or Java</li><li>Minimum 3 months, ideally 6 months. Start from May 2027.</li></ul>"
            }
        )
        first = enrich_offer(self.offer)
        self.assertEqual(first.content["source_revision_id"], revision.pk)
        self.assertEqual(first.facts["duration"]["source_revision_id"], revision.pk)
        first_hash = first.content["input_hash"]
        self.assertEqual(enrich_offer(self.offer).content_version, 1)
        self.revision(
            {
                "descriptionHtml": "<h2>About the role</h2><p>Build tools</p><h2>Requirements</h2><p>Python or Java</p><p>Minimum 3 months, ideally 6 months. Start from May 2027.</p>"
            },
            raw_hash="c" * 64,
        )
        changed = enrich_offer(self.offer)
        self.assertEqual(changed.content_version, 1)
        self.assertNotEqual(changed.content["input_hash"], first_hash)
        revision.refresh_from_db()
        self.assertIn("<ul>", revision.payload["descriptionHtml"])

    def test_language_filters_and_matching_use_requirements_not_preferences(self):
        self.offer.description = (
            "French native speaker, fluent in English, and German skills are a plus"
        )
        self.offer.save()
        self.revision({"description": self.offer.description})
        enrichment = enrich_offer(self.offer)
        self.assertIsNotNone(
            enrichment.facts["required_languages"]["source_revision_id"]
        )
        qs = Offer.objects.filter(pk=self.offer.pk)
        for code, found in [("fr", True), ("en", True), ("de", False)]:
            self.assertEqual(
                filter_catalogue(
                    qs, {"required_language": code, "include_unknown": "false"}
                ).exists(),
                found,
            )
        match = evaluate_match(self.offer, {}, {"languages": ["fr", "en"]})
        self.assertNotIn("language_de", match["unknown_fields"])

    def test_language_alternatives_pass_filters_without_requiring_both(self):
        self.offer.description = "French or German required. English preferred."
        self.offer.save()
        self.revision({"description": self.offer.description})
        enrich_offer(self.offer)
        qs = Offer.objects.filter(pk=self.offer.pk)
        for code, found in [("fr", True), ("de", True), ("en", False)]:
            for policy in ["true", "false"]:
                self.assertEqual(
                    filter_catalogue(
                        qs, {"required_language": code, "include_unknown": policy}
                    ).exists(),
                    found,
                )
        match = evaluate_match(self.offer, {}, {"languages": ["fr"]})
        self.assertNotIn("language_alternative", match["unknown_fields"])
        self.assertIn("language_alternative_level", match["unknown_fields"])

    def test_wrapped_language_clauses_keep_revision_provenance(self):
        self.offer.description = "Fluent\nin\nFrench\nand\nEnglish. German preferred."
        self.offer.save()
        revision = self.revision({"description": self.offer.description})
        enrichment = enrich_offer(self.offer)
        for field in [
            "required_languages",
            "preferred_languages",
            "language_requirements",
        ]:
            self.assertEqual(enrichment.facts[field]["source_revision_id"], revision.pk)

    def test_conflicting_language_follows_unknown_filter_policy(self):
        self.offer.description = (
            "English required. French required. French is not required."
        )
        self.offer.save()
        self.revision({"description": self.offer.description})
        enrich_offer(self.offer)
        qs = Offer.objects.filter(pk=self.offer.pk)
        self.assertFalse(
            filter_catalogue(
                qs, {"required_language": "fr", "include_unknown": "false"}
            ).exists()
        )
        self.assertTrue(
            filter_catalogue(
                qs, {"required_language": "fr", "include_unknown": "true"}
            ).exists()
        )
        match = evaluate_match(self.offer, {}, {"languages": ["en", "fr"]})
        self.assertIn("language_conflicts", match["unknown_fields"])

    def test_structured_summary_profile_languages_have_decoded_source_proof(self):
        profile = "- French native speaker, fluent in English, and German skills are a plus\n- Interested in technology"
        self.offer.description = (
            "Résumé publié par Welcome to the Jungle\n\nJoin our team.\n\n" + profile
        )
        self.offer.save()
        revision = self.revision(
            {
                "description_kind": "search_summary",
                "summary": "Join our team.",
                "profile": profile,
                "key_missions": [],
            }
        )
        enrichment = enrich_offer(self.offer)
        for field in [
            "required_languages",
            "preferred_languages",
            "language_requirements",
        ]:
            self.assertEqual(enrichment.facts[field]["source_revision_id"], revision.pk)

    def test_language_modalities_do_not_bleed_across_source_blocks(self):
        for description in [
            "- English required\n- German preferred\n- French not required",
            "<ul><li>English required</li><li>German preferred</li><li>French not required</li></ul>",
        ]:
            with self.subTest(description=description):
                facts = extract_facts("Marketing Intern", description)["facts"]
                self.assertEqual(
                    [item["code"] for item in facts["required_languages"]["value"]],
                    ["en"],
                )
                self.assertEqual(
                    [item["code"] for item in facts["preferred_languages"]["value"]],
                    ["de"],
                )

    def test_language_evidence_preserves_bullet_scope(self):
        facts = extract_facts(
            "Marketing Intern",
            "- Able to thrive\n- French native speaker, fluent in English, and German skills are a plus\n- Interested in technology",
        )["facts"]
        self.assertEqual(
            facts["required_languages"]["value"][0]["evidence_text"],
            "- French native speaker",
        )
        self.assertEqual(
            facts["preferred_languages"]["value"][0]["evidence_text"],
            "and German skills are a plus",
        )

    def test_language_component_version_invalidates_a_legacy_cache(self):
        self.offer.description = (
            "French native speaker, fluent in English, German is a plus."
        )
        self.offer.save()
        self.revision({"description": self.offer.description})
        old = enrich_offer(self.offer)
        old.semantic_hash = semantic_hash(self.offer)
        old.facts = {}
        old.save()
        fresh = enrich_offer(self.offer)
        self.assertEqual(
            [item["code"] for item in fresh.facts["required_languages"]["value"]],
            ["fr", "en"],
        )
        self.assertEqual(
            fresh.facts["required_languages"]["language_rule_version"], "languages-2"
        )

    def test_language_block_scope_changes_invalidate_cache(self):
        self.offer.description = "English required\n\nGerman preferred"
        self.offer.save()
        first = enrich_offer(self.offer)
        self.assertIn("required_languages", first.facts)
        self.offer.description = "English required German preferred"
        self.offer.save()
        second = enrich_offer(self.offer)
        self.assertNotEqual(first.semantic_hash, second.semantic_hash)
        self.assertNotIn("required_languages", second.facts)

    def test_partial_dates_and_open_duration_bounds_in_filters(self):
        self.revision({"description": self.offer.description})
        enrich_offer(self.offer)
        qs = Offer.objects.filter(pk=self.offer.pk)
        self.assertTrue(
            filter_catalogue(
                qs, {"start_from": "2027-05-01", "include_unknown": "true"}
            ).exists()
        )
        self.assertFalse(
            filter_catalogue(
                qs, {"start_from": "2027-05-01", "include_unknown": "false"}
            ).exists()
        )
        self.assertTrue(
            filter_catalogue(
                qs,
                {
                    "duration_min": 4,
                    "duration_unit": "months",
                    "include_unknown": "false",
                },
            ).exists()
        )
        self.assertFalse(
            filter_catalogue(
                qs,
                {
                    "duration_max": 2,
                    "duration_unit": "months",
                    "include_unknown": "false",
                },
            ).exists()
        )
        self.assertNotEqual(
            evaluate_match(self.offer, {}, {"duration_max_months": 4})["compatibility"],
            "incompatible_explicit",
        )

    def test_public_api_includes_projection_without_writing(self):
        self.revision({"description": self.offer.description})
        enrich_offer(self.offer)
        before = self.offer.enrichment.content
        response = self.client.get(f"/api/v1/offers/{self.offer.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], before)
        self.assertNotIn("payload", response.json()["content"])

    def test_structured_change_updates_semantic_facts(self):
        self.revision(
            {
                "description": self.offer.description,
                "application_deadline": "2027-03-01T12:00:00Z",
            }
        )
        first = enrich_offer(self.offer)
        self.assertEqual(first.facts["application_deadline"]["method"], "structured")
        self.revision(
            {
                "description": self.offer.description,
                "application_deadline": "2027-04-01T12:00:00Z",
            },
            "d" * 64,
        )
        second = enrich_offer(self.offer)
        self.assertEqual(second.content_version, 2)
        self.assertTrue(
            second.facts["application_deadline"]["value"].startswith("2027-04-01")
        )

    def test_conflicting_exact_date_does_not_pass_strict_date_filter(self):
        self.offer.description = "Start: 2027-05-01."
        self.offer.save()
        self.revision(
            {"description": self.offer.description, "jobStartDate": "2027-06-01"}
        )
        enrichment = enrich_offer(self.offer)
        self.assertEqual(enrichment.facts["start_date"]["status"], "conflict")
        qs = Offer.objects.filter(pk=self.offer.pk)
        self.assertFalse(
            filter_catalogue(
                qs, {"start_to": "2027-12-31", "include_unknown": "false"}
            ).exists()
        )
        self.assertTrue(
            filter_catalogue(
                qs, {"start_to": "2027-12-31", "include_unknown": "true"}
            ).exists()
        )
