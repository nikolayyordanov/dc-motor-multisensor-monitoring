"""Render the review PDF and inventory VML/legacy equations, read-only."""
from pathlib import Path
import json
import pymupdf
from docx import Document

OUT = Path(__file__).resolve().parent / "review_lab10"
pdf = pymupdf.open(OUT / "Lab10_review.pdf")
text = []
for index, page in enumerate(pdf):
    page.get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6)).save(OUT / f"page_{index+1:02d}.png")
    text.append(f"PAGE {index+1}\n" + page.get_text())
(OUT / "pdf_text.txt").write_text("\n".join(text), encoding="utf-8")
doc = Document(OUT / "Lab10_review.docx")
items = []
for i, p in enumerate(doc.paragraphs):
    images = p._p.xpath('.//*[local-name()="imagedata"]')
    if images:
        paths = []
        for image in images:
            rel_id = image.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
            if rel_id:
                paths.append(doc.part.rels[rel_id].target_ref)
        items.append({"paragraph": i, "text": p.text, "images": paths})
for i, table in enumerate(doc.tables):
    items.append({"table": i, "text": [[c.text for c in r.cells] for r in table.rows],
                  "image_count": len(table._tbl.xpath('.//*[local-name()="imagedata"]'))})
(OUT / "image_locations.json").write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
print("Rendered", len(pdf), "pages")