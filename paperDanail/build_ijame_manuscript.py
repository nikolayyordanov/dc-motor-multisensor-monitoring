"""Build the revised manuscript in the IJAME 2026 template, marking new/clarified/proposed parts in red for review."""
import copy
import re
from pathlib import Path
from PIL import Image
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Inches, Pt, RGBColor

HERE = Path(__file__).resolve().parent
TPL = HERE / "Template IJAME 2026-OTH.docx"
FIGS = HERE / "_inspect" / "figs"
OUT = HERE / "IJAME_2026_Slavov_Zhilevski.docx"

RED = RGBColor(0xC0, 0x00, 0x00)
BLACK = RGBColor(0x00, 0x00, 0x00)


def set_cell_margins(cell, top=40, bottom=40, left=80, right=80):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for m, val in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        node = OxmlElement(f"w:{m}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        tcMar.append(node)
    tcPr.append(tcMar)


def set_table_borders_booktabs(table):
    tblPr = table._tbl.tblPr
    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        '<w:top w:val="single" w:sz="8" w:space="0" w:color="000000"/>'
        '<w:bottom w:val="single" w:sz="8" w:space="0" w:color="000000"/>'
        '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        '<w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        '<w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        "</w:tblBorders>"
    )
    tblPr.append(borders)


def set_row_bottom_border(row, sz=6):
    for cell in row.cells:
        tcPr = cell._tc.get_or_add_tcPr()
        old = tcPr.find(qn("w:tcBorders"))
        if old is not None:
            tcPr.remove(old)
        b = parse_xml(
            f'<w:tcBorders {nsdecls("w")}>'
            f'<w:bottom w:val="single" w:sz="{sz}" w:space="0" w:color="000000"/>'
            "</w:tcBorders>"
        )
        tcPr.append(b)


def set_table_borderless(table):
    tblPr = table._tbl.tblPr
    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        '<w:top w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        '<w:bottom w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        '<w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        '<w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        "</w:tblBorders>"
    )
    tblPr.append(borders)


def add_rich_runs(p, segments, size=10):
    """Add runs from a list of tuples: (text, kwargs) where kwargs may include red, italic, bold, sup, sub."""
    for seg in segments:
        if isinstance(seg, str):
            text, kw = seg, {}
        else:
            text, kw = seg[0], seg[1]
        r = p.add_run(text)
        r.font.name = "Times New Roman"
        if size is not None:
            r.font.size = Pt(size)
        if kw.get("bold"):
            r.bold = True
        if kw.get("italic"):
            r.italic = True
        if kw.get("sup"):
            r.font.superscript = True
        if kw.get("sub"):
            r.font.subscript = True
        if kw.get("red"):
            r.font.color.rgb = RED


def add_heading1(doc, text, red=False):
    p = doc.add_paragraph(style="Content")
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.first_line_indent = Cm(0)
    r = p.add_run(text)
    r.bold = True
    r.font.name = "Times New Roman"
    if red:
        r.font.color.rgb = RED
    return p


def add_heading2(doc, text, red=False):
    p = doc.add_paragraph(style="Content")
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.first_line_indent = Cm(0)
    r = p.add_run(text)
    r.bold = True
    r.font.name = "Times New Roman"
    if red:
        r.font.color.rgb = RED
    return p


def add_body(doc, segments, first=False, before_heading=False):
    p = doc.add_paragraph(style="Content")
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Cm(0) if first else Cm(0.5)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(6) if before_heading else Pt(0)
    add_rich_runs(p, segments, size=None)
    return p


def add_equation_row(doc, omml_inner: str, num: int, red=False):
    tbl = doc.add_table(rows=1, cols=2)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borderless(tbl)
    c0, c1 = tbl.rows[0].cells
    c0.width = Cm(15.2)
    c1.width = Cm(1.8)
    set_cell_margins(c0, top=40, bottom=40, left=0, right=40)
    set_cell_margins(c1, top=40, bottom=40, left=40, right=0)

    p0 = c0.paragraphs[0]
    p0.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p0.paragraph_format.space_before = Pt(4)
    p0.paragraph_format.space_after = Pt(4)
    omath = parse_xml(
        f'<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        f'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">{omml_inner}</m:oMath>'
    )
    if red:
        for rpr in omath.xpath(".//w:rPr", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}):
            c = OxmlElement("w:color")
            c.set(qn("w:val"), "C00000")
            rpr.append(c)
    p0._p.append(omath)

    p1 = c1.paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p1.paragraph_format.space_before = Pt(4)
    p1.paragraph_format.space_after = Pt(4)
    r = p1.add_run(f"({num})")
    r.font.name = "Times New Roman"
    r.font.size = Pt(10)
    if red:
        r.font.color.rgb = RED


def mr(text, roman=False):
    sty = '<m:rPr><m:sty m:val="p"/></m:rPr>' if roman else ""
    return f'<m:r>{sty}<w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/><w:sz w:val="20"/></w:rPr><m:t>{text}</m:t></m:r>'


def msub(base, sub):
    return f"<m:sSub><m:sSubPr/><m:e>{base}</m:e><m:sub>{sub}</m:sub></m:sSub>"


def mfrac(num, den):
    return f"<m:f><m:fPr/><m:num>{num}</m:num><m:den>{den}</m:den></m:f>"


def mnary(chr_val, sub, sup, body):
    return (
        f'<m:nary><m:naryPr><m:chr m:val="{chr_val}"/><m:limLoc m:val="undOvr"/></m:naryPr>'
        f"<m:sub>{sub}</m:sub><m:sup>{sup}</m:sup><m:e>{body}</m:e></m:nary>"
    )


def add_figure(doc, img_name: str, caption_segments, width_cm: float):
    img_path = FIGS / img_name
    p_img = doc.add_paragraph(style="Content")
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_img.paragraph_format.first_line_indent = Cm(0)
    p_img.paragraph_format.space_before = Pt(6)
    p_img.paragraph_format.space_after = Pt(2)
    p_img.paragraph_format.keep_with_next = True
    run = p_img.add_run()
    run.add_picture(str(img_path), width=Cm(width_cm))

    p_cap = doc.add_paragraph(style="Figure Caption")
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_cap.paragraph_format.space_before = Pt(4)
    p_cap.paragraph_format.space_after = Pt(6)
    add_rich_runs(p_cap, caption_segments, size=9)


