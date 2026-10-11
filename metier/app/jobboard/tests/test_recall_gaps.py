from django.test import SimpleTestCase

from jobboard.integrations.greenhouse_catalogue import normalize_snapshot
from jobboard.integrations.public_catalogue import normalize_ashby, normalize_lever
from jobboard.services.ats_probing import qualifies
from jobboard.services.engine_quality import extract_facts


class RecallGapTests(SimpleTestCase):
    def test_ashby_hybrid_remote_flag_preserves_european_internship(self):
        job = {
            "title": "Software Engineer, Intern (Summer 2027)",
            "descriptionPlain": "A twelve week internship in Vienna.",
            "jobUrl": "https://jobs.ashbyhq.com/sentry/test",
            "location": "Vienna, Austria",
            "address": {"postalAddress": {"addressCountry": "Austria"}},
            "employmentType": "FullTime",
            "isRemote": True,
            "workplaceType": "Hybrid",
        }
        for workplace, mode, eligible in [
            ("Hybrid", "hybrid", True),
            ("OnSite", "onsite", True),
            ("Remote", "remote", False),
            (None, "remote", False),
            ("unrecognized", "remote", False),
        ]:
            with self.subTest(workplace=workplace):
                row = normalize_ashby({"jobs": [dict(job, workplaceType=workplace)]})[0]
                self.assertEqual(row["work_mode"], mode)
                self.assertEqual(qualifies(row), eligible)
        self.assertFalse(
            qualifies(
                normalize_ashby(
                    {
                        "jobs": [
                            dict(
                                job,
                                title="Software Engineer, New Grad",
                                descriptionPlain="A full-time position.",
                            )
                        ]
                    }
                )[0]
            )
        )
        self.assertEqual(normalize_ashby({"jobs": [dict(job, isListed=False)]}), [])

    def test_lever_country_belongs_only_to_primary_location(self):
        job = {
            "id": "stage",
            "text": "Internship",
            "descriptionPlain": "Internship for six months",
            "hostedUrl": "https://jobs.lever.co/acme/stage",
            "country": "FR",
            "categories": {"location": "Paris", "allLocations": ["Paris", "Boston"]},
        }
        row = normalize_lever([job])[0]
        self.assertEqual(
            row["location_details"],
            [{"name": "Paris", "country": "FR"}, {"name": "Boston", "country": ""}],
        )
        self.assertTrue(qualifies(row))
        job["categories"]["location"] = "Missing"
        self.assertFalse(qualifies(normalize_lever([job])[0]))
        job["categories"]["location"] = "Paris"
        job["workplaceType"] = "remote"
        self.assertFalse(qualifies(normalize_lever([job])[0]))

    def gh(self, location, labels):
        return normalize_snapshot(
            {
                "meta": {"total": 1},
                "jobs": [
                    {
                        "id": 1,
                        "title": "Internship",
                        "content": "Internship",
                        "absolute_url": "https://example.com/job/1",
                        "location": {"name": location},
                        "metadata": [
                            {
                                "name": "Locations",
                                "value_type": "multi_select",
                                "value": labels,
                            }
                        ],
                        "offices": [
                            {"name": "London", "location": "London, United Kingdom"},
                            {"name": "Paris", "location": "Paris, France"},
                            {"name": "Boston", "location": "Boston, United States"},
                        ],
                    }
                ],
            }
        )[0]

    def test_greenhouse_comma_list_requires_matching_metadata(self):
        row = self.gh("Paris, London", ["London", "Paris"])
        self.assertEqual(
            {d["country"] for d in row["location_details"]},
            {"", "France", "United Kingdom"},
        )
        self.assertTrue(qualifies(row))
        for location, labels in [
            ("Paris, Texas", []),
            ("Paris, Texas", ["Paris", "London"]),
            ("London, Paris", ["London"]),
            ("London, Paris", "London"),
            ("Remote", ["London", "Paris"]),
        ]:
            with self.subTest(location=location, labels=labels):
                self.assertFalse(qualifies(self.gh(location, labels)))

    def test_danish_requires_placement_period_and_preserves_exclusions(self):
        for title in [
            "Bliv AI Praktikant hos WPP Media",
            "Bliv videopraktikant hos WPP Media",
        ]:
            facts = extract_facts(
                title,
                "Praktikperiode: 11. januar – 18. juni 2027.",
                locations=[{"name": "Copenhagen, Denmark"}],
            )
            self.assertEqual(facts["classification"], "confirmed")
            self.assertEqual(
                facts["facts"]["classification"]["reason"], "danish_placement_period"
            )
            self.assertEqual(
                extract_facts(title, "We have offices in Denmark")["classification"],
                "uncertain",
            )
        self.assertEqual(
            extract_facts("Senior Praktikant", "Praktikperiode: januar til juni")[
                "classification"
            ],
            "not_internship",
        )
        self.assertNotEqual(
            extract_facts("Office assistant", "Praktikperiode: januar til juni")[
                "classification"
            ],
            "confirmed",
        )
