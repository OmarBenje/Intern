"""Export the four Markdown report pages to A4 PDF using Matplotlib.

The report stays the single editable source. An overflowing page fails export.
"""

from pathlib import Path
import os
import re
import tempfile
import textwrap

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "intern-matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.image as mpimg
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath

from etalonnage import digest


ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 595.28, 841.89
MARGIN = 40


def plain(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.replace("**", "").replace("`", "")


def wrap_cell(text, width):
    """Wrap to the actual font width, including the wider bold header font."""
    font = FontProperties(size=8.2, weight="bold")
    lines, current = [], ""
    for word in text.split():
        candidate = (current + " " + word).strip()
        if current and TextPath((0, 0), candidate, prop=font).get_extents().width > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    return "\n".join([*lines, current])


def render_page(fig, content, source):
    y = HEIGHT - MARGIN
    lines = content.strip().splitlines()
    index = 0

    def space(points):
        nonlocal y
        y -= points
        if y < MARGIN + 15:
            raise RuntimeError("Report page overflows: shorten its text or table")

    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            size = {1: 15, 2: 12, 3: 10.5}.get(level, 10)
            fig.text(MARGIN / WIDTH, y / HEIGHT, plain(line.lstrip("# ")),
                     fontsize=size, fontweight="bold", va="top", color="#16324b")
            space(size + 10)
            index += 1
        elif line.startswith("!["):
            target = re.search(r"\]\(([^)]+)\)", line).group(1)
            image = mpimg.imread(source.parent / target)
            h = min(450, (WIDTH - 2 * MARGIN) * image.shape[0] / image.shape[1])
            w = h * image.shape[1] / image.shape[0]
            ax = fig.add_axes([(WIDTH - w) / (2 * WIDTH), (y - h) / HEIGHT, w / WIDTH, h / HEIGHT])
            ax.imshow(image)
            ax.axis("off")
            space(h + 8)
            index += 1
        elif line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = [plain(cell.strip()) for cell in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                index += 1
            count = len(rows[0])
            widths = [0.34, 0.33, 0.33] if count == 3 else [0.15, 0.30, 0.275, 0.275]
            wrapped = [[wrap_cell(cell, (WIDTH - 2 * MARGIN) * width * .88)
                        for cell, width in zip(row, widths)] for row in rows]
            row_heights = [max(cell.count("\n") + 1 for cell in row) * 10.5 + 8 for row in wrapped]
            height = sum(row_heights)
            ax = fig.add_axes([MARGIN / WIDTH, (y - height) / HEIGHT,
                               (WIDTH - 2 * MARGIN) / WIDTH, height / HEIGHT])
            ax.axis("off")
            table = ax.table(cellText=wrapped, colWidths=widths, bbox=[0, 0, 1, 1], cellLoc="left")
            table.auto_set_font_size(False)
            table.set_fontsize(8.2)
            for (row, col), cell in table.get_celld().items():
                cell.set_height(row_heights[row] / height)
                cell.set_edgecolor("#c2ccd5")
                cell.set_linewidth(.5)
                cell.PAD = .05
                if row == 0:
                    cell.set_facecolor("#e6eef5")
                    cell.set_text_props(fontweight="bold")
            space(height + 10)
        else:
            paragraph = []
            while index < len(lines) and lines[index].strip():
                if paragraph and lines[index].strip().startswith(("#", "|", "![", "- ")):
                    break
                paragraph.append(lines[index].strip())
                index += 1
                if paragraph[0].startswith("- "):
                    break
            text = plain(" ".join(paragraph))
            if text.startswith("- "):
                text = "• " + text[2:]
            wrapped = textwrap.fill(text, width=105, break_long_words=False, break_on_hyphens=False)
            fig.text(MARGIN / WIDTH, y / HEIGHT, wrapped, fontsize=9.3,
                     linespacing=1.30, va="top", color="#202c38")
            space((wrapped.count("\n") + 1) * 12.1 + 7)


def main():
    source = ROOT / "docs/rapport-charge.md"
    pages = source.read_text().split("<!-- page -->")
    if len(pages) != 4:
        raise RuntimeError("Expected four explicit report pages")
    with PdfPages(source.with_suffix(".pdf"), metadata={"Title": "Intern : analyse et comparaison de charge",
                                                      "Author": "Projet Intern"}) as pdf:
        for number, page in enumerate(pages, 1):
            fig = plt.figure(figsize=(WIDTH / 72, HEIGHT / 72))
            render_page(fig, page, source)
            fig.text(MARGIN / WIDTH, .025, "Intern · Mesure de charge", fontsize=8, color="#64748b")
            fig.text(.94, .025, f"{number} / 4", fontsize=8, ha="right", color="#64748b")
            pdf.savefig(fig)
            plt.close(fig)
    artifacts = [source, source.with_suffix(".pdf"),
                 ROOT / "resultats/etape18/analyse.json", ROOT / "resultats/etape18/comparaison.csv",
                 ROOT / "docs/courbes/ensemble.png", ROOT / "docs/courbes/ensemble.pdf"]
    artifacts += [ROOT / f"docs/courbes/{name}.{extension}"
                  for name in ("debit", "latence-p95", "erreurs") for extension in ("png", "svg")]
    (ROOT / "resultats/etape18/SHA256SUMS").write_text(
        "".join(f"{digest(path)}  {path.relative_to(ROOT)}\n" for path in sorted(artifacts)))
    print("Rapport A4 exporté : quatre pages.")


if __name__ == "__main__":
    main()
