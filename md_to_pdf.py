#!/usr/bin/env python3
"""
Convert a Markdown report to a self-contained PDF.

Designed for analysis_findings.md (with embedded images/ screenshots) so the
result can be e-mailed to colleagues. Pure-Python stack (markdown + xhtml2pdf),
so it needs no system libraries — works out-of-the-box on Windows.

Dependencies:
    pip install markdown xhtml2pdf pygments

Usage:
    python md_to_pdf.py                          # analysis_findings.md -> analysis_findings.pdf
    python md_to_pdf.py report.md                # report.md -> report.pdf
    python md_to_pdf.py report.md out.pdf        # explicit output name
"""

from __future__ import annotations

import os
import re
import sys

import markdown
from xhtml2pdf import pisa


# Simple print-friendly stylesheet (xhtml2pdf supports a subset of CSS 2.1).
CSS = """
@page { size: A4; margin: 1.8cm 1.6cm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 10.5pt;
       line-height: 1.4; color: #1a1a1a; }
h1 { font-size: 20pt; color: #0b3d66; border-bottom: 2px solid #0b3d66;
     padding-bottom: 4px; margin-top: 4px; }
h2 { font-size: 15pt; color: #0b3d66; border-bottom: 1px solid #bcd; margin-top: 18px; }
h3 { font-size: 12.5pt; color: #145a8d; margin-top: 14px; }
h4 { font-size: 11pt; color: #145a8d; }
p, li { font-size: 10.5pt; }
code { font-family: "Courier New", monospace; background: #f2f4f7;
       padding: 1px 3px; font-size: 9.5pt; }
pre { background: #f2f4f7; border: 1px solid #d6dde5; padding: 8px;
      font-size: 9pt; white-space: pre-wrap; }
table { border-collapse: collapse; width: 100%; margin: 8px 0;
        table-layout: fixed; }
th, td { border: 1px solid #b9c4cf; padding: 4px 6px; font-size: 9pt;
         text-align: left; vertical-align: top;
         word-wrap: break-word; word-break: break-word; }
th { background: #e7eef5; color: #0b3d66; }
blockquote { border-left: 3px solid #9bbcd6; margin: 8px 0; padding: 4px 10px;
             color: #33475b; background: #f6f9fc; }
img { max-width: 480px; }
hr { border: 0; border-top: 1px solid #ccd; }
"""


def normalize_unicode(text: str) -> str:
    """
    Replace Unicode super/subscript digits with ASCII forms.

    The built-in xhtml2pdf fonts (Helvetica family) have no glyphs for these,
    so they render as black boxes. Superscript runs become '^n', subscript
    runs become plain digits (e.g. 'log\u2081\u2080' -> 'log10').
    """
    sup = {"\u2070": "0", "\u00b9": "1", "\u00b2": "2", "\u00b3": "3",
           "\u2074": "4", "\u2075": "5", "\u2076": "6", "\u2077": "7",
           "\u2078": "8", "\u2079": "9"}
    sub = {"\u2080": "0", "\u2081": "1", "\u2082": "2", "\u2083": "3",
           "\u2084": "4", "\u2085": "5", "\u2086": "6", "\u2087": "7",
           "\u2088": "8", "\u2089": "9"}

    def sup_run(m: re.Match) -> str:
        return "^" + "".join(sup[c] for c in m.group(0))

    def sub_run(m: re.Match) -> str:
        return "".join(sub[c] for c in m.group(0))

    text = re.sub("[" + "".join(sup) + "]+", sup_run, text)
    text = re.sub("[" + "".join(sub) + "]+", sub_run, text)
    return text


def add_colgroups(html: str) -> str:
    """
    Inject an explicit <colgroup> into every table.

    xhtml2pdf does not auto-size table columns; without explicit widths the
    cells overlap. We give the first column (row labels) a bit more room and
    split the remainder evenly across the other columns.
    """
    def repl(match: re.Match) -> str:
        table = match.group(0)
        # An empty leading header cell (from a "| |" markdown header) gets
        # dropped by xhtml2pdf, collapsing the column. Give it content so the
        # column is preserved and body cells line up with the header.
        table = re.sub(r"<th>\s*</th>", "<th>&#160;</th>", table)
        header = re.search(r"<tr>(.*?)</tr>", table, re.DOTALL)
        ncols = len(re.findall(r"<th", header.group(1))) if header else 0
        if ncols < 2:
            return table
        first = 26  # percent for the label column
        rest = (100 - first) / (ncols - 1)
        cols = f'<col width="{first}%"/>' + \
            f'<col width="{rest:.4f}%"/>' * (ncols - 1)
        return table.replace(
            "<table>", f"<table><colgroup>{cols}</colgroup>", 1)

    return re.sub(r"<table>.*?</table>", repl, html, flags=re.DOTALL)


def link_callback(uri: str, rel: str) -> str:
    """Resolve relative image/resource paths to absolute filesystem paths."""
    if uri.startswith(("http://", "https://", "data:")):
        return uri
    base = link_callback.base_dir  # type: ignore[attr-defined]
    path = os.path.normpath(os.path.join(base, uri))
    if not os.path.exists(path):
        print(f"  [warning] resource not found: {uri}")
    return path


def convert(md_path: str, pdf_path: str) -> bool:
    with open(md_path, "r", encoding="utf-8") as fh:
        md_text = fh.read()

    md_text = normalize_unicode(md_text)

    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "codehilite", "toc", "sane_lists"],
        extension_configs={"codehilite": {"noclasses": True}},
    )

    html_body = add_colgroups(html_body)

    html = (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{CSS}</style></head><body>{html_body}</body></html>"
    )

    link_callback.base_dir = os.path.dirname(os.path.abspath(md_path))  # type: ignore[attr-defined]

    try:
        with open(pdf_path, "wb") as out:
            result = pisa.CreatePDF(html, dest=out, link_callback=link_callback)
    except PermissionError:
        print(f"[!] Cannot write {pdf_path} — the file is open in another "
              f"program (e.g. a PDF viewer). Close it and run again.")
        return False

    if result.err:
        print(f"[!] PDF generation reported {result.err} error(s).")
        return False
    return True


def main() -> None:
    args = sys.argv[1:]
    here = os.path.dirname(os.path.abspath(__file__))

    md_path = args[0] if args else os.path.join(here, "analysis_findings.md")
    if len(args) >= 2:
        pdf_path = args[1]
    else:
        pdf_path = os.path.splitext(md_path)[0] + ".pdf"

    if not os.path.exists(md_path):
        print(f"[!] Markdown file not found: {md_path}")
        sys.exit(1)

    print(f"Converting: {md_path}")
    print(f"      ->    {pdf_path}")
    ok = convert(md_path, pdf_path)
    if ok:
        size_kb = os.path.getsize(pdf_path) / 1024
        print(f"Done. {pdf_path} ({size_kb:.0f} KB)")
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
