"""Exercise the actual upgrade AND rollback with legacy data in an isolated test DB."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

OLD = [("jobboard", "0008_alter_offer_contract_type_alter_offer_work_mode")]
NEW = [("jobboard", "0014_composite_foreign_keys")]


class SchemaMigrationTests(TransactionTestCase):
    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        self.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_upgrade_and_rollback_preserve_legacy_ids_links_and_preferences(self):
        old = self.migrate(OLD)
        User = old.get_model("auth", "User")
        user = User.objects.create(username="legacy")
        other_user = User.objects.create(username="legacy-none")
        skill = old.get_model("jobboard", "Skill").objects.create(name="C++")
        another_skill = old.get_model("jobboard", "Skill").objects.create(name="C#")
        role = old.get_model("jobboard", "Role").objects.create(name="Engineer")
        company = old.get_model("jobboard", "Company").objects.create(
            name="Legacy company"
        )
        location = old.get_model("jobboard", "Location").objects.create(name="Paris")
        offer = old.get_model("jobboard", "Offer").objects.create(
            company=company,
            role=role,
            title="Legacy role",
            description="Description conservée",
            application_url="https://example.com/apply",
            contract_type="job",
            work_mode="hybrid",
            is_active=False,
        )
        offer.locations.add(location)
        offer.skills.add(skill, another_skill)
        profile = old.get_model("jobboard", "CandidateProfile").objects.create(
            user=user,
            full_name="Legacy",
            location="Lieu libre conservé",
            resume_url="https://example.com/private-cv.pdf",
        )
        profile.skills.add(skill)
        other_profile = old.get_model("jobboard", "CandidateProfile").objects.create(
            user=other_user, full_name="None"
        )
        preference = old.get_model("jobboard", "SearchPreference").objects.create(
            profile=profile,
            accepts_internships=False,
            accepts_apprenticeships=False,
            accepts_jobs=True,
            accepts_remote=True,
            accepts_hybrid=False,
            accepts_onsite=False,
        )
        preference.roles.add(role)
        preference.locations.add(location)
        empty_preference = old.get_model("jobboard", "SearchPreference").objects.create(
            profile=other_profile,
            accepts_internships=False,
            accepts_apprenticeships=False,
            accepts_jobs=False,
            accepts_remote=False,
            accepts_hybrid=False,
            accepts_onsite=False,
        )
        link_id = offer.locations.through.objects.get(
            offer_id=offer.pk, location_id=location.pk
        ).pk

        new = self.migrate(NEW)
        upgraded_offer = new.get_model("jobboard", "Offer").objects.get(pk=offer.pk)
        self.assertEqual(upgraded_offer.contract_type, "employment")
        self.assertEqual(upgraded_offer.status, "closed")
        self.assertEqual(upgraded_offer.description, "Description conservée")
        self.assertEqual(
            set(upgraded_offer.skills.values_list("pk", flat=True)),
            {skill.pk, another_skill.pk},
        )
        self.assertEqual(
            new.get_model("jobboard", "OfferLocation")
            .objects.get(offer_id=offer.pk)
            .pk,
            link_id,
        )
        source = new.get_model("jobboard", "OfferSource").objects.get(offer_id=offer.pk)
        self.assertEqual(source.apply_url, "https://example.com/apply")
        self.assertFalse(source.board.enabled)
        upgraded_profile = new.get_model("jobboard", "CandidateProfile").objects.get(
            pk=profile.pk
        )
        self.assertEqual(upgraded_profile.location_text, "Lieu libre conservé")
        self.assertEqual(
            upgraded_profile.resume_url, "https://example.com/private-cv.pdf"
        )
        self.assertIsNone(upgraded_profile.current_resume_id)
        self.assertEqual(
            list(upgraded_profile.skills.values_list("pk", flat=True)), [skill.pk]
        )
        self.assertEqual(
            new.get_model("jobboard", "Location")
            .objects.get(pk=location.pk)
            .canonical_key,
            f"legacy:{location.pk}",
        )
        self.assertEqual(
            new.get_model("jobboard", "Skill")
            .objects.filter(slug__isnull=True)
            .count(),
            0,
        )
        self.assertEqual(
            new.get_model("jobboard", "Skill")
            .objects.values("slug")
            .distinct()
            .count(),
            2,
        )
        upgraded_preference = new.get_model("jobboard", "SearchPreference").objects.get(
            pk=preference.pk
        )
        self.assertEqual(
            list(upgraded_preference.roles.values_list("pk", flat=True)), [role.pk]
        )
        self.assertEqual(
            list(upgraded_preference.locations.values_list("pk", flat=True)),
            [location.pk],
        )
        contracts = new.get_model("jobboard", "PreferenceContract")
        modes = new.get_model("jobboard", "PreferenceWorkMode")
        self.assertEqual(
            list(
                contracts.objects.filter(preference_id=preference.pk).values_list(
                    "value", flat=True
                )
            ),
            ["employment"],
        )
        self.assertEqual(
            list(
                modes.objects.filter(preference_id=preference.pk).values_list(
                    "value", flat=True
                )
            ),
            ["remote"],
        )
        self.assertFalse(
            contracts.objects.filter(preference_id=empty_preference.pk).exists()
        )
        self.assertFalse(
            modes.objects.filter(preference_id=empty_preference.pk).exists()
        )

        restored = self.migrate(OLD)
        restored_offer = restored.get_model("jobboard", "Offer").objects.get(
            pk=offer.pk
        )
        self.assertEqual(restored_offer.contract_type, "job")
        self.assertFalse(restored_offer.is_active)
        self.assertEqual(
            restored_offer.locations.through.objects.get(offer_id=offer.pk).pk, link_id
        )
        restored_preference = restored.get_model(
            "jobboard", "SearchPreference"
        ).objects.get(pk=preference.pk)
        self.assertTrue(restored_preference.accepts_jobs)
        self.assertFalse(restored_preference.accepts_internships)
        self.assertTrue(restored_preference.accepts_remote)
        self.assertFalse(restored_preference.accepts_hybrid)
        restored_profile = restored.get_model(
            "jobboard", "CandidateProfile"
        ).objects.get(pk=profile.pk)
        self.assertEqual(restored_profile.location, "Lieu libre conservé")
