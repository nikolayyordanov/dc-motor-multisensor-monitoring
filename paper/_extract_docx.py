"""Extract text (paragraphs + tables) from the DiB template and sample docx files.

Writes UTF-8 output so non-ASCII text is preserved when read back.
"""
import sys
from pathlib import Path

try:
    from docx import Document
except ImportError:
    print("python-docx not installed", file=sys.stderr)
    sys.exit(2)


def iter_block_items(doc):
    """Yield ('para', text) and ('table', rows) in document order."""
    from docx.oxml.text.paragraph import CT_P
    from docx.oxml.table import CT_Tbl
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body = doc.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield ("para", Paragraph(child, doc))
        elif isinstance(child, CT_Tbl):
            yield ("table", Table(child, doc))


def dump(path: Path, out: Path):
    doc = Document(str(path))
    lines = []
    for kind, item in iter_block_items(doc):
        if kind == "para":
            style = item.style.name if item.style else ""
            text = item.text.rstrip()
            if text:
                lines.append(f"[{style}] {text}")
            else:
                lines.append("")
        else:  # table
            lines.append("=== TABLE START ===")
            for row in item.rows:
                cells = [c.text.strip().replace("\n", " / ") for c in row.cells]
                lines.append(" | ".join(cells))
            lines.append("=== TABLE END ===")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out} ({len(lines)} lines)")


here = Path(__file__).parent
dump(here / "data-in-brief-article-template.docx", here / "_template.txt")
dump(here / "data-in-brief-article_ MZH_NY_MM_ME_MG.docx", here / "_sample.txt")
