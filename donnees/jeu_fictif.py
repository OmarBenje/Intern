"""Shared account definitions for the DEV seed and SQL export guard."""

CANDIDATS = (
    ("alice", "Alice Exemple"),
    ("bob", "Bob Exemple"),
    ("vide", "Camille Exemple"),
    ("attente", "Dominique Exemple"),
)
RECRUTEURS = (
    ("recruteur_a", "Elise Exemple", True),
    ("recruteur_b", "Farid Exemple", True),
    ("recruteur_non_verifie", "Gaelle Exemple", False),
)
ADMIN_LOGIN = "admin"
MOT_DE_PASSE_DEMO = "Intern-Demo-2026!"


def comptes_attendus():
    return {
        login: f"{login}@example.test"
        for login in (
            *(row[0] for row in CANDIDATS),
            *(row[0] for row in RECRUTEURS),
            ADMIN_LOGIN,
        )
    }
