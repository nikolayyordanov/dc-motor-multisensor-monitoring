"""Make the inserted inline equations display-sized by editing document.xml.

Word ignores argSz for inline fractions, so runs inside fraction numerators/denominators are enlarged
to compensate for the inline script-size reduction; sum limits are placed under/over.
"""
import shutil
import zipfile
from pathlib import Path

from lxml import etree

HERE = Path(__file__).resolve().parent
FILES = ["12. ЛУ 8_v.docx", "13. ЛУ 9_v.docx", "14. ЛУ 10_v.docx"]
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"m": M, "w": W}
SCALE = 1.4
BASE_HALF_POINTS = 28  # paragraph text is 14 pt in all three files
AFTER_SZ = {"szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign", "rtl", "cs", "em", "lang",
            "eastAsianLayout", "specVanish", "oMath"}


def q(tag, ns=M):
    return f"{{{ns}}}{tag}"


def set_size(rpr, half_points):
    for tag in ("sz", "szCs"):
        el = rpr.find(q(tag, W))
        if el is None:
            el = etree.Element(q(tag, W))
            anchor = next((c for c in rpr if etree.QName(c).localname in AFTER_SZ and
                           not (tag == "szCs" and etree.QName(c).localname == "szCs")), None)
            if tag == "szCs":
                rpr.find(q("sz", W)).addnext(el)
            elif anchor is not None:
                anchor.addprevious(el)
            else:
                rpr.append(el)
        el.set(q("val", W), str(half_points))


def tune(root):
    changes = 0
    for arg_pr in root.xpath("//m:oMath//m:f/*/m:argPr[m:argSz[@m:val='1'] and count(*)=1]", namespaces=NS):
        arg_pr.getparent().remove(arg_pr)
    # a stacked fraction of sums is unreadable inline: use a linear (slashed) fraction instead
    for frac in root.xpath("//m:oMath//m:f[.//m:nary]", namespaces=NS):
        pr = frac.find(q("fPr"))
        if pr is None:
            pr = etree.Element(q("fPr"))
            frac.insert(0, pr)
        typ = pr.find(q("type"))
        if typ is None:
            typ = etree.Element(q("type"))
            pr.insert(0, typ)
        typ.set(q("val"), "lin")
        changes += 1
    for rpr in root.xpath("//m:oMath//w:rPr", namespaces=NS):
        in_frac = bool(rpr.xpath("(ancestor::m:num or ancestor::m:den) and not(ancestor::m:sub or ancestor::m:sup)"
                                 " and not(ancestor::m:f[.//m:nary])", namespaces=NS))
        set_size(rpr, round(BASE_HALF_POINTS * SCALE) if in_frac else BASE_HALF_POINTS)
        changes += 1
    for nary in root.xpath("//m:oMath//m:nary", namespaces=NS):
        pr = nary.find(q("naryPr"))
        if pr is None:
            pr = etree.Element(q("naryPr"))
            nary.insert(0, pr)
        loc = pr.find(q("limLoc"))
        if loc is None:
            loc = etree.Element(q("limLoc"))
            pr.insert(1 if pr.find(q("chr")) is not None else 0, loc)
        want = "subSup" if nary.xpath("ancestor::m:f", namespaces=NS) else "undOvr"
        if loc.get(q("val")) != want:
            loc.set(q("val"), want)
            changes += 1
    return changes


def main():
    for name in FILES:
        path = HERE / name
        tmp = path.with_suffix(".tmp")
        with zipfile.ZipFile(path) as src:
            root = etree.fromstring(src.read("word/document.xml"))
            changes = tune(root)
            xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            with zipfile.ZipFile(tmp, "w") as dst:
                for item in src.infolist():
                    data = xml if item.filename == "word/document.xml" else src.read(item.filename)
                    dst.writestr(item, data, compress_type=item.compress_type)
        shutil.move(tmp, path)
        print(name, "changes", changes)


if __name__ == "__main__":
    main()
