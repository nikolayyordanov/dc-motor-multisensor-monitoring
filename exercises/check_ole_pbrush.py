"""Check whether figures in exercises/ALL/*.doc are PBrush/Paintbrush OLE objects or normal pictures."""
import zipfile
from collections import Counter
from pathlib import Path
from lxml import etree

TMP = Path(__file__).resolve().parent / "review_guide" / "tmp_all_docx"
OUT = Path(__file__).resolve().parent / "review_guide" / "ole_check.txt"
NS = {"o": "urn:schemas-microsoft-com:office:office", "v": "urn:schemas-microsoft-com:vml"}

lines = []
for path in sorted(TMP.glob("*.docx")):
    if path.name.startswith("~$"):
        continue
    with zipfile.ZipFile(path) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        progs = Counter(root.xpath("//o:OLEObject/@ProgID", namespaces=NS))
        embeds = [n for n in z.namelist() if n.startswith("word/embeddings/")]
        pngs = [n for n in z.namelist() if n.startswith("word/media/") and n.endswith((".png", ".jpg", ".jpeg", ".bmp"))]
        lines.append(f"{path.name}: ProgIDs={dict(progs)} | embeddings={len(embeds)} | raster_media={len(pngs)}")

OUT.write_text("\n".join(lines), encoding="utf-8")
print("OK")
