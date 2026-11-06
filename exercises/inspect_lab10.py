"""Read-only Lab10 review: separate DOCX/PDF, text and embedded equations."""
from pathlib import Path
import hashlib
import json
import zipfile
import win32com.client
from docx import Document
from lxml import etree

HERE = Path(__file__).resolve().parent
OUT = HERE / "review_lab10"
OUT.mkdir(exist_ok=True)
source = HERE / "Lab10.doc"
before = hashlib.sha256(source.read_bytes()).hexdigest()
target = OUT / "Lab10_review.docx"
word = win32com.client.DispatchEx("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
try:
    doc = word.Documents.Open(str(source), ReadOnly=True, AddToRecentFiles=False)
    try:
        doc.SaveAs2(str(target), FileFormat=16, AddToRecentFiles=False)
        doc.ExportAsFixedFormat(str(OUT / "Lab10_review.pdf"), 17)
    finally:
        doc.Close(SaveChanges=0)
finally:
    word.Quit()
assert hashlib.sha256(source.read_bytes()).hexdigest() == before
doc = Document(target)
lines = [f"P{i}: {p.text}" for i, p in enumerate(doc.paragraphs)]
for i, table in enumerate(doc.tables):
    lines.append(f"TABLE {i}")
    lines.extend(" | ".join(cell.text for cell in row.cells) for row in table.rows)
(OUT / "source_text.txt").write_text("\n".join(lines), encoding="utf-8")
formula_lines = []
for i, p in enumerate(doc.paragraphs):
    for math in p._p.xpath(".//m:oMath"):
        formula_lines.append(f"P{i}: " + etree.tostring(math, encoding="unicode"))
(OUT / "formula_xml.txt").write_text("\n".join(formula_lines), encoding="utf-8")
with zipfile.ZipFile(target) as archive:
    media = []
    for name in archive.namelist():
        if name.startswith(("word/media/", "word/embeddings/")):
            path = OUT / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(name))
            media.append(name)
report = {"source_sha256": before, "source_unchanged": True,
          "paragraphs": len(doc.paragraphs), "tables": len(doc.tables),
          "inline_shapes": len(doc.inline_shapes),
          "omml_count": len(doc.element.body.xpath(".//m:oMath")),
          "legacy_objects": len(doc.element.body.xpath(".//w:object")), "media": media}
(OUT / "inspection.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in report.items() if key != "media"}))