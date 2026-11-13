"""Apply the review corrections to the Lab 8/9/10 and Appendix 1 Word files with Track Changes.

Originals are copied to archive_before_guide_fixes/ first. Lab 9 and Lab 10 are saved as new .docx files
(native equations need a non-compatibility document); the original .doc files stay unchanged.
Use --dry-run to only check that every anchor is found exactly once.
"""
import shutil
import sys
from pathlib import Path

import win32com.client

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE / "archive_before_guide_fixes"
LOG = HERE / "review_guide" / "apply_log.txt"
DRY = "--dry-run" in sys.argv
WD_FIELD_EMBED, WD_FIELD_QUOTE = 58, 35
FORMAT_DOCX, COMPAT_CURRENT = 16, 65535

log: list[str] = []


class Abort(Exception):
    pass


def occurrences(doc, text, within=None):
    rng = (within or doc.Content).Duplicate
    end = rng.End
    found = []
    f = rng.Find
    f.ClearFormatting()
    f.Text = text
    f.Forward = True
    f.Wrap = 0
    f.MatchCase = True
    f.MatchWildcards = False
    while f.Execute() and rng.End <= end:
        found.append((rng.Start, rng.End))
        rng.Collapse(0)
    return found


def unique(doc, text, within=None):
    hits = occurrences(doc, text, within)
    if len(hits) != 1:
        raise Abort(f"expected 1 match, got {len(hits)}: {text!r}")
    return doc.Range(*hits[0])


def replace_text(doc, old, new, within=None):
    rng = unique(doc, old, within)
    p = 0
    while p < min(len(old), len(new)) and old[p] == new[p]:
        p += 1
    s = 0
    while s < min(len(old), len(new)) - p and old[-1 - s] == new[-1 - s]:
        s += 1
    log.append(f"  replace {old!r} -> {new!r}")
    if not DRY:
        doc.Range(rng.Start + p, rng.End - s).Text = new[p:len(new) - s]


def paragraph(doc, anchor):
    rng = unique(doc, anchor)
    return rng.Paragraphs(1).Range


def field_in(para, field_type, index=1):
    fields = [para.Fields(i) for i in range(1, para.Fields.Count + 1) if para.Fields(i).Type == field_type]
    if len(fields) < index:
        raise Abort(f"field type {field_type} #{index} not found in paragraph {para.Text[:60]!r}")
    return fields[index - 1]


def replace_field_with_equation(doc, para, field_type, linear, index=1):
    field = field_in(para, field_type, index)
    log.append(f"  equation: field type {field_type} #{index} -> {linear}")
    if DRY:
        return
    size = para.Font.Size if para.Font.Size < 1000 else 14
    start = field.Code.Start - 1
    rng = doc.Range(start, start)
    rng.Text = linear
    rng.Font.Size = size
    math = doc.OMaths.Add(rng)
    math.OMaths(1).BuildUp()
    field.Delete()


def lab8(doc):
    replace_field_with_equation(doc, paragraph(doc, "Дискретният измерен сигнал"), WD_FIELD_QUOTE, "x[n]")
    para = paragraph(doc, "броят на отчетите е")
    replace_field_with_equation(doc, para, WD_FIELD_EMBED, "N=T_w f_s=22050", index=3)
    replace_field_with_equation(doc, paragraph(doc, "(8.8)"), WD_FIELD_EMBED,
                                "E_(b,m)=(∑_(k∈B_b)▒〖|X_m [k]|^2〗)/(∑_(k=0)^(N-1)▒〖|X_m [k]|^2〗)")
    replace_text(doc, "е нормализираният спектрален показател за b-тата", "е относителната мощност в b-тата")
    rng = unique(doc, "принадлежащи на съответната честотна лента.")
    log.append("  append sentence after band definition")
    if not DRY:
        rng.Collapse(0)
        rng.InsertAfter(" Спектралните коефициенти се определят след отстраняване на средната стойност "
                        "и прилагане на прозорец на Хан, а знаменателят обхваща всички честотни съставки.")
    replace_text(doc, "скрипта lab8.py в архив lab08_ml.zip",
                 "скрипта lab8/lab8_ml.py от архива labs_8_9_10_software_v1.0.zip")
    replace_text(doc, "се използва групова кръстосана проверка (GroupKFold)",
                 "се използва стратифицирана групова кръстосана проверка с пет дяла (StratifiedGroupKFold)")
    rng = unique(doc, "едновременно за обучение и оценяване.")
    log.append("  append record-level sentence")
    if not DRY:
        rng.Collapse(0)
        rng.InsertAfter(" Класът на всеки запис се определя чрез мнозинство от предсказанията за неговите "
                        "прозорци; показателите в табл. 8.2 и 8.3 и матриците на фиг. 8.4 са изчислени "
                        "за 36 записа (по 9 за всяко състояние).")
    replace_text(doc, "Фиг. 10.4. Матрици на объркванията", "Фиг. 8.4. Матрици на объркванията")


