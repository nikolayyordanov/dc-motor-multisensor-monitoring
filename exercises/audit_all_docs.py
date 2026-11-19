"""Audit images (format, pixel size, display size, effective DPI) and body font size in exercises/ALL/*.doc."""
import io
import zipfile
from collections import Counter
from pathlib import Path
from lxml import etree
from PIL import Image
import win32com.client

HERE = Path(__file__).resolve().parent
ALL_DIR = HERE / "ALL"
TMP = HERE / "review_guide" / "tmp_all_docx"
OUT = HERE / "review_guide" / "all_doc_audit.txt"
TMP.mkdir(parents=True, exist_ok=True)
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "v": "urn:schemas-microsoft-com:vml",
}


def audit_docx(docx_path: Path):
    sizes = Counter()
    media_info = []
    with zipfile.ZipFile(docx_path) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        for p in root.xpath("//w:body/w:p", namespaces=NS):
            txt = "".join(p.xpath(".//w:t/text()", namespaces=NS)).strip()
            if len(txt) > 30:
                szs = p.xpath(".//w:rPr/w:sz/@w:val", namespaces=NS)
                for s in szs[:1]:
                    sizes[int(s) / 2] += 1
        # Collect displayed sizes from drawingml (wp:extent in EMUs: 914400 per inch) or VML style
        boxes = []
        for ext in root.xpath("//wp:inline/wp:extent | //wp:anchor/wp:extent", namespaces=NS):
            cx = int(ext.get("cx", 0)) / 914400.0
            cy = int(ext.get("cy", 0)) / 914400.0
            boxes.append((cx, cy))
        for name in sorted(z.namelist()):
            if name.startswith("word/media/"):
                data = z.read(name)
                ext = Path(name).suffix.lower()
                dims = "?"
                w_px = h_px = 0
                try:
                    im = Image.open(io.BytesIO(data))
                    w_px, h_px = im.width, im.height
                    dims = f"{w_px}x{h_px}px"
                except Exception:
                    pass
                media_info.append((Path(name).name, ext, len(data) // 1024, dims, w_px, h_px))
    return dict(sizes), boxes, media_info


def main():
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    lines = []
    try:
        for path in sorted(ALL_DIR.glob("*.doc")):
            docx_path = TMP / (path.stem + ".docx")
            if not docx_path.exists():
                doc = word.Documents.Open(str(path), ReadOnly=True, AddToRecentFiles=False)
                try:
                    doc.SaveAs2(str(docx_path), FileFormat=16)
                finally:
                    doc.Close(SaveChanges=0)
            sizes, boxes, media_info = audit_docx(docx_path)
            lines.append(f"=== {path.name} | body_font_pt={sizes} | media={len(media_info)} | boxes={len(boxes)} ===")
            for idx, (mname, ext, kb, dims, w_px, h_px) in enumerate(media_info):
                box_s = f"{boxes[idx][0]*2.54:.1f}x{boxes[idx][1]*2.54:.1f}cm" if idx < len(boxes) else "?"
                dpi_s = f"{w_px/boxes[idx][0]:.0f}dpi" if (idx < len(boxes) and w_px and boxes[idx][0] > 0) else ""
                lines.append(f"  {mname} ({ext}, {kb}KB, {dims}) box={box_s} {dpi_s}")
    finally:
        word.Quit()
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("OK", len(lines))


if __name__ == "__main__":
    main()
