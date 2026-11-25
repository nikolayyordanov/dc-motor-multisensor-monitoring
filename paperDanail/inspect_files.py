"""Inspect the three DOCX files in paperDanail: manuscript, review, and IJAME template."""
import zipfile
from pathlib import Path
from docx import Document
from lxml import etree

HERE = Path(__file__).resolve().parent
OUT = HERE / "_inspect"
OUT.mkdir(exist_ok=True)

FILES = [
    ("manuscript", "IJOMAM-2026_4_Zhilevski_2.docx"),
    ("review", "69.docx"),
    ("template", "Template IJAME 2026-OTH.docx"),
]

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "o": "urn:schemas-microsoft-com:office:office",
}


def dump_docx(label: str, filename: str):
    path = HERE / filename
    doc = Document(path)
    lines = [f"=== {filename} ==="]
    lines.append(f"Paragraphs: {len(doc.paragraphs)} | Tables: {len(doc.tables)} | Sections: {len(doc.sections)}")

    # Section layout info
    for idx, sec in enumerate(doc.sections, 1):
        lines.append(
            f"  Section {idx}: {sec.page_width.cm:.2f}x{sec.page_height.cm:.2f} cm, "
            f"margins L={sec.left_margin.cm:.2f} R={sec.right_margin.cm:.2f} "
            f"T={sec.top_margin.cm:.2f} B={sec.bottom_margin.cm:.2f}"
        )

    # Media / equations / OLE in zip
    with zipfile.ZipFile(path) as z:
        media = [n for n in z.namelist() if n.startswith("word/media/")]
        embeds = [n for n in z.namelist() if n.startswith("word/embeddings/")]
        root = etree.fromstring(z.read("word/document.xml"))
        omaths = len(root.xpath("//m:oMath", namespaces=NS))
        oles = root.xpath("//o:OLEObject/@ProgID", namespaces=NS)
        lines.append(f"  Media: {len(media)} | Embeddings: {len(embeds)} | OMaths: {omaths} | OLEs: {set(oles)}")

    lines.append("\n--- PARAGRAPHS ---")
    for idx, p in enumerate(doc.paragraphs):
        txt = p.text.strip()
        has_math = bool(p._element.xpath(".//*[local-name()='oMath']"))
        has_pic = bool(p._element.xpath(".//*[local-name()='blip' or local-name()='imagedata']"))
        has_ole = bool(p._element.xpath(".//*[local-name()='OLEObject']"))
        tags = []
        if has_math:
            tags.append("MATH")
        if has_pic:
            tags.append("PIC")
        if has_ole:
            tags.append("OLE")
        tag_s = f" [{','.join(tags)}]" if tags else ""
        if txt or tags:
            lines.append(f"P{idx:03d} ({p.style.name}){tag_s}: {txt}")

    if doc.tables:
        lines.append("\n--- TABLES ---")
        for ti, tbl in enumerate(doc.tables):
            lines.append(f"Table {ti} ({len(tbl.rows)}x{len(tbl.columns)}):")
            for ri, row in enumerate(tbl.rows):
                cells = [c.text.strip().replace("\n", " / ") for c in row.cells]
                lines.append(f"  R{ri:02d}: " + " | ".join(cells))

    (OUT / f"{label}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"OK {label}: {len(lines)} lines")


def main():
    for label, fn in FILES:
        dump_docx(label, fn)


if __name__ == "__main__":
    main()
