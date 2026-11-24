"""Build a compact 15-slide 16:9 PowerPoint presentation for the intro session on LLMs + Labs 8, 9, 10."""
from pathlib import Path
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
OUT = HERE / "Презентация_ЛУ_8_9_10_и_AI.pptx"

NAVY = RGBColor(0x1B, 0x36, 0x5D)
TEAL = RGBColor(0x00, 0x77, 0xB6)
AMBER = RGBColor(0xD9, 0x77, 0x06)
GREEN = RGBColor(0x15, 0x80, 0x3D)
RED = RGBColor(0xB9, 0x1C, 0x1C)
DARK = RGBColor(0x1E, 0x29, 0x3B)
MUTED = RGBColor(0x47, 0x55, 0x69)
LIGHT_BG = RGBColor(0xF4, 0xF7, 0xFA)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BORDER = RGBColor(0xCB, 0xD5, 0xE1)
SOFT_BLUE = RGBColor(0xE0, 0xF2, 0xFE)
SOFT_AMBER = RGBColor(0xFE, 0xF3, 0xC7)
SOFT_GREEN = RGBColor(0xDC, 0xFC, 0xE7)
SOFT_RED = RGBColor(0xFE, 0xE2, 0xE2)

FONT = "Segoe UI"


def new_prs():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    return prs


def add_blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def add_header(slide, title, subtitle="", tag="", page_num=None):
    # Top accent bar
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.1))
    bar.fill.solid()
    bar.fill.fore_color.rgb = TEAL
    bar.line.fill.background()

    # Tag pill
    if tag:
        pill = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.6), Inches(0.26), Inches(2.5), Inches(0.32))
        pill.fill.solid()
        pill.fill.fore_color.rgb = SOFT_BLUE
        pill.line.fill.background()
        tf = pill.text_frame
        tf.word_wrap = False
        tf.margin_left = tf.margin_right = Inches(0.1)
        tf.margin_top = tf.margin_bottom = Inches(0.02)
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = tag
        r.font.name = FONT
        r.font.size = Pt(11)
        r.font.bold = True
        r.font.color.rgb = TEAL

    y_title = Inches(0.62) if tag else Inches(0.32)
    tb = slide.shapes.add_textbox(Inches(0.6), y_title, Inches(12.1), Inches(0.55))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = title
    r.font.name = FONT
    r.font.size = Pt(24)
    r.font.bold = True
    r.font.color.rgb = NAVY

    if subtitle:
        stb = slide.shapes.add_textbox(Inches(0.6), y_title + Inches(0.48), Inches(12.1), Inches(0.35))
        stf = stb.text_frame
        stf.word_wrap = True
        stf.margin_left = stf.margin_right = stf.margin_top = stf.margin_bottom = 0
        sp = stf.paragraphs[0]
        sr = sp.add_run()
        sr.text = subtitle
        sr.font.name = FONT
        sr.font.size = Pt(13.5)
        sr.font.color.rgb = MUTED

    # Subtle bottom line + page number
    if page_num is not None:
        ft = slide.shapes.add_textbox(Inches(0.6), Inches(7.1), Inches(12.1), Inches(0.28))
        ftf = ft.text_frame
        ftf.margin_left = ftf.margin_right = ftf.margin_top = ftf.margin_bottom = 0
        fp = ftf.paragraphs[0]
        fp.alignment = PP_ALIGN.RIGHT
        fr = fp.add_run()
        fr.text = f"ТУ – София | Лабораторни упражнения № 8–10    {page_num} / 15"
        fr.font.name = FONT
        fr.font.size = Pt(10)
        fr.font.color.rgb = MUTED


def add_card(slide, x, y, w, h, title=None, bg=LIGHT_BG, border_color=BORDER, title_color=NAVY, accent_top=None):
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    card.adjustments[0] = 0.03
    card.fill.solid()
    card.fill.fore_color.rgb = bg
    if border_color:
        card.line.color.rgb = border_color
        card.line.width = Pt(1)
    else:
        card.line.fill.background()

    if accent_top:
        acc = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(0.08))
        acc.fill.solid()
        acc.fill.fore_color.rgb = accent_top
        acc.line.fill.background()

    if title:
        tb = slide.shapes.add_textbox(Inches(x + 0.18), Inches(y + 0.14), Inches(w - 0.36), Inches(0.38))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = title
        r.font.name = FONT
        r.font.size = Pt(15)
        r.font.bold = True
        r.font.color.rgb = title_color
    return card


