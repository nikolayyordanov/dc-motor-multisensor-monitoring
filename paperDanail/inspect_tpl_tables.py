"""Inspect XML structure of the 3 tables in Template IJAME 2026-OTH.docx."""
from pathlib import Path
from docx import Document

HERE = Path(__file__).resolve().parent
doc = Document(HERE / "Template IJAME 2026-OTH.docx")
out = []
for i, t in enumerate(doc.tables):
    out.append(f"=== TABLE {i} ({len(t.rows)}x{len(t.columns)}) style={t.style.name if t.style else None} ===")
    out.append(t._tbl.xml[:2500])
(HERE / "_inspect" / "template_tables_xml.txt").write_text("\n".join(out), encoding="utf-8")
print("OK")
