"""Generate a simplified relation diagram as a PDF and a PNG preview."""

import subprocess
from pathlib import Path

from reportlab.lib import colors
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1200, 950
BLUE = colors.HexColor("#203d56")
GRAY = colors.HexColor("#536472")
BOX_WIDTH, BOX_HEIGHT = 280, 145

# The arrows point from the referencing table to the referenced table.
NODES = {
    "candidate": (
        60,
        645,
        "Profil candidat",
        "jobboard_candidateprofile",
        ["PK id", "FK user_id — unique", "FK current_resume_id — optionnel"],
    ),
    "user": (
        460,
        645,
        "Compte",
        "auth_user",
        [
            "PK id · UNIQUE username",
            "password / mot_de_passe_hash",
            "is_active · droits d'administration",
        ],
    ),
    "recruiter": (
        860,
        645,
        "Profil recruteur",
        "jobboard_recruiterprofile",
        [
            "PK id · FK user_id — unique",
            "FK company_id — optionnel",
            "email_verified · verification_status",
        ],
    ),
    "document": (
        60,
        395,
        "Document privé",
        "jobboard_document",
        ["PK id · FK owner_id", "kind · object_key · sha256", "3 CV de démonstration"],
    ),
    "application": (
        460,
        395,
        "Candidature",
        "jobboard_application",
        ["PK id · FK user_id / offer_id", "FK source_id", "UNIQUE (user_id, offer_id)"],
    ),
    "job": (
        860,
        395,
        "Poste du recruteur",
        "jobboard_recruiterjob",
        [
            "PK id · FK owner_id",
            "FK offer_id — unique, optionnel",
            "2 postes, 2 propriétaires distincts",
        ],
    ),
    "source": (
        60,
        145,
        "Source d'une offre",
        "jobboard_offersource",
        [
            "PK id · FK offer_id / board_id",
            "source_id + offer_id cohérents",
            "Sources fictives, sans envoi externe",
        ],
    ),
    "offer": (
        460,
        145,
        "Offre de stage",
        "jobboard_offer",
        [
            "PK id · FK company_id obligatoire",
            "title · contract_type · status",
            "4 stages, dont 2 sans candidature",
        ],
    ),
    "company": (
        860,
        145,
        "Entreprise",
        "jobboard_company",
        ["PK id · name", "3 entreprises", "Dont une sans offre"],
    ),
}


def arrow(pdf, points):
    pdf.setStrokeColor(GRAY)
    pdf.setLineWidth(1.4)
    for start, end in zip(points, points[1:]):
        pdf.line(*start, *end)
    x, y = points[-1]
    old_x, old_y = points[-2]
    if x == old_x:
        sign = 1 if y > old_y else -1
        pdf.line(x, y, x - 5, y - 9 * sign)
        pdf.line(x, y, x + 5, y - 9 * sign)
    else:
        sign = 1 if x > old_x else -1
        pdf.line(x, y, x - 9 * sign, y - 5)
        pdf.line(x, y, x - 9 * sign, y + 5)


def main():
    pdf = canvas.Canvas(
        str(ROOT / "schema_visuel.pdf"), pagesize=(WIDTH, HEIGHT), invariant=1
    )
    pdf.setTitle("Intern — relations principales de la couche données")
    pdf.setAuthor("Intern")
    pdf.setFillColor(BLUE)
    pdf.setFont("Helvetica-Bold", 27)
    pdf.drawString(60, 900, "Intern — couche données")
    pdf.setFont("Helvetica", 12)
    pdf.setFillColor(GRAY)
    pdf.drawString(
        60,
        871,
        "Vue simplifiée : 9 tables principales parmi les 72 tables du schéma complet.",
    )
    pdf.drawString(
        60,
        850,
        "Les flèches suivent les clés étrangères vers la table référencée. PK = clé primaire ; FK = clé étrangère.",
    )

    for points in [
        [(340, 730), (460, 730)],
        [(860, 730), (740, 730)],
        [(600, 540), (600, 645)],
        [(600, 395), (600, 290)],
        [(460, 440), (375, 440), (375, 250), (340, 250)],
        [(200, 540), (200, 595), (500, 595), (500, 645)],
        [(1000, 540), (1000, 645)],
        [(860, 440), (800, 440), (800, 250), (740, 250)],
        [(1120, 645), (1170, 645), (1170, 215), (1140, 215)],
        [(340, 190), (460, 190)],
        [(740, 215), (860, 215)],
    ]:
        arrow(pdf, points)

    for x, y, title, table, fields in NODES.values():
        pdf.setFillColor(colors.HexColor("#f3f6f8"))
        pdf.setStrokeColor(colors.HexColor("#cfdae2"))
        pdf.roundRect(x, y, BOX_WIDTH, BOX_HEIGHT, 10, fill=1, stroke=1)
        pdf.setFillColor(BLUE)
        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawString(x + 15, y + 119, title)
        pdf.setFont("Helvetica", 10)
        pdf.setFillColor(GRAY)
        pdf.drawString(x + 15, y + 99, table)
        pdf.setFillColor(colors.HexColor("#192936"))
        pdf.setFont("Helvetica", 11)
        for index, field in enumerate(fields):
            pdf.drawString(x + 15, y + 73 - 22 * index, field)

    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(BLUE)
    pdf.drawString(
        60,
        99,
        "Transmission au recruteur : candidature, poste destinataire et CV du candidat liés par des FK composites.",
    )
    pdf.setFont("Helvetica", 11)
    pdf.setFillColor(GRAY)
    pdf.drawString(
        60,
        76,
        "Le modèle détaillé décrit aussi cette transmission, les sources de catalogue et les autres tables.",
    )
    pdf.drawString(
        60,
        47,
        "Jeu fictif : 8 comptes · 3 entreprises · 4 stages · 2 candidatures · 3 CV. Les droits HTTP relèvent de l'API.",
    )
    pdf.save()
    subprocess.run(
        [
            "pdftoppm",
            "-scale-to",
            "1800",
            "-png",
            "-singlefile",
            str(ROOT / "schema_visuel.pdf"),
            str(ROOT / "schema_visuel"),
        ],
        check=True,
    )
    print("Generated schema_visuel.pdf and schema_visuel.png")


if __name__ == "__main__":
    main()
