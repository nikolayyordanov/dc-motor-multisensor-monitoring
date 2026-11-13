"""Dump characters from Equation.3 'Equation Native' (MTEF v3) streams in a legacy .doc, to locate equations by content."""
import sys
from pathlib import Path

import olefile

HERE = Path(__file__).resolve().parent


def mtef_chars(data: bytes) -> str:
    # Equation Native: 28-byte header (cbHdr at offset 0), then MTEF; CHAR records = tag 2 (+options), typeface, 16-bit char
    hdr = int.from_bytes(data[0:2], "little")
    m = data[hdr:]
    out = []
    i = 5  # MTEF v3 header: version, platform, product, product version, sub-version
    while i < len(m):
        tag = m[i] & 0x0F
        opts = m[i] >> 4
        i += 1
        if tag == 0:
            out.append("}")
            continue
        if tag == 1:  # LINE
            if opts & 0x1:
                i += 1  # nudge (approx)
            if opts & 0x4:
                i += 1
            continue
        if tag == 2:  # CHAR
            if opts & 0x8:
                i += 2
            typeface = m[i]
            ch = int.from_bytes(m[i + 1:i + 3], "little")
            i += 3
            out.append(chr(ch) if ch else "?")
            continue
        if tag == 3:  # TMPL
            if opts & 0x8:
                i += 2
            sel, var = m[i], m[i + 1]
            i += 3
            out.append(f"[T{sel}.{var}:")
            continue
        if tag == 4:  # PILE
            if opts & 0x8:
                i += 2
            i += 2
            out.append("[P:")
            continue
        if tag == 5:  # MATRIX
            out.append("[MATRIX]")
            break
        if tag == 6:  # EMBELL
            if opts & 0x8:
                i += 2
            i += 1
            out.append("~")
            continue
        if tag in (10, 11, 12, 13, 14):
            continue
        if tag == 8:  # FONT: typeface, style, null-terminated name
            i += 2
            while i < len(m) and m[i] != 0:
                i += 1
            i += 1
            continue
        if tag in (7, 9, 15):
            out.append(f"<tag{tag}>")
            break
    return "".join(out)


def main():
    path = HERE / sys.argv[1]
    lines = []
    if path.suffix.lower() == ".docx":
        import io
        import zipfile
        with zipfile.ZipFile(path) as z:
            for name in sorted(n for n in z.namelist() if n.startswith("word/embeddings/") and n.endswith(".bin")):
                ole = olefile.OleFileIO(io.BytesIO(z.read(name)))
                if ole.exists("Equation Native"):
                    lines.append(f"{name} {mtef_chars(ole.openstream('Equation Native').read())[:160]}")
    else:
        ole = olefile.OleFileIO(str(path))
        for entry in ole.listdir():
            if entry[-1] == "Equation Native":
                data = ole.openstream(entry).read()
                lines.append(f"{'/'.join(entry[:-1])} {mtef_chars(data)[:160]}")
    (HERE / "review_guide" / f"eq_{path.stem}.txt").write_text("\n".join(lines), encoding="utf-8")
    print("OK", len(lines))


if __name__ == "__main__":
    main()
