"""Inspect the exact contents of PBrush embeddings vs normal raster media in Labs 1-10."""
import io
import struct
import zipfile
from pathlib import Path
from lxml import etree
from PIL import Image
import olefile

TMP = Path(__file__).resolve().parent / "review_guide" / "tmp_all_docx"
OUT = Path(__file__).resolve().parent / "review_guide" / "pbrush_deep_audit.txt"
NS = {
    "o": "urn:schemas-microsoft-com:office:office",
    "v": "urn:schemas-microsoft-com:vml",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


def inspect_pbrush_bin(raw: bytes) -> str:
    try:
        ole = olefile.OleFileIO(io.BytesIO(raw))
        streams = ["/".join(s) for s in ole.listdir()]
        for s in ole.listdir():
            data = ole.openstream(s).read()
            idx = data.find(b"BM")
            if idx != -1 and idx + 26 <= len(data):
                # Check DIB header size (40 = BITMAPINFOHEADER)
                hdr_sz = struct.unpack_from("<I", data, idx + 14)[0]
                if hdr_sz in (12, 40, 108, 124):
                    w, h = struct.unpack_from("<ii", data, idx + 18)
                    bpp = struct.unpack_from("<H", data, idx + 28)[0]
                    return f"BMP {w}x{abs(h)}px {bpp}bpp (streams={streams})"
        return f"streams={streams} len={len(raw)}"
    except Exception as e:
        return f"non-ole ({e}) len={len(raw)}"


lines = []
for path in sorted(TMP.glob("*.docx")):
    if path.name.startswith("~$"):
        continue
    with zipfile.ZipFile(path) as z:
        rels = etree.fromstring(z.read("word/_rels/document.xml.rels"))
        rel_map = {r.get("Id"): r.get("Target") for r in rels}
        root = etree.fromstring(z.read("word/document.xml"))

        # Find all shapes/drawings that are figures (excluding tiny Equation objects)
        pbrush_items = []
        for ole_el in root.xpath("//o:OLEObject[@ProgID='PBrush']", namespaces=NS):
            rid = ole_el.get(f"{{{NS['r']}}}id")
            target = "word/" + rel_map.get(rid, "")
            parent = ole_el.getparent()
            imagedata = parent.xpath(".//v:imagedata", namespaces=NS)
            img_rid = imagedata[0].get(f"{{{NS['r']}}}id") if imagedata else None
            img_target = "word/" + rel_map.get(img_rid, "") if img_rid else None
            preview_dims = "?"
            if img_target and img_target in z.namelist():
                im = Image.open(io.BytesIO(z.read(img_target)))
                preview_dims = f"{im.width}x{im.height}px"
            bmp_info = inspect_pbrush_bin(z.read(target)) if target in z.namelist() else "missing"
            pbrush_items.append((Path(target).name, preview_dims, bmp_info))

        # Normal non-OLE pictures (v:imagedata without OLEObject sibling, or a:blip)
        normal_pics = []
        for imdata in root.xpath("//v:shape[not(following-sibling::o:OLEObject)]/v:imagedata", namespaces=NS):
            rid = imdata.get(f"{{{NS['r']}}}id")
            target = "word/" + rel_map.get(rid, "")
            if target in z.namelist() and not target.endswith((".wmf", ".emf")):
                im = Image.open(io.BytesIO(z.read(target)))
                if im.width > 80 or im.height > 80:
                    normal_pics.append(f"{Path(target).name}:{im.width}x{im.height}px")
        for blip in root.xpath("//a:blip", namespaces=NS):
            rid = blip.get(f"{{{NS['r']}}}embed")
            target = "word/" + rel_map.get(rid, "")
            if target in z.namelist() and not target.endswith((".wmf", ".emf")):
                im = Image.open(io.BytesIO(z.read(target)))
                if im.width > 80 or im.height > 80:
                    normal_pics.append(f"{Path(target).name}:{im.width}x{im.height}px")

        lines.append(f"=== {path.name}: PBrush={len(pbrush_items)} | Normal_figures={len(normal_pics)} ===")
        for bname, prev, binfo in pbrush_items[:5]:
            lines.append(f"  [PBrush {bname}] preview={prev} | native={binfo}")
        if len(pbrush_items) > 5:
            lines.append(f"  ... (+{len(pbrush_items)-5} more PBrush)")
        for npic in normal_pics:
            lines.append(f"  [Normal] {npic}")

OUT.write_text("\n".join(lines), encoding="utf-8")
print("OK")