def add_bullets(slide, x, y, w, h, items, font_size=13.5, space_after=6, color=DARK, bullet="• "):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for idx, item in enumerate(items):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.space_after = Pt(space_after)
        if isinstance(item, tuple):
            lead, rest = item
            r0 = p.add_run()
            r0.text = bullet + lead
            r0.font.name = FONT
            r0.font.size = Pt(font_size)
            r0.font.bold = True
            r0.font.color.rgb = color
            r1 = p.add_run()
            r1.text = rest
            r1.font.name = FONT
            r1.font.size = Pt(font_size)
            r1.font.color.rgb = color
        else:
            r = p.add_run()
            r.text = bullet + item
            r.font.name = FONT
            r.font.size = Pt(font_size)
            r.font.color.rgb = color
    return tb


def add_picture_fit(slide, img_path: Path, x, y, max_w, max_h):
    with Image.open(img_path) as im:
        iw, ih = im.size
    ratio = min(max_w / iw, max_h / ih)
    w = iw * ratio
    h = ih * ratio
    px = x + (max_w - w) / 2
    py = y + (max_h - h) / 2
    slide.shapes.add_picture(str(img_path), Inches(px), Inches(py), width=Inches(w), height=Inches(h))


def style_cell(cell, text, font_size=11.5, bold=False, color=DARK, bg=None, align=PP_ALIGN.LEFT):
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    cell.margin_left = Inches(0.1)
    cell.margin_right = Inches(0.1)
    cell.margin_top = Inches(0.06)
    cell.margin_bottom = Inches(0.06)
    if bg:
        cell.fill.solid()
        cell.fill.fore_color.rgb = bg
    tf = cell.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.name = FONT
    r.font.size = Pt(font_size)
    r.font.bold = bold
    r.font.color.rgb = color


