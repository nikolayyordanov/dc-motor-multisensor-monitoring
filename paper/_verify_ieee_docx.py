"""Dump the generated IEEE manuscript to text so its structure can be checked."""

from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

here = Path(__file__).parent
doc = Document(str(here / "Multimodal_DC_Motor_IEEE_draft.docx"))

lines, n_imgs, n_tables = [], 0, 0
for child in doc.element.body.iterchildren():
    if isinstance(child, CT_P):
        par = Paragraph(child, doc)
        if child.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip"):
            n_imgs += 1
            lines.append("<<IMAGE>>")
        sect = child.findall(".//" + qn("w:sectPr"))
        if sect:
            cols = sect[0].find(qn("w:cols"))
            lines.append(f"<<SECTION BREAK: cols={cols.get(qn('w:num')) if cols is not None else '?'}>>")
        if par.text.strip():
            sizes = {r.font.size.pt for r in par.runs if r.font.size}
            lines.append(f"[{par.alignment}|{sorted(sizes)}] {par.text}")
    elif isinstance(child, CT_Tbl):
        n_tables += 1
        table = Table(child, doc)
        lines.append("=== TABLE ===")
        for row in table.rows:
            lines.append(" | ".join(c.text.strip() for c in row.cells))
        lines.append("=== END TABLE ===")

sec = doc.sections[0]
lines.insert(0, f"page={sec.page_width.inches}x{sec.page_height.inches} "
                f"margins L/R={sec.left_margin.inches}/{sec.right_margin.inches} "
                f"sections={len(doc.sections)} images={n_imgs} tables={n_tables}")
(here / "_ieee_dump.txt").write_text("\n".join(lines), encoding="utf-8")
print(lines[0])
