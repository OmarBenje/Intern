from pathlib import Path
import markdown
from bs4 import BeautifulSoup
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BodyDev", fontName="Helvetica", fontSize=8.5, leading=11, spaceAfter=5))
styles.add(ParagraphStyle(name="CellDev", fontName="Helvetica", fontSize=7.5, leading=9.5))

def prepare_html_for_reportlab(element):
    """
    Formatte les liens <a> pour ReportLab sans imbriquer de balises <u>
    qui cassent le parseur XML interne de ReportLab.
    """
    soup_copy = BeautifulSoup(str(element), "html.parser")
    
    for a in soup_copy.find_all("a"):
        href = a.get("href")
        if href:
            text = a.get_text()
            # Nettoyage des attributs pour garder uniquement href et color
            a.attrs = {
                "href": href,
                "color": "#0056b3"
            }
            # Texte brut sans balises HTML imbriquées à l'intérieur de <a>
            a.string = text

    root_tag = soup_copy.find()
    if root_tag and root_tag.name in ["p", "li", "h1", "h2", "h3", "td", "th"]:
        return "".join(str(child) for child in root_tag.children)
    
    return str(soup_copy)

def render(source, target):
    md_text = source.read_text(encoding="utf-8")
    html_content = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    
    soup = BeautifulSoup(html_content, "html.parser")
    story = []
    
    for node in soup.children:
        name = getattr(node, "name", None)
        if not name:
            continue
            
        if name == "table":
            rows = []
            for row in node.find_all("tr"):
                cells = []
                for cell in row.find_all(["th", "td"]):
                    formatted_cell_html = prepare_html_for_reportlab(cell)
                    cells.append(Paragraph(formatted_cell_html, styles["CellDev"]))
                if cells:
                    rows.append(cells)
                    
            if rows:
                columns = len(rows[0])
                widths = [523 / columns] * columns
                if columns == 3:
                    widths = [95, 214, 214]
                elif columns == 4:
                    widths = [28, 205, 205, 85]
                
                table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5edf3")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#aebcc5")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]))
                story += [table, Spacer(1, 8)]
                
        elif name in ["ul", "ol"]:
            for item in node.find_all("li", recursive=False):
                formatted_item_html = prepare_html_for_reportlab(item)
                story.append(Paragraph("• " + formatted_item_html, styles["BodyDev"]))
                
        else:
            style = styles[{"h1": "Heading1", "h2": "Heading2", "h3": "Heading3"}.get(name, "BodyDev")]
            formatted_node_html = prepare_html_for_reportlab(node)
            story.append(Paragraph(formatted_node_html, style))
            
    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.drawString(36, 20, "Intern - DEV - Analyse fonctionnelle")
        canvas.drawRightString(A4[0] - 36, 20, str(doc.page))
        
    SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=30,
        bottomMargin=34,
        title=source.stem,
        author="Projet Intern"
    ).build(story, onFirstPage=footer, onLaterPages=footer)

if __name__ == "__main__":
    source = ROOT / "cas_d_usage.md"
    render(source, source.with_suffix(".pdf"))