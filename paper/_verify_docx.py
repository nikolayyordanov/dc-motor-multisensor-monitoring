from pathlib import Path
from docx import Document
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.table import Table
from docx.text.paragraph import Paragraph

here = Path(__file__).parent
doc = Document(str(here / "Data_in_Brief_DCData_mendeley.docx"))
lines = []
n_imgs = 0
for child in doc.element.body.iterchildren():
    if isinstance(child, CT_P):
        p = Paragraph(child, doc)
        if p.text.strip():
            lines.append(f"[{p.style.name}] {p.text}")
        if child.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip'):
            n_imgs += 1
            lines.append("<<IMAGE>>")
    elif isinstance(child, CT_Tbl):
        t = Table(child, doc)
        lines.append("=== TABLE ===")
        for row in t.rows:
            lines.append(" | ".join(c.text.strip() for c in row.cells))
        lines.append("=== END TABLE ===")
lines.append(f"\n[TOTAL IMAGES EMBEDDED: {n_imgs}]")
(here / "_generated.txt").write_text("\n".join(lines), encoding="utf-8")
print("lines:", len(lines), "images:", n_imgs)
