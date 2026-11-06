"""Generate Lab10 examples and a targeted, verified separate DOCX revision."""
from copy import deepcopy
import json
from pathlib import Path
import zipfile

from docx import Document
from docx.shared import Inches
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn

from build_lab09_figures import canonical_xml, replace_text, save_revision
from lab10_vibroacoustics import generate, sha

HERE = Path(__file__).resolve().parent
OUT = HERE / "figures_lab10"
SOURCE = HERE / "review_lab10/Lab10_review.docx"


def revise(info):
    original_hash = sha(HERE / "Lab10.doc")
    source_hash = sha(SOURCE)
    doc = Document(SOURCE)
    originals = [(node, deepcopy(node)) for node in doc.element.body]
    objects = [canonical_xml(n) for n in doc.element.body.xpath(".//w:object")]
    edited = set()
    def edit(p, old, new):
        if replace_text(p, old, new):
            edited.add(p._p)
            return True
        return False
    counts = {"speeds": 0, "method": 0, "mean_number": 0, "figures": 0}
    for p in doc.paragraphs:
        if edit(p, "25%, 50%, 75% и 100%", "10%, 20%, 50%, 80% и 100%"):
            counts["speeds"] += 1
        old = "За повишаване на представителността на резултатите се извършват по пет последователни измервания при всяка скорост."
        new = ("При работа с предоставения набор се използват всички налични показания на всяка величина в съответния XLS файл. "
               "Броят им се отчита отделно за всяка величина; това са последователни показания, не независими повторни опити. "
               "При нов студентски опит се записват най-малко пет показания и се отбелязва действителният им брой.")
        if edit(p, old, new):
            counts["method"] += 1
        if edit(p, "При всяка зададена скорост се записват по пет последователни измервания на трите вибрационни величини.",
                "При всяка зададена скорост се използват наличните XLS показания на трите вибрационни величини; при нов опит се записват най-малко пет показания и действителният им брой."):
            counts["method"] += 1
        if edit(p, "При всяка скорост се извършват по пет последователни измервания на вибропреместването, виброскоростта и виброускорението, като се запазват положението и ориентацията на вибрационния датчик.",
                "При всяка скорост се използват наличните XLS показания на вибропреместването, виброскоростта и виброускорението; при нов опит се записват най-малко пет показания, като се запазват положението и ориентацията на вибрационния датчик."):
            counts["method"] += 1
        edit(p, "(m=5) е броят на измерванията", "m е действителният брой показания на разглежданата величина в съответния файл или нов опит")
        edit(p, "неотрицателната част на спектъра", "за неотрицателната част на спектъра (k = 0, …, ⌊N/2⌋)")
    # Identify by neighbouring text, not a fragile formula-object representation.
    paragraphs = doc.paragraphs
    for i, p in enumerate(paragraphs):
        if "(10.6)" in p.text and any("средната аритметична стойност:" in x.text for x in paragraphs[max(0, i-3):i]):
            assert edit(p, "(10.6)", "(10.7)")
            counts["mean_number"] += 1
    caption4 = next(p for p in doc.paragraphs if p.text.startswith("Фиг. 10.4."))
    edit(caption4, caption4.text, caption4.text +
         " Първи WAV канал, интервал 2–6 s, отстранено средно; симетричен прозорец на Хан и корекция чрез сумата му. "
         "Амплитудата е спрямо цифровия пълен обхват (FS), не в калибрирани механични единици; честотна стъпка 0,25 Hz.")
    caption5 = next(p for p in doc.paragraphs if p.text.startswith("Фиг. 10.5."))
    edit(caption5, caption5.text, caption5.text +
         " Първи канал, 50%, интервал 2–6 s от всеки отделен запис, отстранено средно. "
         "STFT: Hann 2048 проби, припокриване 1024; цветът е PSD в dB re 1 FS²/Hz, не SPL. "
         "Еднакви цветни скали за двете състояния в една модалност; WAV/M4A не са синхронни и не са физически амплитудно калибрирани.")
    p = next(p for p in doc.paragraphs if p.text.startswith("За регистриране на непрекъснат вибрационен сигнал"))
    edit(p, p.text, p.text + " WAV пробите от аудиоизхода се използват в цифров пълен обхват (FS); "
         "без калибриране не се преобразуват в mm/s или m/s². Скриптът lab10_vibroacoustics.py "
         "генерира примерните фиг. 10.4–10.5 и vibration_statistics.csv за петте задания; указанията са в README_lab10_bg.md.")
    images = set()
    for element in doc.element.body.xpath(".//w:p"):
        p = Paragraph(element, doc._body)
        stem = None
        if "[Място за фигура" in p.text and "lab9.py" in p.text:
            stem = "fig10_4_amplitude_spectra"
        elif p.text.startswith("[Място за фиг. 10.5"):
            stem = "fig10_5_spectrograms"
        if stem:
            assert not p._p.xpath(".//w:object")
            p.clear()
            p.add_run().add_picture(str(OUT / (stem + ".png")), width=Inches(6.3))
            p.paragraph_format.keep_with_next = True
            images.add(p._p)
            counts["figures"] += 1
    assert counts == {"speeds": 3, "method": 3, "mean_number": 1, "figures": 2}, counts
    assert [canonical_xml(n) for n in doc.element.body.xpath(".//w:object")] == objects
    # Verify all original body elements except explicitly edited paragraphs and images.
    protected = 0
    for node, old in originals:
        affected = any(n in edited or n in images for n in node.iter())
        if not affected:
            assert canonical_xml(node) == canonical_xml(old)
            protected += 1
    target = save_revision(doc, HERE / "Lab10_revised.docx")
    check = Document(target)
    assert [canonical_xml(n) for n in check.element.body.xpath(".//w:object")] == objects
    assert len(check.inline_shapes) == 2
    assert canonical_xml(doc.element.body) == canonical_xml(check.element.body)
    text = "\n".join(p.text for p in check.paragraphs)
    assert text.count("(10.6)") == 1 and text.count("(10.7)") == 2
    assert "25%" not in text and "75%" not in text and "(m=5)" not in text
    with zipfile.ZipFile(SOURCE) as src, zipfile.ZipFile(target) as dst:
        for name in src.namelist():
            if name.startswith(("word/media/", "word/embeddings/")):
                assert src.read(name) == dst.read(name), name
        contents = [dst.read(name) for name in dst.namelist() if name.startswith("word/media/")]
        assert all((OUT / (stem + ".png")).read_bytes() in contents for stem in ("fig10_4_amplitude_spectra", "fig10_5_spectrograms"))
    assert sha(HERE / "Lab10.doc") == original_hash and sha(SOURCE) == source_hash
    assert all(sha(HERE.parent / "DCData_mendeley" / item["path"]) == item["sha256"] for item in info["sources"])
    (OUT / "document_validation.json").write_text(json.dumps({"output": target.name, "changes": counts,
         "legacy_objects_preserved": len(objects), "untouched_body_elements_verified": protected,
         "all_original_media_and_embeddings_byte_identical": True, "original_doc_sha256": original_hash}, indent=2), encoding="utf-8")
    return target


if __name__ == "__main__":
    info = generate(HERE.parent / "DCData_mendeley", OUT)
    target = revise(info)
    with zipfile.ZipFile(HERE / "lab10_vibroacoustics.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("lab10_vibroacoustics.py", "requirements_lab10.txt", "README_lab10_bg.md"):
            archive.write(HERE / name, name)
    print("Saved", target.name, "; Lab10 standalone ZIP created; originals and formulas verified.")