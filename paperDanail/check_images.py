"""Check image resolutions in IJOMAM-2026_4_Zhilevski_2.docx."""
import io
import zipfile
from pathlib import Path
from PIL import Image

p = Path(__file__).resolve().parent / "IJOMAM-2026_4_Zhilevski_2.docx"
with zipfile.ZipFile(p) as z:
    for n in sorted(z.namelist()):
        if n.startswith("word/media/"):
            data = z.read(n)
            im = Image.open(io.BytesIO(data))
            print(f"{n}: {im.width}x{im.height}px, mode={im.mode}, dpi={im.info.get('dpi')}, {len(data)//1024}KB")
