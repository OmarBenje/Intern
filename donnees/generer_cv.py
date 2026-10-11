"""Render a generic fictitious internship CV."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent
BLUE = colors.HexColor("#203d56")
GRAY = colors.HexColor("#536472")
STYLES = {
    "title": ParagraphStyle(
        "title", fontName="Helvetica-Bold", fontSize=23, leading=27, textColor=BLUE
    ),
    "subtitle": ParagraphStyle("subtitle", fontSize=12, leading=17, textColor=GRAY),
    "section": ParagraphStyle(
        "section",
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=BLUE,
        spaceBefore=14,
        spaceAfter=7,
    ),
    "body": ParagraphStyle("body", fontSize=9, leading=14, spaceAfter=7),
    "small": ParagraphStyle(
        "small", fontSize=8, leading=12, textColor=GRAY, spaceAfter=5
    ),
    "metric": ParagraphStyle(
        "metric",
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=22,
        alignment=TA_CENTER,
        textColor=BLUE,
    ),
    "caption": ParagraphStyle(
        "caption", fontSize=8, leading=12, alignment=TA_CENTER, textColor=GRAY
    ),
}


def paragraph(text, style="body"):
    return Paragraph(text, STYLES[style])


def main():
    document = SimpleDocTemplate(
        str(ROOT / "cv_fictif.pdf"),
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=32,
        bottomMargin=32,
        title="CV fictif — candidat stage informatique — Intern",
        author="Intern — jeu de démonstration",
        invariant=1,
    )
    story = [
        paragraph("Profil candidat — exemple", "title"),
        paragraph("Étudiant en informatique · Stage développement web", "subtitle"),
        paragraph("Paris, France · Disponibilité : stage de six mois", "small"),
        paragraph(
            "DONNÉES ENTIÈREMENT FICTIVES · Modèle de recette sans identité nominative",
            "small",
        ),
        Spacer(1, 12),
        HRFlowable(width="100%", thickness=1, color=BLUE),
        Spacer(1, 14),
    ]
    metrics = Table(
        [
            [
                paragraph("6 mois", "metric"),
                paragraph("3 projets", "metric"),
                paragraph("Web &amp; SQL", "metric"),
            ],
            [
                paragraph("Stage recherché", "caption"),
                paragraph("Travaux pédagogiques fictifs", "caption"),
                paragraph("Domaine de formation", "caption"),
            ],
        ],
        colWidths=[174, 174, 175],
    )
    story.extend([metrics, Spacer(1, 15)])
    left = [
        paragraph("PROFIL", "section"),
        paragraph(
            "Étudiant préparant une licence informatique. Recherche un stage pour participer à une application web, développer des API et travailler sur la qualité des données."
        ),
        paragraph("PROJETS ET EXPÉRIENCE", "section"),
        paragraph(
            "<b>Application web de suivi de stages</b><br/>Projet universitaire fictif · 2026"
        ),
        paragraph(
            "• Conception d'une interface React et d'une API Python.<br/>• Modélisation relationnelle sous PostgreSQL.<br/>• Contrôle des accès et tests de cohérence des données."
        ),
        paragraph("Python · Django · React · PostgreSQL", "small"),
        paragraph(
            "<b>Tableau de bord de données</b><br/>Travail pédagogique fictif · 2025"
        ),
        paragraph(
            "• Nettoyage d'un jeu de données de démonstration.<br/>• Requêtes SQL et restitution de statistiques.<br/>• Documentation des résultats et des cas limites."
        ),
        paragraph("Python · SQL · Git", "small"),
        paragraph(
            "<b>Site de présentation associatif</b><br/>Exercice de développement fictif · 2025"
        ),
        paragraph(
            "• Pages adaptables aux écrans mobiles.<br/>• Composants réutilisables et formulaires accessibles.<br/>• Revue de code et corrections en binôme."
        ),
        paragraph("HTML · CSS · JavaScript", "small"),
    ]
    right = [
        paragraph("COMPÉTENCES", "section"),
        paragraph("<b>Langages</b><br/>Python, JavaScript, TypeScript, SQL"),
        paragraph("<b>Développement web</b><br/>React, Django, API REST, HTML, CSS"),
        paragraph(
            "<b>Données et outils</b><br/>PostgreSQL, Git, Linux, tests automatisés"
        ),
        paragraph("FORMATION", "section"),
        paragraph(
            "<b>Licence informatique</b><br/>Établissement fictif<br/>2024–2027 — en cours"
        ),
        paragraph(
            "Algorithmique, bases de données, programmation web et génie logiciel."
        ),
        paragraph("LANGUES", "section"),
        paragraph("Français : courant<br/>Anglais : lecture technique"),
        paragraph("CENTRES D'INTÉRÊT", "section"),
        paragraph("Projets logiciels, veille technique et travail en équipe."),
    ]
    columns = Table([[left, right]], colWidths=[330, 193])
    columns.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 22),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#f3f6f8")),
                ("LEFTPADDING", (1, 0), (1, 0), 14),
                ("RIGHTPADDING", (1, 0), (1, 0), 12),
            ]
        )
    )
    story.append(columns)

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GRAY)
        canvas.drawString(
            36, 20, "Intern · CV générique partagé pour les tests · Aucun envoi réel"
        )
        canvas.drawRightString(A4[0] - 36, 20, f"Page {doc.page}")

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    print(ROOT / "cv_fictif.pdf")


if __name__ == "__main__":
    main()
