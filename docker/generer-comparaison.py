"""Render the comparison source as a two-page PDF."""

from pathlib import Path

import markdown
from bs4 import BeautifulSoup
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs/comparaison.md"
TARGET = ROOT / "docs/compte_rendu_comparaison.pdf"
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=8.5, leading=11, spaceAfter=5)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=7.6, leading=9, spaceAfter=0)
TITLE = ParagraphStyle("title", parent=BODY, fontSize=15, leading=18, spaceAfter=8)
HEADING = ParagraphStyle("heading", parent=BODY, fontSize=10, leading=12, spaceBefore=5, spaceAfter=5)


def content(node):
    copy = BeautifulSoup(str(node), "html.parser")
    for tag in copy.find_all("code"):
        tag.name = "font"
        tag.attrs = {"name": "Courier"}
    for tag in copy.find_all("a"):
        # Links to repository files remain in the Markdown source.
        tag.unwrap()
    outer = copy.find()
    return outer.decode_contents()


def page_number(canvas, document):
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(A4[0] - 36, 20, f"Intern | comparaison | {document.page}/2")


def main():
    pages = SOURCE.read_text().split("<!-- pagebreak -->")
    if len(pages) != 2:
        raise ValueError("The source must define exactly two pages")
    story = []
    for index, text in enumerate(pages):
        if index:
            story.append(PageBreak())
        soup = BeautifulSoup(markdown.markdown(text, extensions=["tables"]), "html.parser")
        for node in soup.children:
            tag = getattr(node, "name", None)
            if tag in ("h1", "h2", "h3", "p"):
                style = TITLE if tag == "h1" else BODY if tag == "p" else HEADING
                story.append(Paragraph(content(node), style))
            elif tag == "table":
                rows = [[Paragraph(content(cell), CELL) for cell in row.find_all(["td", "th"])]
                        for row in node.find_all("tr")]
                table = Table(rows, colWidths=[(A4[0] - 72) / len(rows[0])] * len(rows[0]), repeatRows=1)
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf3")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c3ccd6")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.extend([table, Spacer(1, 6)])
            elif tag in ("ol", "ul"):
                for item in node.find_all("li", recursive=False):
                    story.append(Paragraph("- " + content(item), BODY))
    SimpleDocTemplate(str(TARGET), pagesize=A4, rightMargin=36, leftMargin=36,
                      topMargin=32, bottomMargin=32,
                      title="Intern - comparaison VM et conteneurs", author="Intern").build(
                          story, onFirstPage=page_number, onLaterPages=page_number)
    print(TARGET.name)


if __name__ == "__main__":
    main()