def main():
    prs = new_prs()

    # 1. Title slide
    s = add_blank(prs)
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
    bg.fill.solid()
    bg.fill.fore_color.rgb = NAVY
    bg.line.fill.background()

    stripe = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(5.65), Inches(13.333), Inches(0.08))
    stripe.fill.solid()
    stripe.fill.fore_color.rgb = TEAL
    stripe.line.fill.background()

    tb = s.shapes.add_textbox(Inches(0.9), Inches(1.2), Inches(11.5), Inches(3.2))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "ТЕХНИЧЕСКИ УНИВЕРСИТЕТ – СОФИЯ  |  КАТЕДРА „АЕ“"
    r.font.name = FONT
    r.font.size = Pt(14)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0x7D, 0xD3, 0xFC)

    p2 = tf.add_paragraph()
    p2.space_before = Pt(18)
    r2 = p2.add_run()
    r2.text = "Мониторинг и диагностика на системи за електрозадвижване"
    r2.font.name = FONT
    r2.font.size = Pt(34)
    r2.font.bold = True
    r2.font.color.rgb = WHITE

    p3 = tf.add_paragraph()
    p3.space_before = Pt(14)
    r3 = p3.add_run()
    r3.text = "Общо въведение към лабораторни упражнения № 8, 9 и 10\n+ Практическа дискусия: Езикови модели (LLM) за студенти"
    r3.font.name = FONT
    r3.font.size = Pt(18)
    r3.font.color.rgb = RGBColor(0xE2, 0xE8, 0xF0)

    # 2. Agenda
    s = add_blank(prs)
    add_header(s, "План на днешното занятие", "Две свързани части: модерни AI инструменти за работа и експериментална диагностика на електрозадвижвания", "ПРОГРАМА", 2)
    add_card(s, 0.6, 1.65, 5.9, 5.1, "Част I: Езикови модели (LLM) в практиката", LIGHT_BG, BORDER, NAVY, TEAL)
    add_bullets(s, 0.85, 2.25, 5.4, 4.3, [
        ("Отворена дискусия: ", "кой какви модели ползва, за какви задачи и какви проблеми среща."),
        ("Инженерни практики: ", "как LLM да помагат за Python, анализ на данни и учене, без да заместват разбирането."),
        ("Студентски достъп и отстъпки: ", "какво дават безплатно или с намаление GitHub Copilot, Google Gemini, ChatGPT и Claude."),
    ], font_size=14, space_after=14)

    add_card(s, 6.83, 1.65, 5.9, 5.1, "Част II: Лабораторни упражнения № 8, 9 и 10", LIGHT_BG, BORDER, NAVY, AMBER)
    add_bullets(s, 7.08, 2.25, 5.4, 4.3, [
        ("Стендът и данните: ", "двигател 3PI12.06, преобразувател ELL 14010 и многосензорният набор DCData_mendeley."),
        ("ЛУ 9 (Токов анализ): ", "осцилоскопски записи, пулсации 300 Hz и честоти на въртене."),
        ("ЛУ 10 (Виброакустика): ", "виброметър AV-160B + микрофон, ISO 20816-1, спектри и спектрограми."),
        ("ЛУ 8 (Машинно обучение): ", "признаци, kNN / SVM / Random Forest и оценка по цели записи."),
        ("Код и протокол: ", "пакетът от Приложение 1 и изискванията по Приложение 2."),
    ], font_size=13.5, space_after=10)

    # 3. LLM Discussion
    s = add_blank(prs)
    add_header(s, "Дискусия: Кой какво ползва и как?", "Споделете реален опит преди да преминем към примерите и студентските планове", "ЧАСТ I • ДИСКУСИЯ", 3)
    qs = [
        ("1. Кои инструменти ползвате?", "ChatGPT, Gemini, Claude, GitHub Copilot, локални модели (Ollama) или друго?", SOFT_BLUE, TEAL),
        ("2. За какви задачи помагат?", "Писане на Python/MATLAB код, дебъгване, обяснение на теория, формули, превод, оформяне на текст?", SOFT_GREEN, GREEN),
        ("3. Къде моделът ви подведе?", "Измислени формули/цитати, неработещи библиотеки, уверен грешен отговор по математика?", SOFT_AMBER, AMBER),
        ("4. Как проверявате резултата?", "Пускате ли кода, сравнявате ли с учебника, четете ли грешките преди да копирате?", LIGHT_BG, NAVY),
    ]
    coords = [(0.6, 1.65), (6.83, 1.65), (0.6, 4.3), (6.83, 4.3)]
    for (x, y), (t, body, bgc, ac) in zip(coords, qs):
        add_card(s, x, y, 5.9, 2.4, t, bgc, BORDER, NAVY, ac)
        add_bullets(s, x + 0.2, y + 0.65, 5.5, 1.5, [body], font_size=14, bullet="")

    # 4. Smart use vs Traps
    s = add_blank(prs)
    add_header(s, "Как да ползваме LLM умно в инженерните упражнения", "Асистент за скорост и проверка — не заместител на инженерната преценка", "ЧАСТ I • ПРАКТИКА", 4)
    add_card(s, 0.6, 1.65, 5.9, 5.1, "Полезни практики (ДА)", SOFT_GREEN, BORDER, GREEN, GREEN)
    add_bullets(s, 0.85, 2.25, 5.4, 4.3, [
        ("Учене в диалог: ", "Study Mode / Learning Mode — искайте обяснение стъпка по стъпка и контролни въпроси."),
        ("Работа с код: ", "обяснение на непознати функции (SciPy, scikit-learn), оформяне на графики, диагностика на грешки в терминала."),
        ("Проверка на единици и размерности: ", "превръщане rad/s ↔ Hz ↔ rpm, проверка на мащаби."),
        ("Критично четене: ", "задавайте конкретен контекст (напр. „честотата на дискретизация е 44.1 kHz, прозорецът е 0.5 s“)."),
    ], font_size=13.5, space_after=12)

    add_card(s, 6.83, 1.65, 5.9, 5.1, "Чести капани (НЕ)", SOFT_RED, BORDER, RED, RED)
    add_bullets(s, 7.08, 2.25, 5.4, 4.3, [
        ("Сляпо доверие: ", "моделът може да измисли коефициент, стандарт (ISO) или параметър на функция."),
        ("Изгубен физичен смисъл: ", "напр. да приеме зададена скорост (30%) за измерена, или волтове (V) директно за ампери (A)."),
        ("Грешно разделяне в ML: ", "честа грешка в генериран код — случайно разделяне по прозорци вместо по цели записи."),
        ("Академична етика: ", "предаване на непонятен за вас текст или „украсени“ данни личи веднага при защита."),
    ], font_size=13.5, space_after=12)

    # 5. Student offers table
    s = add_blank(prs)
    add_header(s, "Безплатни и студентски опции при основните доставчици", "Проверено към ноември 2026 г. — изисква се валиден студентски статус / университетски имейл", "ЧАСТ I • ДОСТЪП", 5)
    tbl_shape = s.shapes.add_table(5, 4, Inches(0.6), Inches(1.65), Inches(12.13), Inches(4.55))
    t = tbl_shape.table
    widths = [Inches(2.1), Inches(3.2), Inches(4.33), Inches(2.5)]
    for i, w in enumerate(widths):
        t.columns[i].width = w
    headers = ["Доставчик", "Студентска / безплатна опция", "Какво включва за работа и учене", "Условие / бележка"]
    for c, h in enumerate(headers):
        style_cell(t.cell(0, c), h, 12.5, True, WHITE, NAVY)

    rows = [
        ("GitHub Copilot\n(Student Pack)", "Безплатен Copilot Student\n(education.github.com/pack)",
         "Неограничено дописване на код в VS Code, AI кредити, чат/агент; + GitHub Pro, PyCharm, Deepnote Team, $100 Azure кредити.",
         "Верификация на студентски статус (карта/имейл)."),
        ("Google Gemini", "Google AI Plus за учащи\n0 € за 1 година (gemini.google/students)",
         "По-високи лимити, учебни бележници, персонализирани тестове, Deep Research, Gemini Live, 400 GB. Отделно NotebookLM е безплатен.",
         "Оферта до 31.12.2026; след 1 г. 4,99 €/мес. (може отказ по всяко време)."),
        ("ChatGPT\n(OpenAI)", "Безплатен план\n+ институционален ChatGPT Edu",
         "Study Mode (насочващо учене), работа с PDF/снимки на схеми, уеб търсене и базово генериране на код.",
         "Няма постоянна глобална индивидуална студентска отстъпка за Plus."),
        ("Claude\n(Anthropic)", "Безплатен план (claude.ai)\n+ Claude for Education / API кредити",
         "Силен при Python код, анализ на грешки и Artifacts; Learning mode (сократов подход) в университетски програми.",
         "Институционален лиценз; студенти с проекти могат да кандидатстват за API кредити."),
    ]
    for r_idx, row in enumerate(rows, start=1):
        bgc = WHITE if r_idx % 2 == 1 else LIGHT_BG
        for c_idx, val in enumerate(row):
            style_cell(t.cell(r_idx, c_idx), val, 11.5, c_idx == 0, NAVY if c_idx == 0 else DARK, bgc)

    add_card(s, 0.6, 6.32, 12.13, 0.62, None, SOFT_BLUE, TEAL)
    add_bullets(s, 0.8, 6.44, 11.8, 0.4, [
        ("Практичен минимум за курса: ", "VS Code + безплатният GitHub Student Pack и безплатен Gemini/ChatGPT/Claude са напълно достатъчни.")
    ], font_size=12.5, bullet="")

    # 6. Overview of Labs 8, 9, 10
    s = add_blank(prs)
    add_header(s, "Част II: Общ поглед върху упражнения № 8, 9 и 10", "Три метода за мониторинг и диагностика върху един и същ лабораторен стенд", "ЧАСТ II • ПРЕГЛЕД", 6)
    cards = [
        ("ЛУ 9 • Анализ на тока", TEAL, [
            ("Сигнал: ", "ток на котвата с цифров осцилоскоп Rigol (.bin)."),
            ("Метод: ", "времеви показатели (RMS, размах, CF) + едностранен спектър (Хан)."),
            ("Цел: ", "откриване на пулсации (300 Hz), честота на въртене и настройка на РС/РТ."),
        ]),
        ("ЛУ 10 • Виброакустика", AMBER, [
            ("Сигнали: ", "виброметър AV-160B (.xls и .wav) + микрофон на телефон (.m4a)."),
            ("Метод: ", "статистика по скорости (10–100%), ISO 20816-1, FFT и STFT спектрограми."),
            ("Цел: ", "влияние на скоростта и разхлабения фундамент (контактно и безконтактно)."),
        ]),
        ("ЛУ 8 • Машинно обучение", GREEN, [
            ("Сигнал: ", "вибрационен WAV (44.1 kHz, 36 записа, 1599 прозореца по 0.5 s)."),
            ("Метод: ", "4 времеви + 7 честотни признака → kNN, SVM, Random Forest."),
            ("Цел: ", "класификация на 4 състояния с StratifiedGroupKFold по цели записи."),
        ]),
    ]
    for idx, (ctitle, col, bullets) in enumerate(cards):
        x = 0.6 + idx * 4.15
        add_card(s, x, 1.65, 3.85, 5.1, ctitle, LIGHT_BG, BORDER, NAVY, col)
        add_bullets(s, x + 0.18, 2.28, 3.49, 4.2, bullets, font_size=13, space_after=12)

    # 7. Test bench and 4 conditions
    s = add_blank(prs)
    add_header(s, "Изследваната система и четирите работни състояния", "Експериментална установка за ЛУ 8, 9 и 10 (работа без външен механичен товар)", "СТЕНД И РЕЖИМИ", 7)
    add_card(s, 0.6, 1.65, 5.9, 2.4, "Основни параметри на електрозадвижването", LIGHT_BG, BORDER, NAVY, TEAL)
    add_bullets(s, 0.85, 2.2, 5.4, 1.7, [
        ("Двигател: ", "четков СДПМ 3PI12.06 (55 V, 12.5 A, 2.7 Nm, 209.44 rad/s ≈ 2000 rpm)."),
        ("Преобразувател: ", "четириквадрантен тиристорен ELL 14010."),
        ("Измервания: ", "ток (Rigol MSO5074), вибрации (AV-160B), звук (телефон на ~1 m)."),
    ], font_size=13, space_after=8)

    add_card(s, 0.6, 4.25, 5.9, 2.5, "Четири сравнявани състояния (без реверсиране)", LIGHT_BG, BORDER, NAVY, AMBER)
    add_bullets(s, 0.85, 4.8, 5.4, 1.8, [
        ("Номинално: ", "РС (P05.04) = 10, РТ (P06.02) = 2, стегнато закрепване."),
        ("Разхлабен фундамент: ", "номинални настройки (10 / 2), разхлабени крепежни елементи."),
        ("Неоптимален РС: ", "понижено усилване на скоростния регулатор (0,2 / 2)."),
        ("Неоптимален РТ: ", "понижено усилване на токовия регулатор (10 / 0,1)."),
    ], font_size=12.5, space_after=6)

    add_card(s, 6.83, 1.65, 5.9, 5.1, "Структура на многосензорния набор (Mendeley Data)", WHITE, BORDER, NAVY)
    add_picture_fit(s, HERE / "figures_lab08" / "fig8_2_dataset.png", 6.95, 2.15, 5.66, 4.45)

    # 8. Data discipline / critical caveats
    s = add_blank(prs)
    add_header(s, "Критични правила при работа с данните (DCData_mendeley)", "Грешките при интерпретация идват не от кода, а от пренебрегване на измервателните условия", "МЕТОДИКА", 8)
    rules = [
        ("1. Последователни (несинхронизирани) записи",
         "Токът, вибрациите и звукът са записвани последователно при еднакви режими — не се сравняват момент по момент, а по честотни структури и статистики.", TEAL),
        ("2. Некалибрирани амплитуди",
         "Токът е във волтове (V) без известен коефициент A/V; WAV/M4A са в цифров пълен обхват (FS), а спектрограмите са в dB re 1 FS²/Hz (не SPL).", AMBER),
        ("3. Задание ≠ измерена скорост",
         "„30%“ или „50%“ е зададената стойност (напр. 62.83 rad/s при 30%), а не директно измерен оборот на вала.", NAVY),
        ("4. Повторни показания ≠ независими опити",
         "Последователните редове в .xls или отрязъците от един .wav запис не са независими експерименти — при ML те задължително остават в един и същ дял.", RED),
    ]
    for idx, (rt, rb, col) in enumerate(rules):
        y = 1.65 + idx * 1.3
        add_card(s, 0.6, y, 12.13, 1.15, rt, LIGHT_BG, BORDER, col)
        add_bullets(s, 0.85, y + 0.52, 11.6, 0.55, [rb], font_size=13, bullet="")

    # 9. Lab 9 spectra
    s = add_blank(prs)
    add_header(s, "ЛУ 9: Мониторинг чрез анализ на котвения ток", "Сравнение на четирите състояния при задание 30% (без реверсиране, интервал 2–4 s)", "УПРАЖНЕНИЕ № 9", 9)
    add_card(s, 0.6, 1.65, 4.6, 5.1, "Какво изчисляваме и търсим", LIGHT_BG, BORDER, NAVY, TEAL)
    add_bullets(s, 0.8, 2.22, 4.2, 4.3, [
        ("Времева област: ", "отстраняване на средното отместване; RMS на променливата съставка, размах (Xpp) и крест-фактор (CF)."),
        ("Спектър (Хан, Δf ≈ 0.5 Hz): ", "едностранен амплитуден спектър (без допълване с нули и без индивидуална нормализация)."),
        ("Честоти на преобразувателя: ", "fp = 6·50 = 300 Hz и хармоници 600, 900, 1200 Hz."),
        ("Скоростно зависими: ", "честота на въртене fr = ω/(2π) и колекторна честота fk = m·Zk·fr."),
    ], font_size=12.5, space_after=10)
    add_card(s, 5.45, 1.65, 7.28, 5.1, "Едностранни амплитудни спектри (Фиг. 9.6)", WHITE, BORDER, NAVY)
    add_picture_fit(s, HERE / "figures_lab09" / "fig9_6_current_spectra.png", 5.55, 2.15, 7.08, 4.45)

    # 10. Lab 9 waveforms + takeaway
    s = add_blank(prs)
    add_header(s, "ЛУ 9: Времедиаграми и диагностични ограничения", "Еднаквият мащаб по осите позволява пряко сравнение на формата и амплитудата на пулсациите", "УПРАЖНЕНИЕ № 9", 10)
    add_card(s, 0.6, 1.65, 7.35, 5.1, "Общ изглед 2 s и детайл 60 ms = 18 периода на 300 Hz (Фиг. 9.5)", WHITE, BORDER, NAVY)
    add_picture_fit(s, HERE / "figures_lab09" / "fig9_5_current_waveforms.png", 0.72, 2.15, 7.1, 4.45)

    add_card(s, 8.2, 1.65, 4.53, 5.1, "Важни изводи при анализа", SOFT_AMBER, BORDER, NAVY, AMBER)
    add_bullets(s, 8.42, 2.22, 4.1, 4.3, [
        ("Визуализация vs. сметки: ", "обвивката min/max служи само за прегледност; RMS и FFT се смятат от всички оригинални проби."),
        ("Разхлабен фундамент: ", "липсата на отчетлива разлика в тока НЕ доказва, че закрепването е изправно."),
        ("Настройка на регулаторите: ", "само по токовия запис не се определят пререгулирането и времето за установяване — нужен е и запис на скоростта."),
    ], font_size=12.5, space_after=12)

    # 11. Lab 10 vibroacoustics
    s = add_blank(prs)
    add_header(s, "ЛУ 10: Виброакустичен анализ (AV-160B и микрофон)", "Оценка по скорости (10–100%), стандарт ISO 20816-1 и спектрално сравнение при 50%", "УПРАЖНЕНИЕ № 10", 11)
    add_card(s, 0.6, 1.65, 4.6, 5.1, "Методика на измерване", LIGHT_BG, BORDER, NAVY, AMBER)
    add_bullets(s, 0.8, 2.22, 4.2, 4.3, [
        ("Виброметър (.xls): ", "вибропреместване (mm), -скорост (mm/s) и -ускорение (m/s²) при 10, 20, 50, 80, 100%."),
        ("ISO 20816-1: ", "общи принципи — при малки лабораторни двигатели границите за големи машини не се прилагат механично."),
        ("Непрекъснат запис (.wav): ", "аудиоизход на виброметъра при 50% (2–6 s, Δf = 0.25 Hz)."),
        ("Акустика (.m4a): ", "телефон на ~1 m; зависи от помещението и околния шум."),
    ], font_size=12.5, space_after=10)
    add_card(s, 5.45, 1.65, 7.28, 5.1, "Амплитудни спектри при нормално и разхлабено закрепване (Фиг. 10.4)", WHITE, BORDER, NAVY)
    add_picture_fit(s, HERE / "figures_lab10" / "fig10_4_amplitude_spectra.png", 5.55, 2.15, 7.08, 4.45)

    # 12. Lab 10 spectrograms
    s = add_blank(prs)
    add_header(s, "ЛУ 10: Време-честотен анализ (спектрограми STFT)", "Сравнение между вибрационен (AV-160B) и акустичен (телефон) канал при 50%", "УПРАЖНЕНИЕ № 10", 12)
    add_card(s, 0.6, 1.65, 7.65, 5.1, "Спектрограми STFT: Hann 2048 проби, припокриване 1024 (Фиг. 10.5)", WHITE, BORDER, NAVY)
    add_picture_fit(s, HERE / "figures_lab10" / "fig10_5_spectrograms.png", 0.72, 2.15, 7.4, 4.45)

    add_card(s, 8.5, 1.65, 4.23, 5.1, "Как четем спектрограмите", LIGHT_BG, BORDER, NAVY, TEAL)
    add_bullets(s, 8.72, 2.22, 3.8, 4.3, [
        ("Еднакви скали: ", "обхват 80 dB под максимума в рамките на една модалност (вибрация или звук)."),
        ("Без пряко сравнение по ниво: ", "WAV и M4A са с различни датчици и не са амплитудно калибрирани помежду си."),
        ("Фокус на анализа: ", "сравняваме кои честотни ленти се появяват, изместват или засилват при разхлабване."),
    ], font_size=12.5, space_after=12)

    # 13. Lab 8 ML pipeline
    s = add_blank(prs)
    add_header(s, "ЛУ 8: Диагностика чрез машинно обучение", "От суров вибрационен WAV сигнал до оценка на класификатори по цели записи", "УПРАЖНЕНИЕ № 8", 13)
    add_card(s, 0.6, 1.65, 7.2, 4.0, "Структурна схема на обработката (Фиг. 8.1)", WHITE, BORDER, NAVY)
    add_picture_fit(s, HERE / "figures_lab08" / "fig8_1_pipeline.png", 0.72, 2.12, 6.96, 3.4)

    add_card(s, 8.05, 1.65, 4.68, 4.0, "Признаци (11 общо) и модели", LIGHT_BG, BORDER, NAVY, GREEN)
    add_bullets(s, 8.25, 2.18, 4.3, 3.3, [
        ("Сегментиране: ", "пропуск 1 s, прозорци по 0.5 s (22 050 отчета при 44.1 kHz)."),
        ("4 времеви: ", "RMS, размах (PTP), CF, куртозис (Pearson)."),
        ("7 честотни: ", "относителна мощност в ленти 0–10 kHz (периодограма с прозорец на Хан)."),
        ("Модели: ", "kNN (k=5), SVM (RBF), Random Forest (200 дървета); Z-оценка само по train."),
    ], font_size=12, space_after=8)

    add_card(s, 0.6, 5.82, 12.13, 1.0, None, SOFT_GREEN, GREEN)
    add_bullets(s, 0.82, 5.95, 11.7, 0.75, [
        ("Валидиране без изтичане на данни: ",
         "StratifiedGroupKFold с 5 дяла по цели записи (всички прозорци от един запис са заедно). "
         "Финалният клас на записа се определя чрез мнозинство (36 записа, по 9 за състояние).")
    ], font_size=12.5, bullet="")

    # 14. Lab 8 results
    s = add_blank(prs)
    add_header(s, "ЛУ 8: Резултати и влияние на диагностичните признаци", "Показатели на ниво запис (извънобучаващи предсказвания върху 36 записа)", "УПРАЖНЕНИЕ № 8", 14)

    t1 = s.shapes.add_table(4, 3, Inches(0.6), Inches(1.65), Inches(5.6), Inches(1.85)).table
    for i, w in enumerate([Inches(2.4), Inches(1.6), Inches(1.6)]):
        t1.columns[i].width = w
    for c, h in enumerate(["Метод (11 признака)", "Accuracy, %", "Macro-F1"]):
        style_cell(t1.cell(0, c), h, 11.5, True, WHITE, NAVY, PP_ALIGN.CENTER if c else PP_ALIGN.LEFT)
    for r, row in enumerate([("kNN", "44.4", "0.454"), ("SVM (RBF)", "63.9", "0.641"), ("Random Forest", "55.6", "0.560")], start=1):
        for c, val in enumerate(row):
            style_cell(t1.cell(r, c), val, 11.5, r == 2 and c == 0, DARK, WHITE if r % 2 else LIGHT_BG,
                       PP_ALIGN.CENTER if c else PP_ALIGN.LEFT)

    t2 = s.shapes.add_table(4, 4, Inches(6.5), Inches(1.65), Inches(6.23), Inches(1.85)).table
    for i, w in enumerate([Inches(2.63), Inches(1.1), Inches(1.1), Inches(1.4)]):
        t2.columns[i].width = w
    for c, h in enumerate(["Група признаци (Macro-F1)", "kNN", "SVM", "Random Forest"]):
        style_cell(t2.cell(0, c), h, 11.5, True, WHITE, TEAL, PP_ALIGN.CENTER if c else PP_ALIGN.LEFT)
    for r, row in enumerate([
        ("Само времева област (4)", "0.264", "0.044", "0.260"),
        ("Само честотна област (7)", "0.637", "0.418", "0.594"),
        ("Времева + честотна (11)", "0.454", "0.641", "0.560"),
    ], start=1):
        for c, val in enumerate(row):
            style_cell(t2.cell(r, c), val, 11.5, False, DARK, WHITE if r % 2 else LIGHT_BG,
                       PP_ALIGN.CENTER if c else PP_ALIGN.LEFT)

    add_card(s, 0.6, 3.72, 12.13, 3.18, "Матрици на объркванията по записи (Фиг. 8.4)", WHITE, BORDER, NAVY)
    add_picture_fit(s, HERE / "figures_lab08" / "fig8_4_confusion.png", 0.8, 4.18, 11.7, 2.62)

    # 15. Running code & lab protocol
    s = add_blank(prs)
    add_header(s, "Работа с програмния пакет (Приложение 1) и протокола", "Възпроизвеждане на резултатите и оформление по Приложение 2", "ПРАКТИЧЕСКИ СТЪПКИ", 15)
    add_card(s, 0.6, 1.65, 7.2, 5.1, "Команди за работа (labs_8_9_10_software_v1.0.zip)", LIGHT_BG, BORDER, NAVY, TEAL)
    add_bullets(s, 0.82, 2.22, 6.76, 1.2, [
        ("Среда: ", "64-битов Python 3.11+ (виртуална среда), архивът и данните са в отделни папки."),
        ("Инсталация: ", "python -m pip install -r requirements_all.txt"),
    ], font_size=12.5, space_after=6)

    code_box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.82), Inches(3.25), Inches(6.76), Inches(2.2))
    code_box.adjustments[0] = 0.04
    code_box.fill.solid()
    code_box.fill.fore_color.rgb = RGBColor(0x0F, 0x17, 0x2A)
    code_box.line.fill.background()
    ctf = code_box.text_frame
    ctf.word_wrap = True
    ctf.margin_left = ctf.margin_right = Inches(0.18)
    ctf.margin_top = Inches(0.14)
    cp = ctf.paragraphs[0]
    cr = cp.add_run()
    cr.text = (
        "# Упражнение 8 (ML диагностика)\n"
        'python lab8/lab8_ml.py "C:/work/DCData_mendeley" --output "../results8"\n\n'
        "# Упражнение 9 (Токов анализ)\n"
        'python lab9/plot_lab_current.py "C:/work/DCData_mendeley" --speed 30 --output "../results9"\n\n'
        "# Упражнение 10 (Виброакустика)\n"
        'python lab10/lab10_vibroacoustics.py "C:/work/DCData_mendeley" --output "../results10"'
    )
    cr.font.name = "Consolas"
    cr.font.size = Pt(10.2)
    cr.font.color.rgb = RGBColor(0xE2, 0xE8, 0xF0)

    add_bullets(s, 0.82, 5.6, 6.76, 1.0, [
        ("Забележка: ", "при повторно пускане №8 и №10 искат нова папка или --overwrite; всеки скрипт записва provenance JSON с параметрите и SHA-256.")
    ], font_size=11.5, space_after=4)

    add_card(s, 8.05, 1.65, 4.68, 5.1, "Изисквания към протокола", LIGHT_BG, BORDER, NAVY, AMBER)
    add_bullets(s, 8.28, 2.22, 4.22, 4.3, [
        ("Структура (Приложение 2): ", "Задачи, Кратки теоретични сведения, Схема, Резултати, Анализ и изводи."),
        ("Проследимост: ", "посочете версията на програмния пакет, командата и DOI/версията на набора."),
        ("Собствена интерпретация: ", "включете графиките/таблиците и отговорете на контролните въпроси."),
        ("Готови за старт: ", "въпроси преди да преминем към упражненията?"),
    ], font_size=12.5, space_after=12)

    prs.save(OUT)
    print("OK", OUT)


if __name__ == "__main__":
    main()
