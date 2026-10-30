"""Read-only inspection of yellow figure requests in the ML documents."""
from pathlib import Path
import json
import zipfile
from lxml import etree

HERE = Path(__file__).resolve().parent
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
report = []
for path in (HERE / "Lab08_revised.docx", HERE / "Lab08_working.docx"):
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    paragraphs = root.xpath("//w:p", namespaces=NS)
    rows = []
    for i, p in enumerate(paragraphs):
        yellow = p.xpath('.//w:highlight[@w:val="yellow"] | .//w:shd[@w:fill="FFFF00" or @w:fill="ffff00"]', namespaces=NS)
        if yellow:
            rows.append({"index": i, "text": "".join(p.xpath(".//w:t/text()", namespaces=NS)),
                         "previous": "".join(paragraphs[max(0, i-1)].xpath(".//w:t/text()", namespaces=NS)),
                         "next": "".join(paragraphs[min(len(paragraphs)-1, i+1)].xpath(".//w:t/text()", namespaces=NS)),
                         "xml": etree.tostring(p, encoding="unicode")})
    report.append({"file": path.name, "highlights": rows})
(HERE / "figure_highlights_inspection.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print([(r["file"], len(r["highlights"])) for r in report])