"""Verify the delivered seed and SQL constraints; roll back every attempted write."""

import psycopg


def main():
    checks = 0
    with psycopg.connect("") as connection, connection.transaction(force_rollback=True):

        def expect(label, query, expected):
            nonlocal checks
            actual = connection.execute(query).fetchone()[0]
            if actual != expected:
                raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")
            checks += 1
            print(f"OK {checks:02d} — {label}")

        def reject(label, query, sqlstate, constraint=None):
            nonlocal checks
            try:
                with connection.transaction(force_rollback=True):
                    connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
                    connection.execute(query)
            except psycopg.IntegrityError as error:
                if error.sqlstate != sqlstate or (
                    constraint and error.diag.constraint_name != constraint
                ):
                    raise
            else:
                raise AssertionError(f"{label}: invalid write accepted")
            checks += 1
            print(f"OK {checks:02d} — {label} rejected ({sqlstate})")

        for label, table, count in [
            ("8 comptes", "auth_user", 8),
            ("4 profils candidats dont un en attente", "jobboard_candidateprofile", 4),
            ("3 recruteurs", "jobboard_recruiterprofile", 3),
            ("3 entreprises", "jobboard_company", 3),
            ("4 stages", "jobboard_offer", 4),
            ("2 dossiers", "jobboard_application", 2),
            ("2 transmissions au recruteur", "jobboard_recruiterapplicant", 2),
            ("3 CV fictifs", "jobboard_document", 3),
        ]:
            expect(label, f"SELECT count(*) FROM {table}", count)
        expect(
            "Alice possède un dossier",
            """SELECT count(*) FROM jobboard_application
               WHERE user_id=(SELECT id FROM auth_user WHERE username='alice')""",
            1,
        )
        expect(
            "vide sans candidature",
            """SELECT count(*) FROM jobboard_application
               WHERE user_id=(SELECT id FROM auth_user WHERE username='vide')""",
            0,
        )
        expect(
            "Entreprise Sans Offre vide",
            """SELECT count(*) FROM jobboard_offer
               WHERE company_id=(SELECT id FROM jobboard_company
                                 WHERE name='Entreprise Sans Offre')""",
            0,
        )
        expect(
            "2 stages sans candidature",
            """SELECT count(*) FROM jobboard_offer o
               WHERE NOT EXISTS (SELECT 1 FROM jobboard_application a WHERE a.offer_id=o.id)""",
            2,
        )
        expect(
            "compte attente inactif",
            "SELECT is_active FROM auth_user WHERE username='attente'",
            False,
        )
        expect(
            "un seul administrateur",
            "SELECT count(*) FROM auth_user WHERE is_superuser AND is_staff",
            1,
        )
        expect(
            "2 recruteurs vérifiés",
            """SELECT count(*) FROM jobboard_recruiterprofile
               WHERE email_verified AND verification_status='verified'""",
            2,
        )
        expect(
            "recruteur non vérifié sans offre",
            """SELECT count(*) FROM jobboard_recruiterjob j
               JOIN jobboard_recruiterprofile r ON r.id=j.owner_id
               WHERE r.verification_status='unverified'""",
            0,
        )
        expect(
            "2 propriétaires distincts dans la même entreprise",
            """SELECT
               count(DISTINCT j.owner_id)=2 AND count(DISTINCT r.company_id)=1
               FROM jobboard_recruiterjob j JOIN jobboard_recruiterprofile r ON r.id=j.owner_id""",
            True,
        )
        expect(
            "e-mails entièrement fictifs",
            """SELECT count(*) FROM auth_user
               WHERE email <> username || '@example.test'""",
            0,
        )
        expect(
            "8 empreintes scrypt salées distinctes",
            """SELECT count(DISTINCT password)
               FROM auth_user WHERE password LIKE 'scrypt$%'""",
            8,
        )
        expect(
            "alias SQL du hash synchronisé",
            """SELECT count(*) FROM auth_user
               WHERE mot_de_passe_hash IS DISTINCT FROM password""",
            0,
        )
        expect(
            "sources sans possibilité d'envoi externe",
            """SELECT count(*) FROM jobboard_sourceboard
               WHERE submission_mode <> 'unsupported' OR base_url <> 'https://example.test'""",
            0,
        )

        alice = "(SELECT id FROM auth_user WHERE username='alice')"
        bob = "(SELECT id FROM auth_user WHERE username='bob')"
        app = f"(SELECT id FROM jobboard_application WHERE user_id={alice})"
        other_source = (
            f"(SELECT source_id FROM jobboard_application WHERE user_id={bob})"
        )
        other_offer = f"(SELECT offer_id FROM jobboard_application WHERE user_id={bob})"
        reject(
            "R1 / entreprise obligatoire",
            "UPDATE jobboard_offer SET company_id=NULL",
            "23502",
        )
        reject(
            "R1 / entreprise inexistante",
            "UPDATE jobboard_offer SET company_id=-1",
            "23503",
        )
        reject(
            "R2 / CV d'un autre candidat",
            f"""UPDATE jobboard_candidateprofile
               SET current_resume_id=(SELECT id FROM jobboard_document WHERE owner_id={bob})
               WHERE user_id={alice}""",
            "23503",
            "profile_resume_owner_kind_fk",
        )
        reject(
            "R3 / source d'une autre offre",
            f"""UPDATE jobboard_application
               SET source_id={other_source} WHERE id={app}""",
            "23503",
            "application_source_offer_fk",
        )
        reject(
            "R4 / dossier en double",
            f"""INSERT INTO jobboard_application
               (id,user_id,offer_id,source_id,status,created_at,updated_at)
               SELECT -1,user_id,offer_id,source_id,status,created_at,updated_at
               FROM jobboard_application WHERE id={app}""",
            "23505",
            "application_user_offer_unique",
        )
        reject(
            "R5 / login en double",
            "UPDATE auth_user SET username='alice' WHERE username='bob'",
            "23505",
            "auth_user_username_key",
        )
        reject(
            "statut de candidature invalide",
            f"UPDATE jobboard_application SET status='invalid' WHERE id={app}",
            "23514",
            "application_status_valid",
        )
        reject(
            "R2 / transmission au mauvais recruteur",
            f"""UPDATE jobboard_recruiterapplicant
               SET job_id=(SELECT j.id FROM jobboard_recruiterjob j WHERE j.offer_id={other_offer})
               WHERE application_id={app}""",
            "23503",
            "recruiter_application_job_offer_fk",
        )
        reject(
            "R2 / CV transmis d'un tiers",
            f"""UPDATE jobboard_recruiterapplicant
               SET resume_id=(SELECT id FROM jobboard_document WHERE owner_id={bob})
               WHERE application_id={app}""",
            "23503",
            "recruiter_application_resume_owner_fk",
        )
        reject(
            "R2 / candidat miroir falsifié",
            f"""UPDATE jobboard_recruiterapplicant
               SET candidate_id={bob} WHERE application_id={app}""",
            "23503",
            "recruiter_application_owner_offer_fk",
        )
        reject(
            "R2 / document d'un type différent",
            f"""UPDATE jobboard_recruiterapplicant
               SET resume_kind='cover_letter' WHERE application_id={app}""",
            "23514",
            "recruiter_resume_kind_valid",
        )
        reject(
            "offre référencée supprimée",
            f"""DELETE FROM jobboard_offer
               WHERE id=(SELECT offer_id FROM jobboard_application WHERE id={app})""",
            "23503",
        )

        with connection.transaction(force_rollback=True):
            connection.execute(
                "UPDATE auth_user SET password='hash-test-temporaire' WHERE username='alice'"
            )
            expect(
                "alias recalculé après modification",
                """SELECT mot_de_passe_hash=password
                   FROM auth_user WHERE username='alice'""",
                True,
            )
    print(f"PASS — {checks} vérifications ; écritures de test annulées.")


if __name__ == "__main__":
    main()