def lab9(doc):
    replace_text(doc, "параметрите на котвената верига..", "параметрите на котвената верига.")
    replace_field_with_equation(doc, paragraph(doc, "(9.6)"), WD_FIELD_EMBED, "f_r=ω/(2π)")
    para = paragraph(doc, "е броя на отчета, умножен с прозорецът на Хан")
    replace_field_with_equation(doc, para, WD_FIELD_QUOTE, "N", index=2)
    replace_text(doc, "е броя на отчета, умножен с прозорецът на Хан", "отчета, умножен с прозореца на Хан")
    replace_text(doc, ", а ", ", съдържащ ", within=para)
    replace_field_with_equation(doc, paragraph(doc, "(9.10)"), WD_FIELD_EMBED,
                                "I_rms=√(1/N ∑_(n=0)^(N-1)▒〖(x[n]-x̅)〗^2 )")
    replace_text(doc, "plot_lab_current.py и указанията README_figures_bg.md, споделяни към Приложение 2",
                 "lab9/plot_lab_current.py от архива към Приложение 1 (указания в README_START_BG.md)")


def lab10(doc):
    replace_field_with_equation(doc, paragraph(doc, "(10.1)"), WD_FIELD_EMBED, "f_r=ω/(2π)")
    old = "Скриптът lab10_vibroacoustics.py генерира"
    replace_text(doc, old, "Скриптът lab10/lab10_vibroacoustics.py (Приложение 1) генерира")
    rng = unique(doc, "указанията са в README_lab10_bg.md")
    nxt = rng.Paragraphs(1).Next()
    replace_text(doc, "указанията са в README_lab10_bg.md", "указанията са в README_START_BG.md.")
    if nxt is not None and nxt.Range.Text.strip() == ".":
        log.append("  delete stray '.' paragraph")
        if not DRY:
            nxt.Range.Delete()
    replace_text(doc, "1 Кои са основните източници на вибрации", "1. Кои са основните източници на вибрации")


def appendix1(doc):
    replace_text(doc, "[ПОПЪЛВА СЕ С АДРЕСА НА ПУБЛИКУВАНИЯ НАБОР]",
                 "https://doi.org/10.17632/g28trvywnx.1, версия 1")
    for text in ("Адресът на набора от измервания ще се попълни допълнително. ",
                 "Адресът на набора от измервания ще се попълни допълнително."):
        if occurrences(doc, text):
            log.append(f"  delete {text!r}")
            if not DRY:
                unique(doc, text).Text = ""
            break


JOBS = [("12. ЛУ 8_v.docx", None, lab8), ("13. ЛУ 9_v.doc", "13. ЛУ 9_v.docx", lab9),
        ("14. ЛУ 10_v.doc", "14. ЛУ 10_v.docx", lab10), ("17. Приложение 1 (1).doc", None, appendix1)]


def backup():
    ARCHIVE.mkdir(exist_ok=True)
    for name, _, _ in JOBS:
        src, dst = HERE / name, ARCHIVE / name
        if dst.exists():
            if dst.read_bytes() != src.read_bytes():
                raise Abort(f"backup differs from current file, refusing to overwrite: {dst}")
        else:
            shutil.copy2(src, dst)
    for _, new, _ in JOBS:
        if new and (HERE / new).exists():
            raise Abort(f"target already exists: {new}")


def main():
    if not DRY:
        backup()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    ok = True
    try:
        for name, new, job in JOBS:
            log.append(f"## {name}")
            doc = word.Documents.Open(str(HERE / name), ReadOnly=DRY, AddToRecentFiles=False)
            try:
                if not DRY and doc.ReadOnly:
                    raise Abort(f"{name} opened read-only (open in Word?)")
                if not DRY and new:
                    doc.SaveAs2(str(HERE / new), FileFormat=FORMAT_DOCX, CompatibilityMode=COMPAT_CURRENT)
                    log.append(f"  saved as {new} (compat {doc.CompatibilityMode})")
                log.append(f"  compat={doc.CompatibilityMode} revisions_before={doc.Revisions.Count}")
                if not DRY and name.endswith(".docx") and doc.CompatibilityMode < 12:
                    raise Abort("Lab 8 is in Word 2003 compatibility mode; equations unavailable")
                doc.TrackRevisions = not DRY
                job(doc)
                if not DRY:
                    doc.Save()
                    log.append(f"  saved; revisions={doc.Revisions.Count} omaths={doc.OMaths.Count}")
            except Abort as exc:
                ok = False
                log.append(f"  ABORT: {exc}")
            finally:
                doc.Close(SaveChanges=0)
    finally:
        word.Quit()
        LOG.write_text("\n".join(log), encoding="utf-8")
    print("OK" if ok else "ERRORS", LOG)


if __name__ == "__main__":
    main()
