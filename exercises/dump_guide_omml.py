"""Dump the OMML XML of the inserted equations in the corrected docx files (for inspection)."""
import zipfile
from pathlib import Path

from lxml import etree

HERE = Path(__file__).resolve().parent
NS = {"m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}
out = []
for name in ["12. ЛУ 8_v.docx", "13. ЛУ 9_v.docx", "14. ЛУ 10_v.docx"]:
    with zipfile.ZipFile(HERE / name) as z:
        root = etree.fromstring(z.read("word/document.xml"))
    for i, om in enumerate(root.xpath("//m:oMath", namespaces=NS), start=1):
        out.append(f"## {name} oMath{i}\n" + etree.tostring(om, pretty_print=True, encoding="unicode")[:3000])
(HERE / "review_guide" / "omml_dump.txt").write_text("\n".join(out), encoding="utf-8")
print("OK")
