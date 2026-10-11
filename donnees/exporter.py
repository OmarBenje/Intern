"""Export the fictitious seed database using standard PostgreSQL PG* variables."""

import subprocess
from pathlib import Path

import psycopg


def main():
    with psycopg.connect("") as connection:
        rows = connection.execute("SELECT username, email FROM auth_user").fetchall()
        expected = {
            "alice",
            "bob",
            "vide",
            "attente",
            "admin",
            "recruteur_a",
            "recruteur_b",
            "recruteur_non_verifie",
        }
        if {row[0] for row in rows} != expected or any(
            email != f"{username}@example.test" for username, email in rows
        ):
            raise SystemExit("Export refused: use the isolated seed_dev database.")

    directory = Path(__file__).resolve().parent
    for filename, mode in [
        ("schema.sql", "--schema-only"),
        ("data.sql", "--data-only"),
    ]:
        dump = subprocess.check_output(
            ["pg_dump", mode, "--no-owner", "--no-privileges"], text=True
        )
        # Search-document triggers resolve the application tables in public.
        dump = dump.replace(
            "SELECT pg_catalog.set_config('search_path', '', false);",
            "SET LOCAL search_path = public, pg_catalog;",
        )
        header = (
            "-- Intern DEV / étape 3. Généré depuis les migrations et seed_dev.\n"
            "-- Base dédiée uniquement ; voir donnees/README.md.\nBEGIN;\n"
        )
        if filename == "data.sql":
            header += (
                "DO $$ BEGIN\n"
                "  IF EXISTS (SELECT 1 FROM auth_user) OR "
                "EXISTS (SELECT 1 FROM jobboard_company) THEN\n"
                "    RAISE EXCEPTION 'Peuplement refusé : base déjà utilisée';\n"
                "  END IF;\nEND $$;\nSET CONSTRAINTS ALL DEFERRED;\n"
            )
            dump += (
                "\n-- Dates de démonstration locales, sans vérification réseau.\n"
                "UPDATE jobboard_offersource SET last_checked_at = CURRENT_TIMESTAMP;\n"
            )
        (directory / filename).write_text(header + dump + "\nCOMMIT;\n")
        print(f"Exported {filename}")


if __name__ == "__main__":
    main()