def add_data_table(doc, caption_segments, headers, rows, col_widths_cm, col_aligns=None):
    p_cap = doc.add_paragraph(style="Table Caption")
    p_cap.paragraph_format.space_before = Pt(6)
    p_cap.paragraph_format.space_after = Pt(4)
    p_cap.paragraph_format.keep_with_next = True
    add_rich_runs(p_cap, caption_segments, size=9)

    tbl = doc.add_table(rows=1 + len(rows), cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders_booktabs(tbl)

    for ci, h in enumerate(headers):
        cell = tbl.rows[0].cells[ci]
        cell.width = Cm(col_widths_cm[ci])
        set_cell_margins(cell, top=50, bottom=50, left=80, right=80)
        p = cell.paragraphs[0]
        p.alignment = col_aligns[ci] if col_aligns else WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        if isinstance(h, tuple):
            add_rich_runs(p, [(h[0], {"bold": True, **h[1]})], size=9)
        else:
            add_rich_runs(p, [(h, {"bold": True})], size=9)
    set_row_bottom_border(tbl.rows[0], sz=6)

    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = tbl.rows[ri + 1].cells[ci]
            cell.width = Cm(col_widths_cm[ci])
            set_cell_margins(cell, top=40, bottom=40, left=80, right=80)
            p = cell.paragraphs[0]
            p.alignment = col_aligns[ci] if col_aligns else WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            if isinstance(val, tuple):
                add_rich_runs(p, [val], size=9)
            else:
                add_rich_runs(p, [(val, {})], size=9)

    # Small spacer after table
    sp = doc.add_paragraph(style="Content")
    sp.paragraph_format.space_before = Pt(0)
    sp.paragraph_format.space_after = Pt(6)


def main():
    doc = Document(TPL)

    # 1. Update running header: "Author et al." -> "Slavov et al."
    sec = doc.sections[0]
    for p in sec.header.paragraphs:
        if "Author et al." in p.text:
            for r in p.runs:
                if "Author" in r.text:
                    r.text = r.text.replace("Author et al.", "Slavov et al.")
    for tbl in sec.header.tables:
        for row in tbl.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for r in p.runs:
                        if "Author et al." in r.text:
                            r.text = r.text.replace("Author et al.", "Slavov et al.")

    # 2. Replace Title (P00), Authors (P01), Affiliations (P02, P03)
    p0 = doc.paragraphs[0]
    p0.text = ""
    add_rich_runs(p0, [("Research on the robustness of deep learning-based DC motor condition classification using armature current signals", {"bold": True})], size=14)

    p1 = doc.paragraphs[1]
    p1.text = ""
    authors_segs = [
        ("Danail Slavov", {"bold": True}), ("1", {"bold": True, "sup": True}), (", ", {"bold": True}),
        ("Marin Zhilevski", {"bold": True}), ("1", {"bold": True, "sup": True}), (", ", {"bold": True}),
        ("Nikolay Yordanov", {"bold": True}), ("1", {"bold": True, "sup": True}), (", ", {"bold": True}),
        ("Mikho Mikhov", {"bold": True}), ("1", {"bold": True, "sup": True}), (", ", {"bold": True}),
        ("Veselin Krachunov", {"bold": True}), ("1", {"bold": True, "sup": True}), (", ", {"bold": True}),
        ("Oleg Krol", {"bold": True}), ("2*", {"bold": True, "sup": True, "red": True}), (" and ", {"bold": True}),
        ("Vladimir Sokolov", {"bold": True}), ("2", {"bold": True, "sup": True}),
    ]
    add_rich_runs(p1, authors_segs, size=9)

    p2 = doc.paragraphs[2]
    p2.text = ""
    add_rich_runs(p2, [
        ("1", {"sup": True}),
        ("Faculty of Automation, Technical University of Sofia, 8 Kliment Ohridski Blvd, 1000 Sofia, Bulgaria", {}),
    ], size=9)

    p3 = doc.paragraphs[3]
    p3.text = ""
    add_rich_runs(p3, [
        ("2", {"sup": True}),
        ("Volodymyr Dahl East Ukrainian National University, 17 Ioanna Pavla II str., 01042 Kyiv, Ukraine\n", {}),
        ("*Corresponding author email: krolos@i.ua  [REVIEW: confirm corresponding author]", {"red": True, "italic": True}),
    ], size=9)

    # 3. Populate Table 0 (Abstract + Keywords)
    t0 = doc.tables[0]
    abs_cell = t0.cell(0, 0)
    abs_p = abs_cell.paragraphs[0]
    abs_p.text = ""
    abs_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    abs_p.paragraph_format.first_line_indent = Cm(0)
    add_rich_runs(abs_p, [
        ("Abstract – ", {"bold": True}),
        ("Condition monitoring of converter-fed brushed permanent-magnet DC servo motors using electrical signals is practically attractive when supplementary vibration or acoustic sensors are unavailable. ", {"red": True}),
        ("This study investigated deep learning-based classification of four operating conditions of a brushed permanent-magnet DC servo motor using armature-current-related voltage signals, with particular emphasis on generalisation across operating speeds and recording protocols. A selected set of 72 recordings covered nine commanded speed settings and two acquisition modes, with and without periodic rotation reversals. Signals were resampled to 20 kHz and segmented into overlapping 0.5 s windows. A conventional one-dimensional convolutional neural network and single- and two-channel InceptionTime configurations were assessed using recording-disjoint evaluation, an unseen-speed holdout, nine-fold leave-one-speed-out testing, and bidirectional cross-protocol transfer. The two-channel representation additionally incorporated a band-pass-filtered Hilbert envelope. Results were averaged over three random seeds and assessed at the recording level. Leave-one-speed-out mean accuracies reached 98.61% and 98.15% for the one- and two-channel InceptionTime models, respectively. In contrast, cross-protocol mean accuracies were 75.93% and 74.07% when training without reversals, and 62.96% and 61.11% in the opposite direction. Direction-specific analysis did not identify reverse rotation or reversal transients as the sole explanation for reduced transfer performance, and the envelope channel did not provide a consistent improvement. ", {}),
        ("From a practical perspective, these findings distinguish robustness to unobserved speed setpoints from robustness to acquisition-protocol changes and provide concrete guidance for designing leakage-free, protocol-representative evaluation procedures in drive condition monitoring.", {"red": True}),
    ], size=9)

    kw_cell = t0.cell(7, 2)
    kw_p = kw_cell.paragraphs[0]
    kw_p.text = ""
    add_rich_runs(kw_p, [
        ("Condition monitoring; InceptionTime; Generalisation; Rotation reversal; Hilbert envelope; Servo drive", {"italic": True, "red": True}),
    ], size=9)

    # 4. Remove all template body elements after Table 0 (keep sectPr!)
    body = doc.element.body
    t0_el = t0._tbl
    found = False
    to_remove = []
    for child in list(body):
        if child is t0_el:
            found = True
            continue
        if found and child.tag != qn("w:sectPr"):
            to_remove.append(child)
    for child in to_remove:
        body.remove(child)

    # 5. SECTION 1: Introduction
    add_heading1(doc, "1. Introduction")
    add_body(doc, [
        ("Electrical current measurements offer an attractive basis for motor-condition monitoring when supplementary vibration or acoustic instrumentation is unavailable or undesirable. Classical motor-current signature analysis (MCSA) has demonstrated the diagnostic value of electrical signals, particularly for induction machines [1]", {}),
        (", and recent reviews confirm its continued relevance for rotor, stator, and load-side fault detection [2], as well as for motor-driven mechanisms [3]. ", {"red": True}),
        ("However, the characteristics of converter-fed brushed DC servo motors and their closed-loop operating regimes differ substantially from line-fed induction machines, limiting the direct transfer of classical induction-motor spectral indicators.", {}),
    ], first=True)

    add_body(doc, [
        ("Artificial intelligence methods have been widely investigated for rotating-machinery fault diagnosis, encompassing both conventional machine learning and deep learning approaches [4]–[6]. Deep learning architectures have also been extensively studied for univariate and multivariate time-series classification [7], with InceptionTime providing an effective multiscale convolutional architecture [8]. ", {}),
        ("Despite high accuracy reported under familiar laboratory regimes, critical surveys emphasise that performance often degrades sharply under limited labelled data, unseen operating speeds, and domain shifts between acquisition protocols [6], [9]–[11]. ", {"red": True}),
        ("Recent studies on DC motor fault diagnosis using deep learning have mainly focused on start-up transients or single-protocol regimes [12], [13], leaving open the question of how current-based classifiers behave when both operating speed and motion sequence (such as periodic rotation reversals) change simultaneously.", {"red": True}),
    ])

    add_body(doc, [
        ("Related work by the research team examined time–frequency representations for rotating-machinery diagnosis [14] and vibro-acoustic manifestations of loosened motor foundations [15]. ", {}),
        ("The original recording was adopted as the unit of data separation because consecutive overlapping windows from a single oscilloscope capture share operating conditions, acquisition settings, and time-correlated fluctuations; assigning windows from the same recording to both training and testing introduces information leakage and overly optimistic generalisation estimates, as demonstrated in vibration-based bearing diagnosis [16]. Previous studies have also investigated the transferability of convolutional features to unseen machine conditions [17] and outlined broader transfer-learning roadmaps for fault diagnosis [18].", {}),
    ])

    add_body(doc, [
        ("To address these gaps, the aim of this research is to systematically evaluate the generalisation robustness of one-dimensional deep learning classifiers for brushed permanent-magnet DC servo motor condition monitoring using armature-current-related voltage signals under unseen speed setpoints and bidirectional changes in rotation-reversal protocol. ", {"red": True}),
        ("The specific research objectives are: (i) to compare a conventional one-dimensional convolutional neural network (1D-CNN) with single- and two-channel InceptionTime architectures incorporating a band-pass-filtered Hilbert envelope; (ii) to quantify unseen-speed generalisation using strict recording-disjoint holdout and nine-fold leave-one-speed-out (LOSO) protocols; (iii) to measure bidirectional cross-protocol transfer between continuous-forward and periodic-reversal recordings; and (iv) to isolate the role of rotation direction and reversal transients in cross-protocol errors. ", {"red": True}),
        ("The scientific novelty lies in decoupling speed-interpolation robustness from acquisition-protocol robustness on a unified four-class mechanical and control-gain DC servo drive benchmark under strict recording-level separation. Practically, the results demonstrate that an existing electrical signal in the drive can support high-accuracy condition classification across unobserved speeds while warning practitioners that protocol shifts require representative training captures rather than reliance on unseen-speed accuracy alone.", {"red": True}),
    ], before_heading=True)

    # 6. SECTION 2: Materials and Methods
    add_heading1(doc, "2. Materials and Methods")

    add_heading2(doc, "2.1 Problem Formulation and Mathematical Description", red=True)
    add_body(doc, [
        ("Let ", {"red": True}), ("x", {"italic": True, "red": True}), ("(", {"red": True}), ("t", {"italic": True, "red": True}),
        (") denote the continuous armature-current-related voltage signal acquired over a recording of duration ", {"red": True}),
        ("T", {"italic": True, "red": True}), ("0", {"sub": True, "red": True}),
        (" under one of ", {"red": True}), ("C", {"italic": True, "red": True}), (" = 4 labelled operating conditions ", {"red": True}),
        ("c", {"italic": True, "red": True}), (" ∈ {1, …, ", {"red": True}), ("C", {"italic": True, "red": True}),
        ("}. After anti-alias downsampling to ", {"red": True}), ("f", {"italic": True, "red": True}), ("s", {"sub": True, "red": True}),
        (" = 20 kHz and trimming 0.5 s from both ends to suppress boundary artefacts (leaving effective duration ", {"red": True}),
        ("T", {"italic": True, "red": True}), (" = 19 s), each discrete sequence ", {"red": True}),
        ("x", {"italic": True, "red": True}), ("[", {"red": True}), ("n", {"italic": True, "red": True}),
        ("] is segmented into overlapping windows of length ", {"red": True}), ("L", {"italic": True, "red": True}),
        (" = 0.5 s (10,000 samples) with step ", {"red": True}), ("S", {"italic": True, "red": True}),
        (" = 0.25 s (50% overlap). The number of windows per recording ", {"red": True}),
        ("N", {"italic": True, "red": True}), ("w", {"sub": True, "red": True}),
        (" is given by Eq. (1):", {"red": True}),
    ], first=True)

    # Eq (1): N_w = floor((T - L)/S) + 1
    eq1 = (
        msub(mr("N"), mr("w")) + mr("=", roman=True)
        + mr("⌊", roman=True) + mfrac(mr("T") + mr("−", roman=True) + mr("L"), mr("S")) + mr("⌋", roman=True)
        + mr("+1", roman=True)
    )
    add_equation_row(doc, eq1, 1, red=True)

    add_body(doc, [
        ("For the two-channel representation, the resampled waveform ", {"red": True}),
        ("x", {"italic": True, "red": True}), ("[", {"red": True}), ("n", {"italic": True, "red": True}),
        ("] is passed through a zero-phase fourth-order Butterworth band-pass filter (200–1000 Hz) to yield ", {"red": True}),
        ("x", {"italic": True, "red": True}), ("bp", {"sub": True, "red": True}),
        ("[", {"red": True}), ("n", {"italic": True, "red": True}),
        ("], and the non-negative amplitude envelope ", {"red": True}),
        ("e", {"italic": True, "red": True}), ("[", {"red": True}), ("n", {"italic": True, "red": True}),
        ("] is obtained as the magnitude of the discrete Hilbert analytic signal (Eq. (2)):", {"red": True}),
    ], first=True)

    # Eq (2): e[n] = |x_bp[n] + j H{x_bp[n]}|
    eq2 = (
        mr("e") + mr("[", roman=True) + mr("n") + mr("]=", roman=True)
        + mr("|", roman=True) + msub(mr("x"), mr("bp", roman=True)) + mr("[", roman=True) + mr("n") + mr("]+", roman=True)
        + mr("j") + mr("H{", roman=True) + msub(mr("x"), mr("bp", roman=True)) + mr("[", roman=True) + mr("n") + mr("]}|", roman=True)
    )
    add_equation_row(doc, eq2, 2, red=True)

    add_body(doc, [
        ("where ", {"red": True}), ("H", {"italic": True, "red": True}), ("{·} denotes the discrete Hilbert transform and ", {"red": True}),
        ("j", {"italic": True, "red": True}), (" is the imaginary unit. Given window-level softmax class probabilities ", {"red": True}),
        ("p", {"italic": True, "red": True}), ("(", {"red": True}), ("w", {"italic": True, "red": True}), (", ", {"red": True}),
        ("c", {"italic": True, "red": True}), (") for window ", {"red": True}), ("w", {"italic": True, "red": True}),
        (" ∈ {1, …, ", {"red": True}), ("N", {"italic": True, "red": True}), ("w", {"sub": True, "red": True}),
        ("}, the recording-level predicted class ", {"red": True}), ("ŷ", {"italic": True, "red": True}),
        (" is obtained by probability averaging across all windows of the recording (Eq. (3)):", {"red": True}),
    ], first=True)

    # Eq (3): y_hat = argmax_c (1/N_w) sum_{w=1}^{N_w} p(w,c)
    eq3 = (
        mr("ŷ") + mr("=", roman=True) + msub(mr("arg max", roman=True), mr("c"))
        + mfrac(mr("1", roman=True), msub(mr("N"), mr("w")))
        + mnary("∑", mr("w") + mr("=1", roman=True), msub(mr("N"), mr("w")),
                mr("p") + mr("(", roman=True) + mr("w") + mr(",", roman=True) + mr("c") + mr(")", roman=True))
    )
    add_equation_row(doc, eq3, 3, red=True)

    add_body(doc, [
        ("Classification performance is evaluated at the recording level using overall accuracy (Eq. (4)) and macro-averaged F1 score (Eq. (5)), where ", {"red": True}),
        ("N", {"italic": True, "red": True}), ("rec", {"sub": True, "red": True}),
        (" is the number of test recordings, ", {"red": True}), ("N", {"italic": True, "red": True}), ("corr", {"sub": True, "red": True}),
        (" is the number of correctly classified recordings, and ", {"red": True}),
        ("P", {"italic": True, "red": True}), ("c", {"sub": True, "red": True}), (" and ", {"red": True}),
        ("R", {"italic": True, "red": True}), ("c", {"sub": True, "red": True}),
        (" denote precision and recall for class ", {"red": True}), ("c", {"italic": True, "red": True}), (":", {"red": True}),
    ], first=True)

    # Eq (4): Accuracy = (N_corr / N_rec) * 100%
    eq4 = (
        mr("Accuracy", roman=True) + mr("=", roman=True)
        + mfrac(msub(mr("N"), mr("corr", roman=True)), msub(mr("N"), mr("rec", roman=True)))
        + mr("×100%", roman=True)
    )
    add_equation_row(doc, eq4, 4, red=True)

    # Eq (5): Macro-F1 = (1/C) sum_{c=1}^{C} (2 P_c R_c)/(P_c + R_c) * 100%
    eq5 = (
        mr("Macro-F1", roman=True) + mr("=", roman=True)
        + mfrac(mr("1", roman=True), mr("C"))
        + mnary("∑", mr("c") + mr("=1", roman=True), mr("C"),
                mfrac(mr("2", roman=True) + msub(mr("P"), mr("c")) + msub(mr("R"), mr("c")),
                      msub(mr("P"), mr("c")) + mr("+", roman=True) + msub(mr("R"), mr("c"))))
        + mr("×100%", roman=True)
    )
    add_equation_row(doc, eq5, 5, red=True)

    add_heading2(doc, "2.2 Experimental Setup and Recordings")
    add_body(doc, [
        ("The experimental subset comprised 72 recordings from the authors' publicly released multi-sensor DC servo motor dataset (see Availability of Data and Materials)", {"red": True}),
        (": four labelled operating conditions, nine commanded speeds (1%, 2%, 5%, 10%, 20%, 30%, 40%, 50%, and 60% of rated speed, corresponding to 20–1200 rpm), and two acquisition protocols. ", {}),
        ("The laboratory test bench consists of a brushed permanent-magnet DC servo motor (model 3PI12.06; rated voltage 55 V, continuous nominal current 12.5 A, rated torque 2.7 Nm, rated angular speed 209.44 rad/s = 2000 rpm) driven by a four-quadrant thyristor converter (ELL 14010) under cascaded speed and current control, operating without an external mechanical load. ", {"red": True}),
        ("Only the nine common commanded speed settings up to 60% were included so that every class–protocol combination was balanced across all evaluated speeds, as the non-optimal speed-regulator condition was physically limited to 65% of rated speed.", {}),
    ], first=True)

    add_body(doc, [
        ("The four investigated conditions were defined directly from controlled laboratory interventions rather than post hoc clustering: ", {}),
        ("(1) normal operation (N), with nominal speed-regulator gain P05.04 = 10, nominal current-regulator gain P06.02 = 2, and tightened mounting bolts; ", {"red": True}),
        ("(2) loosened motor foundation (LF), with all four mounting bolts loosened by hand while retaining nominal regulator gains (P05.04 = 10, P06.02 = 2); ", {"red": True}),
        ("(3) non-optimal speed-regulator gain (SG), with P05.04 reduced to 0.2 and P06.02 = 2; and ", {"red": True}),
        ("(4) non-optimal current-regulator gain (CG), with nominal speed-regulator gain P05.04 = 10 and current-regulator gain P06.02 reduced to 0.1 [REVIEW: verify against confusion-matrix label SG+CG in Figure 4]. ", {"red": True}),
        ("Each recording lasted approximately 20 s and was acquired at 1 MHz using a Rigol MSO5074 digital oscilloscope (channel 1, DC coupling, 1 V/div, −3 V offset). The recorded signal is a voltage proportional to armature current; because its current-to-voltage conversion coefficient was not established, amplitudes are reported in volts rather than calibrated amperes.", {}),
    ])

    add_body(doc, [
        ("Under the no-reversal protocol the motor rotated continuously in the forward direction. Under the with-reversal protocol approximately four manually initiated direction reversals occurred during each recording (approximately every 4 s), producing short intervals of rapid electrical transient behaviour separated by sustained forward or reverse rotation. To inspect the spectral distribution of the measured channel, power spectral density (PSD) estimates were computed via the fast Fourier transform (FFT) across 0–1,000 Hz, 0–10,000 Hz, and 0–100,000 Hz at 50% commanded speed (Figure 1). Useful diagnostic energy is concentrated primarily below 1 kHz, where converter ripple (300 Hz and harmonics) and commutation-related components appear, while higher frequencies approach the noise floor.", {}),
    ])

    add_figure(doc, "image1.png", [
        ("Figure 1. Power spectral density of the armature-current-related voltage for the four motor conditions at 50% commanded speed: (a) 0–1,000 Hz, (b) 0–10,000 Hz, and (c) 0–100,000 Hz", {})
    ], width_cm=11.5)

    add_body(doc, [
        ("Figure 2 compares the resulting Hilbert amplitude envelopes (Eq. (2)) for the four operating conditions over a representative one-second interval at 50% commanded speed without rotation reversal. The normal and loosened-foundation conditions exhibit relatively similar envelope profiles, whereas the two regulator-related conditions show more pronounced amplitude variations. Because visual differences in individual segments do not necessarily translate into higher classification accuracy, the effectiveness of adding the envelope as a second input channel was evaluated experimentally.", {}),
    ], before_heading=True)

    add_figure(doc, "image2.png", [
        ("Figure 2. Comparison of Hilbert-transform amplitude envelopes of armature-current-related voltage signals for the four motor operating conditions at 50% commanded speed (10–11 s interval, without rotation reversal)", {})
    ], width_cm=13.5)

    add_heading2(doc, "2.3 Preprocessing and Input Representations")
    add_body(doc, [
        ("Signals were downsampled from 1 MHz to 20 kHz (a factor of 50) using polyphase resampling with anti-alias filtering to reduce computational cost while preserving the dominant low-frequency content below 1 kHz. Both network configurations operated directly on one-dimensional time-series windows rather than two-dimensional spectrograms. The single-channel (1-ch) input comprised the resampled current-related voltage waveform, whereas the two-channel (2-ch) input stacked the waveform with its zero-phase Butterworth (200–1000 Hz) Hilbert envelope (Eq. (2)). Because the envelope is derived deterministically from the same electrical channel, the 2-ch configuration does not represent multi-sensor fusion. With ", {}),
        ("T", {"italic": True}), (" = 19 s, ", {}), ("L", {"italic": True}), (" = 0.5 s, and ", {}),
        ("S", {"italic": True}), (" = 0.25 s, Eq. (1) yields ", {}),
        ("N", {"italic": True}), ("w", {"sub": True}),
        (" = 75 windows per recording (5,400 windows across the 72 recordings). Recording-level splits were enforced prior to windowing, and channel-wise Z-score standardisation statistics were computed exclusively on the training partition and applied unchanged to validation and test recordings.", {}),
    ], first=True, before_heading=True)

    add_heading2(doc, "2.4 Models, Training, and Evaluation Protocols")
    add_body(doc, [
        ("The initial benchmark compared a conventional 1D-CNN with InceptionTime [8] using 1-ch and 2-ch inputs. The baseline 1D-CNN comprised three Conv1d–BatchNorm–ReLU–MaxPool blocks with 32, 64, and 128 output channels, kernel sizes 15, 9, and 5 (with length-preserving padding), and pooling factor 4, followed by adaptive global average pooling and a linear four-class output layer. InceptionTime employed parallel multiscale convolutional pathways in a single network (", {}),
        ("n", {"italic": True}), ("f", {"sub": True}),
        (" = 32) rather than an ensemble, isolating the effect of architecture family and input representation. Models were trained with window-level cross-entropy loss using Adam (learning rate 0.001, batch size 32, up to 100 epochs, early-stopping patience 15 epochs), selecting the checkpoint by validation recording-level macro-F1 with validation loss as a tie-breaker. Three random seeds (42, 123, 456) were run to assess sensitivity to initialisation and training stochasticity; sample standard deviations (", {}),
        ("n", {"italic": True, "red": True}), (" − 1 denominator) across seeds are reported where available [REVIEW: add per-seed SD to Tables 1, 3, 4 if raw seed logs are available].", {"red": True}),
    ], first=True)

    add_body(doc, [
        ("Evaluation followed four progressively stricter generalisation protocols. First, the initial benchmark used development speeds of 1%, 2%, 5%, 10%, 30%, 40%, and 60% (five training, one validation, and one standard-test recording per condition and protocol: 40, 8, and 8 recordings) while reserving 20% and 50% for unseen-speed testing (16 recordings). Second, nine-fold LOSO evaluation held out each speed in turn for testing (8 recordings), using the next speed in a cyclic schedule for validation (8 recordings) and the remaining seven speeds for training (56 recordings), with both protocols represented in every partition. Third, bidirectional cross-protocol transfer trained on no-reversal recordings and tested on with-reversal recordings (CR1), or reversed the roles (CR2), using 28 training recordings (seven speeds), 8 same-protocol validation recordings (two held-out speeds), and all 36 opposite-protocol test recordings. Finally, for direction-specific CR1 analysis, reversal events were annotated in 34 of the 36 target recordings (Figure 3), partitioning windows into forward, reverse, and transient regions; the two recordings with unreliable reversal timing remained in the complete CR1 test but were excluded from the direction-specific breakdown.", {}),
    ])

    add_figure(doc, "image3.png", [
        ("Figure 3. Current-related voltage waveform and moving RMS at 30% commanded speed with rotation reversals, showing annotated forward, reverse, and transition intervals (0.15 s before to 0.35 s after each reversal event)", {})
    ], width_cm=14.0)

    # 7. SECTION 3: Results and Discussion
    add_heading1(doc, "3. Results and Discussion")

    add_heading2(doc, "3.1 Conventional Classification and Unseen-Speed Evaluation")
    add_body(doc, [
        ("Table 1 summarises the mean recording-level accuracy over three seeds for the initial benchmark. Both the baseline 1D-CNN and 1-ch InceptionTime achieved 100.00% mean accuracy on the standard test (8 recordings), whereas 2-ch InceptionTime achieved 95.83%. On the two unseen speed settings (16 recordings), mean accuracies reached 97.92%, 100.00%, and 97.92%, respectively. Given the modest test-set sizes, perfect scores should be interpreted as error-free classification of the available laboratory recordings rather than an estimate of zero-error industrial operation. Notably, adding the Hilbert envelope did not improve performance over the simpler 1-ch waveform.", {}),
    ], first=True)

    add_data_table(
        doc,
        [("Table 1. Mean recording-level classification accuracy over three random seeds", {})],
        ["Model", "Standard test (%)", "Unseen speeds (%)"],
        [
            ["1D-CNN, 1-ch", "100.00", "97.92"],
            ["InceptionTime, 1-ch", "100.00", "100.00"],
            ["InceptionTime, 2-ch", "95.83", "97.92"],
        ],
        [6.5, 4.5, 4.5],
        [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER],
    )

    add_heading2(doc, "3.2 Leave-One-Speed-Out Evaluation")
    add_body(doc, [
        ("Across all nine held-out speeds, mean recording-level LOSO accuracies reached 98.61% and 98.15% for the 1-ch and 2-ch InceptionTime models, respectively. Every held-out speed other than 20%, 30%, and 40% achieved 100.00 ± 0.00% for both inputs. Table 2 reports the non-perfect speed folds and overall mean.", {}),
    ], first=True)

    add_data_table(
        doc,
        [("Table 2. Leave-one-speed-out recording-level accuracy by held-out speed (mean ± standard deviation, %)", {})],
        ["Held-out speed", "InceptionTime, 1-ch (%)", "InceptionTime, 2-ch (%)"],
        [
            ["20%", "100.00 ± 0.00", "95.83 ± 5.89"],
            ["30%", "91.67 ± 5.89", "87.50 ± 0.00"],
            ["40%", "95.83 ± 5.89", "100.00 ± 0.00"],
            ["Overall (9 speeds)", "98.61", "98.15"],
        ],
        [5.5, 5.0, 5.0],
        [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER],
    )

    add_body(doc, [
        ("The aggregated confusion matrices (Figure 4, 54 evaluated predictions per true class across nine speeds, two protocols, and three seeds) reveal a highly concentrated error pattern. All seven incorrect model–recording predictions (three for 1-ch and four for 2-ch) involved the non-optimal speed-regulator gain class (SG) being misclassified as loosened foundation (LF), whereas normal operation (N) and the non-optimal current-regulator gain class (CG) ", {"red": True}),
        ("were classified with 100% accuracy throughout. Errors clustered at the 30% held-out speed, with single-seed errors at 20% (2-ch) and 40% (1-ch), and corresponded to only three distinct physical recordings; repeated seeds should therefore not be treated as independent observations.", {}),
    ])

    add_figure(doc, "image4.png", [
        ("Figure 4. Aggregated leave-one-speed-out confusion matrices over nine folds and three seeds (N: normal; LF: loosened foundation; SG: non-optimal speed-regulator gain; ", {}),
        ("CG: non-optimal current-regulator gain, labelled as SG+CG on the plot axes [REVIEW: update axis label in PNG if desired])", {"red": True}),
    ], width_cm=13.5)

    add_heading2(doc, "3.3 Cross-Protocol Evaluation")
    add_body(doc, [
        ("Table 3 presents the bidirectional cross-protocol results averaged across three seeds, with both accuracy and macro-F1 expressed in percentages for consistent reporting. In CR1 (trained without reversals, tested with reversals), the 1-ch and 2-ch models achieved 75.93% and 74.07% accuracy; in CR2 (opposite direction), accuracies dropped to 62.96% and 61.11%. Transfer across acquisition protocols was thus markedly more challenging than interpolation across unseen speeds. Seed-to-seed variability was also substantial (ranging from approximately 56% to 97% in CR1), and the confusion pattern shifted with transfer direction: LF recordings were predominantly misclassified as SG in CR1, whereas LF and several SG recordings were assigned to N in CR2. Although the 2-ch model yielded a slightly higher macro-F1 in CR1 despite lower accuracy, both metrics were lower in CR2, confirming no consistent benefit from the envelope channel.", {}),
    ], first=True)

    add_data_table(
        doc,
        [("Table 3. Cross-protocol recording-level performance averaged over three random seeds", {})],
        ["Protocol", "Input", "Accuracy (%)", ("Macro-F1 (%)", {"red": True})],
        [
            ["CR1 (no-rev → with-rev)", "1-ch", "75.93", ("68.55", {"red": True})],
            ["CR1 (no-rev → with-rev)", "2-ch", "74.07", ("72.10", {"red": True})],
            ["CR2 (with-rev → no-rev)", "1-ch", "62.96", ("56.38", {"red": True})],
            ["CR2 (with-rev → no-rev)", "2-ch", "61.11", ("54.32", {"red": True})],
        ],
        [5.5, 2.8, 3.6, 3.6],
        [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER],
    )

    add_heading2(doc, "3.4 Direction-Specific Analysis")
    add_body(doc, [
        ("To test whether the CR1 performance drop stemmed solely from reverse rotation or reversal transients, the six trained CR1 checkpoints were evaluated without retraining on isolated forward- and reverse-rotation segments across the 34 annotated test recordings (Figure 3). Windows overlapping each reversal event were excluded using three before/after margin settings: 0.10/0.20 s (narrow), 0.15/0.35 s (intermediate; 1,186 forward, 820 reverse, and 544 excluded transition windows), and 0.50/0.50 s (conservative). As shown in Table 4, forward and reverse accuracies were nearly identical (74.51% vs. 73.53% for 1-ch) and insensitive to the exclusion margins. Removing transition windows and isolating forward-only segments did not restore accuracy to the LOSO level, showing that protocol-transfer degradation cannot be attributed solely to reverse rotation or immediate reversal transients.", {}),
    ], first=True)

    add_data_table(
        doc,
        [("Table 4. Direction-specific recording-level accuracy (%) in CR1 for three transient-exclusion margin settings", {})],
        ["Margins before / after (s)", "Input", "Forward (%)", "Reverse (%)"],
        [
            ["0.10 / 0.20", "1-ch", "74.51", "73.53"],
            ["0.10 / 0.20", "2-ch", "76.47", "76.47"],
            ["0.15 / 0.35", "1-ch", "74.51", "73.53"],
            ["0.15 / 0.35", "2-ch", "76.47", "75.49"],
            ["0.50 / 0.50", "1-ch", "74.51", "73.53"],
            ["0.50 / 0.50", "2-ch", "74.51", "74.51"],
        ],
        [5.2, 2.8, 3.8, 3.8],
        [WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER],
    )

    add_heading2(doc, "3.5 Discussion")
    add_body(doc, [
        ("The experimental results confirm that armature-current-related voltage signals carry discriminative information for both mechanical (loosened foundation) and control-related (regulator gain) operating conditions without additional vibration or acoustic sensors. ", {}),
        ("This aligns with recent current-based deep learning studies on electric motors from multiple research groups. Yousefnejad et al. [12] demonstrated that deep learning applied to DC motor start-up current waveforms can accurately detect electrical and mechanical faults, while Sarı et al. [13] achieved high DC motor classification accuracy using an optimised deep classifier under fixed acquisition protocols. Similarly, Goh and Kim [19] showed that tailored current-input transformations enhance CNN stator-fault diagnosis in three-phase induction motors, and Diversi et al. [3] confirmed the diagnostic sensitivity of motor-current models in motor-driven mechanisms. Unlike those studies, which primarily evaluate single acquisition sequences or fixed transient profiles, the present work directly contrasts unseen-speed interpolation against bidirectional acquisition-protocol transfer on the same drive.", {"red": True}),
    ], first=True)

    add_body(doc, [
        ("A central methodological finding is the sharp gap between speed generalisation (>98% LOSO accuracy) and protocol generalisation (61.11–75.93% cross-protocol accuracy). ", {}),
        ("This behaviour mirrors the domain-shift challenges highlighted in recent surveys and causal/episodic domain-generalisation studies on rotating machinery by Xiao et al. [11], Guo et al. [20], and Liao et al. [21], where models that interpolate well across operating speeds still struggle when the underlying temporal distribution or excitation pattern shifts. Moreover, enforcing strict recording-level separation follows the leakage-prevention principles established by Wheat et al. [16], preventing inflated cross-protocol scores caused by overlapping windows from identical captures. ", {"red": True}),
        ("Because isolating forward-only segments and widening transient-exclusion margins did not close the CR1 transfer gap, broader protocol-dependent factors—such as post-reversal settling dynamics, shorter steady-state intervals, or subtle operating-state variations—likely contribute to the shift. Adding the 200–1000 Hz Hilbert envelope increased dimensionality without consistent gains, indicating that the multiscale convolutional filters in 1-ch InceptionTime already capture the primary discriminative structure in the 20 kHz waveform.", {}),
    ])

    add_body(doc, [
        ("The study is subject to clear scope limitations: experiments were conducted on a single no-load laboratory motor and thyristor converter, with 20 s recordings, three random seeds, and eight independent test recordings per LOSO fold. Because the labels correspond to controlled laboratory interventions, the classifiers detect stable electrical signatures of those interventions rather than directly estimating physical stiffness or controller parameters. Consequently, the results should not be extrapolated directly to loaded industrial machines without dedicated multi-load validation.", {}),
    ], before_heading=True)

    # 8. SECTION 4: Conclusions
    add_heading1(doc, "4. Conclusions")
    add_body(doc, [
        ("This study evaluated the generalisation robustness of one-dimensional deep learning classifiers for brushed permanent-magnet DC servo motor condition monitoring using armature-current-related voltage signals across four operating conditions, nine commanded speeds, and two motion protocols. ", {"red": True}),
        ("Under strict recording-level separation, the models achieved strong generalisation to unseen speed setpoints: nine-fold LOSO mean accuracies reached 98.61% (1-ch InceptionTime) and 98.15% (2-ch InceptionTime), with all seven misclassifications across 216 model–recording evaluations restricted to confusing non-optimal speed-regulator gain with loosened foundation on three physical recordings. ", {"red": True}),
        ("In contrast, bidirectional cross-protocol transfer yielded substantially lower and more seed-sensitive accuracies—75.93% (1-ch) and 74.07% (2-ch) in CR1, and 62.96% (1-ch) and 61.11% (2-ch) in CR2—and direction-specific analysis (74.51% forward vs. 73.53% reverse for 1-ch) demonstrated that reverse rotation and immediate reversal transients do not solely explain this degradation. ", {"red": True}),
        ("Incorporating a 200–1000 Hz Hilbert-transform envelope did not consistently outperform the simpler single-channel 20 kHz waveform, confirming 1-ch InceptionTime as the preferable baseline for this signal.", {"red": True}),
    ], first=True)

    add_body(doc, [
        ("Future research will extend this framework along three directions: (i) acquiring a full factorial multi-load dataset with repeated independent captures of continuous-forward, continuous-reverse, and reversal-containing sequences to separate load, direction, and run-to-run effects; (ii) evaluating domain-generalisation and protocol-invariant training strategies with target-protocol recordings strictly held out; and (iii) validating current-based diagnosis across additional DC and brushless servo motor systems alongside calibrated current-probe measurements.", {"red": True}),
    ], before_heading=True)

    # 9. Mandatory IJAME Back-Matter Sections
    add_heading1(doc, "Acknowledgements", red=True)
    add_body(doc, [
        ("The authors thank the laboratory staff of the Department of Automation of Electrical Drives at the Technical University of Sofia for technical assistance with the experimental test bench. [REVIEW: confirm or remove if not needed]", {"red": True}),
    ], first=True, before_heading=True)

    add_heading1(doc, "Funding", red=True)
    add_body(doc, [
        ("This work was supported by the Research and Development Sector at the Technical University of Sofia. [REVIEW: add specific grant number if applicable]", {"red": True}),
    ], first=True, before_heading=True)

    add_heading1(doc, "Declaration of Competing Interests", red=True)
    add_body(doc, [
        ("The authors declare no relevant financial or non-financial conflicts of interest.", {"red": True}),
    ], first=True, before_heading=True)

    add_heading1(doc, "CRediT Author Contribution Statement", red=True)
    credit_lines = [
        "D. Slavov: Methodology; Software; Analysis; Validation; Visualisation; Writing – original draft [REVIEW]",
        "M. Zhilevski: Conceptualisation; Investigation; Data curation; Resources; Writing – review & revise [REVIEW]",
        "N. Yordanov: Conceptualisation; Investigation; Data curation; Software; Writing – review & revise [REVIEW]",
        "M. Mikhov: Conceptualisation; Supervision; Resources; Writing – review & revise [REVIEW]",
        "V. Krachunov: Investigation; Validation; Resources [REVIEW]",
        "O. Krol: Conceptualisation; Methodology; Supervision; Writing – review & revise [REVIEW]",
        "V. Sokolov: Methodology; Validation; Writing – review & revise [REVIEW]",
    ]
    for idx, cl in enumerate(credit_lines):
        p = doc.add_paragraph(style="bullets")
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(6 if idx == len(credit_lines) - 1 else 2)
        add_rich_runs(p, [(cl, {"red": True})], size=None)

    add_heading1(doc, "Availability of Data and Materials", red=True)
    add_body(doc, [
        ("The experimental dataset analysed during the current study is publicly available in Mendeley Data at https://doi.org/10.17632/g28trvywnx.1 (Version 1). Analysis scripts are available from the corresponding author upon reasonable request. [REVIEW: confirm DOI/version]", {"red": True}),
    ], first=True, before_heading=True)

    add_heading1(doc, "Ethics Statement", red=True)
    add_body(doc, [
        ("This study did not involve human participants or animal subjects. Ethical approval was therefore not required.", {"red": True}),
    ], first=True, before_heading=True)

    add_heading1(doc, "Generative Artificial Intelligence Disclosure", red=True)
    add_body(doc, [
        ("AI-based tools were used solely for language editing and grammar refinement. No AI content generation or data interpretation was performed. All intellectual contributions are original and solely attributable to the authors. All AI-assisted edits were reviewed and verified by the authors for accuracy and originality. Final interpretations and conclusions are the sole responsibility of the authors. [REVIEW]", {"red": True}),
    ], first=True, before_heading=True)

    # 10. References (IEEE style, 21 items; 8 new external refs in RED; self-citations = 2/21 = 9.5%)
    p_rh = doc.add_paragraph(style="Normal")
    p_rh.paragraph_format.space_before = Pt(12)
    p_rh.paragraph_format.space_after = Pt(4)
    add_rich_runs(p_rh, [("References", {"bold": True})], size=10)

    refs = [
        (False, "W. T. Thomson and M. Fenger, “Current signature analysis to detect induction motor faults,” ", "IEEE Industry Applications Magazine", ", vol. 7, no. 4, pp. 26–34, 2001. https://doi.org/10.1109/2943.930988"),
        (True,  "S. Halder, S. Bhat, D. Zychma, and P. Sowa, “Broken rotor bar fault diagnosis techniques based on motor current signature analysis for induction motor—A review,” ", "Energies", ", vol. 15, no. 22, Art. no. 8569, 2022. https://doi.org/10.3390/en15228569"),
        (True,  "R. Diversi, A. Lenzi, N. Speciale, and M. Barbieri, “An autoregressive-based motor current signature analysis approach for fault diagnosis of electric motor-driven mechanisms,” ", "Sensors", ", vol. 25, no. 4, Art. no. 1130, 2025. https://doi.org/10.3390/s25041130"),
        (False, "R. Liu, B. Yang, E. Zio, and X. Chen, “Artificial intelligence for fault diagnosis of rotating machinery: A review,” ", "Mechanical Systems and Signal Processing", ", vol. 108, pp. 33–47, 2018. https://doi.org/10.1016/j.ymssp.2018.02.016"),
        (False, "O. Das, D. Das, and D. Birant, “Machine learning for fault analysis in rotating machinery: A comprehensive review,” ", "Heliyon", ", vol. 9, no. 6, Art. no. e17584, 2023. https://doi.org/10.1016/j.heliyon.2023.e17584"),
        (False, "Z. Zhu, Y. Lei, G. Qi, et al., “A review of the application of deep learning in intelligent fault diagnosis of rotating machinery,” ", "Measurement", ", vol. 206, Art. no. 112346, 2023. https://doi.org/10.1016/j.measurement.2022.112346"),
        (False, "H. I. Fawaz, G. Forestier, J. Weber, L. Idoumghar, and P.-A. Muller, “Deep learning for time series classification: A review,” ", "Data Mining and Knowledge Discovery", ", vol. 33, no. 4, pp. 917–963, 2019. https://doi.org/10.1007/s10618-019-00619-1"),
        (False, "H. I. Fawaz, B. Lucas, G. Forestier, et al., “InceptionTime: Finding AlexNet for time series classification,” ", "Data Mining and Knowledge Discovery", ", vol. 34, pp. 1936–1962, 2020. https://doi.org/10.1007/s10618-020-00710-y"),
        (False, "Z. Zhao, T. Li, J. Wu, et al., “Deep learning algorithms for rotating machinery intelligent diagnosis: An open source benchmark study,” ", "ISA Transactions", ", vol. 107, pp. 224–255, 2020. https://doi.org/10.1016/j.isatra.2020.08.010"),
        (False, "L. Zhang, J. Lin, B. Liu, et al., “Rotating machinery fault detection and diagnosis based on deep domain adaptation: A survey,” ", "Chinese Journal of Aeronautics", ", vol. 36, no. 1, pp. 45–74, 2023. https://doi.org/10.1016/j.cja.2021.10.006"),
        (True,  "Y. Xiao, H. Shao, S. Yan, J. Wang, Y. Peng, and B. Liu, “Domain generalization for rotating machinery fault diagnosis: A survey,” ", "Advanced Engineering Informatics", ", vol. 64, Art. no. 103063, 2025. https://doi.org/10.1016/j.aei.2024.103063"),
        (True,  "S. Yousefnejad, F. Bagheri, R. Alshawi, M. T. Hoque, and E. Amiri, “Deep learning based fault detection method in DC motor start,” ", "IEEE Transactions on Energy Conversion", ", vol. 40, no. 2, pp. 1678–1681, 2025. https://doi.org/10.1109/tec.2025.3560559"),
        (True,  "V. Sarı, V. Göreke, and S. Kockanat, “A novel fault diagnosis method for a DC electric motor using a deep learning classifier optimized by an artificial bee colony algorithm,” ", "Iranian Journal of Science and Technology, Transactions of Electrical Engineering", ", vol. 49, no. 4, pp. 1673–1692, 2025. https://doi.org/10.1007/s40998-025-00874-7"),
        (False, "A. Orhan, N. Yordanov, M. Ertarğın, M. Zhilevski, and M. Mikhov, “A comparative study of time–frequency representations for bearing and rotating fault diagnosis using Vision Transformer,” ", "Machines", ", vol. 13, no. 8, Art. no. 737, 2025. https://doi.org/10.3390/machines13080737"),
        (False, "N. Yordanov, M. Zhilevski, M. Mikhov, O. Krol, and V. Sokolov, “Vibro-acoustic analysis of loose foundation effects in electric motors at varying rotational speeds,” ", "International Journal of Mechatronics and Applied Mechanics", ", no. 22, vol. II, pp. 125–131, 2025. https://doi.org/10.17683/ijomam/issue22.v2.12"),
        (False, "L. Wheat, M. Mohrenschildt, S. Habibi, and D. Al-Ani, “Impact of data leakage in vibration signals used for bearing fault diagnosis,” ", "IEEE Access", ", vol. 12, pp. 169879–169895, 2024. https://doi.org/10.1109/ACCESS.2024.3497716"),
        (False, "T. Han, C. Liu, W. Yang, and D. Jiang, “Learning transferable features in deep convolutional neural networks for diagnosing unseen machine conditions,” ", "ISA Transactions", ", vol. 93, pp. 341–353, 2019. https://doi.org/10.1016/j.isatra.2019.03.017"),
        (False, "Y. Lei, B. Yang, X. Jiang, F. Jia, N. Li, and A. K. Nandi, “Applications of machine learning to machine fault diagnosis: A review and roadmap,” ", "Mechanical Systems and Signal Processing", ", vol. 138, Art. no. 106587, 2020. https://doi.org/10.1016/j.ymssp.2019.106587"),
        (True,  "Y. J. Goh and K. M. Kim, “Clarke-Park transformation-based input configuration for CNN diagnosis of stator faults in three phase induction motors using motor current signature analysis,” ", "IEEE Access", ", vol. 13, pp. 150505–150516, 2025. https://doi.org/10.1109/access.2025.3602975"),
        (True,  "C. Guo, Z. Zhao, J. Ren, S. Wang, Y. Liu, and X. Chen, “Causal explaining guided domain generalization for rotating machinery intelligent fault diagnosis,” ", "Expert Systems with Applications", ", vol. 243, Art. no. 122806, 2024. https://doi.org/10.1016/j.eswa.2023.122806"),
        (True,  "Y. Liao, S. Zhou, Y. Liu, et al., “Episodic training and feature orthogonality-driven domain generalization for rotating machinery fault diagnosis under unseen working conditions,” ", "Machines", ", vol. 13, no. 7, Art. no. 563, 2025. https://doi.org/10.3390/machines13070563"),
    ]

    for idx, (is_new, pre, journal, post) in enumerate(refs, start=1):
        p = doc.add_paragraph(style="Normal")
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.left_indent = Cm(0.8)
        p.paragraph_format.first_line_indent = Cm(-0.8)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        kw = {"red": True} if is_new else {}
        add_rich_runs(p, [
            (f"[{idx}]\t{pre}", kw),
            (journal, {**kw, "italic": True}),
            (post, kw),
        ], size=9)

    doc.save(OUT)
    # Count abstract words
    abs_words = len(abs_p.text.split()) - 2  # exclude "Abstract –"
    print(f"OK saved {OUT.name} | abstract_words={abs_words} | refs={len(refs)}")


if __name__ == "__main__":
    main()
