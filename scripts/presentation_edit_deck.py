"""Apply the presentation edits to the team's deck (keeps its wording and look).

    python3 scripts/presentation_edit_deck.py IN.pptx OUT.pptx [--figures docs/presentation/figures]

Edits: front camera is 30 fps (take.json), pipeline table becomes a storyboard of one
real throw, a new data slide (outcomes, landing map, miss causes), a conclusion slide,
slide 7 fixed and moved to backup, page numbers updated. Figures come from
scripts/presentation_figures.py.
"""

from __future__ import annotations

import argparse
import copy
import os
import re

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INK, MUTED, RULE, CARD = "1C1A17", "57514A", "E3DCCF", "FFFEFB"
BLUE, GOLD, RED, GREY = "2F5D8A", "8A6A2B", "A8432A", "6E665C"
FONT = "Times New Roman"


def rgb(h):
    return RGBColor.from_string(h)


def shape_by_text(slide, start):
    for sh in slide.shapes:
        if sh.has_text_frame and sh.text_frame.text.startswith(start):
            return sh
    raise KeyError(start)


def set_text(shape, text):
    """Replace a shape's text, keeping the first run's formatting."""
    tf = shape.text_frame
    p0 = tf.paragraphs[0]
    for p in tf.paragraphs[1:]:
        p._p.getparent().remove(p._p)
    runs = p0.runs
    for r in runs[1:]:
        r._r.getparent().remove(r._r)
    runs[0].text = text


def replace_in_runs(slide, old, new):
    hit = False
    for sh in slide.shapes:
        frames = []
        if sh.has_text_frame:
            frames.append(sh.text_frame)
        if sh.has_table:
            frames += [c.text_frame for row in sh.table.rows for c in row.cells]
        for tf in frames:
            for p in tf.paragraphs:
                full = "".join(r.text for r in p.runs)
                if old not in full:
                    continue
                hit = True
                if any(old in r.text for r in p.runs):
                    for r in p.runs:
                        r.text = r.text.replace(old, new)
                else:  # text split across runs: merge into the first run
                    p.runs[0].text = full.replace(old, new)
                    for r in p.runs[1:]:
                        r._r.getparent().remove(r._r)
    assert hit, old


def card(slide, x, y, w, h, fill=CARD, line=RULE):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    s.adjustments[0] = 0.02
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(1)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    s.text_frame.text = ""
    return s


def text(slide, x, y, w, h, runs, size=12, color=MUTED, bold=False, italic=False, align=PP_ALIGN.LEFT,
         spacing=1.3, anchor=MSO_ANCHOR.TOP):
    """runs: str, or list of paragraphs; each paragraph a str or list of (text, overrides) tuples."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        for seg, over in ([(para, {})] if isinstance(para, str) else para):
            r = p.add_run()
            r.text = seg
            f = r.font
            f.name = FONT
            f.size = Pt(over.get("size", size))
            f.bold = over.get("bold", bold)
            f.italic = over.get("italic", italic)
            f.color.rgb = rgb(over.get("color", color))
    return tb


def new_slide_like(prs, template, label, title):
    """New slide on the template's layout, with its section label, title and footers copied."""
    s = prs.slides.add_slide(template.slide_layout)
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    keep = [sh for sh in template.shapes if sh.top > Inches(6.7) or sh.top < Inches(1.6)]
    for sh in keep:
        s.shapes._spTree.append(copy.deepcopy(sh._element))
    bg = template._element.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}bg")
    if bg is not None:
        s._element.cSld.insert(0, copy.deepcopy(bg))
    set_text(shape_by_text(s, template.shapes[0].text_frame.text), label)
    set_text(s.shapes.title, title)
    return s


def move_slide(prs, slide, index):
    lst = prs.slides._sldIdLst
    el = next(e for e in lst if prs.part.related_part(e.rId) is slide.part)
    lst.remove(el)
    lst.insert(index, el)


def picture(slide, path, x, y, w=None, h=None):
    return slide.shapes.add_picture(path, Inches(x), Inches(y),
                                    Inches(w) if w else None, Inches(h) if h else None)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--figures", default=os.path.join(ROOT, "docs", "presentation", "figures"))
    a = ap.parse_args()
    fig = lambda n: os.path.join(a.figures, n)  # noqa: E731

    prs = Presentation(a.src)
    S = list(prs.slides)  # original order, 0-based

    # --- slide 4: the front phone records 30 fps (take.json: 1280x720 at 30 fps)
    replace_in_runs(S[3], "Front phone (60 fps)", "Front phone (30 fps)")
    replace_in_runs(S[3], "front (60 fps)", "front (30 fps)")

    # --- slide 7: the bottom cards sat on the table's last row
    for sh in S[6].shapes:
        if Inches(4.3) < sh.top < Inches(6.0):
            sh.top = sh.top + Inches(0.55)

    # --- slide 9: table -> storyboard of one real throw
    s9 = S[8]
    replace_in_runs(s9, "front 60 fps", "front 30 fps")
    table = [sh for sh in s9.shapes if sh.has_table][0]
    table._element.getparent().remove(table._element)
    pic = picture(s9, fig("pipeline_storyboard.png"), 0.90, 3.12, w=11.54)
    text(s9, 0.90, 3.12 + pic.height / 914400 + 0.08, 11.54, 0.25,
         [[("One real throw through the six steps: ", {"bold": True, "color": INK}),
           ("Player 1, Take 6, Throw 1. Every number on this strip is the engine's own output for that throw.", {})]],
         size=11)
    n9 = s9.notes_slide.notes_text_frame
    n9.text = n9.text + (" [Strip below the boxes: this is one real throw, Player 1 Take 6 Throw 1. "
                         "Sync shifted the front phone 213 ms; the pose model finds the body; 68 bag points "
                         "follow a drag-free arc; the bag's own fall gives 211 px per metre and 10.0 m/s², "
                         "close to gravity; release 7.7 m/s at 41°; it landed short and slid in, so the "
                         "advice is: nothing to change.]")

    # --- slide 13: the third insight now carries its counts
    s13 = S[12]
    set_text(shape_by_text(s13, "The slide was named"),
             "The slide was named 31 times; the carry 23 (44 explained misses).")
    n13 = s13.notes_slide.notes_text_frame
    n13.text = re.sub(r"\s*\[Check per-athlete values[^\]]*\]", "", n13.text)

    # --- new data slide after 13
    d = new_slide_like(prs, s13, "PART 4 · WHERE THE 92 THROWS WENT",
                       "Same release, very different results")
    card(d, 0.90, 1.75, 3.30, 4.85)
    text(d, 1.10, 1.92, 2.95, 0.26, "First contact on the board", size=14, color=INK, bold=True)
    text(d, 1.10, 2.20, 2.95, 0.40, "Each dot is where a bag first touched (81 located).", size=11)
    picture(d, fig("landing_map.png"), 1.20, 2.62, h=3.10)
    text(d, 1.10, 5.80, 2.95, 0.70,
         [[("Hole shots land about 18 in short and slide in.", {"color": BLUE, "bold": True})]], size=12)

    card(d, 4.40, 1.75, 8.04, 2.35)
    picture(d, fig("outcomes_by_athlete.png"), 4.55, 1.88, h=2.05)
    text(d, 9.25, 1.92, 3.05, 0.26, "Outcome per athlete", size=14, color=INK, bold=True)
    text(d, 9.25, 2.22, 3.05, 1.20,
         "18 hole · 38 board · 36 off. All four release near 7.5 m/s, yet PPR runs from 1.4 to 6.0.", size=12)
    text(d, 9.25, 3.45, 3.05, 0.50, [[("→ Consistency, not power, sets the score.", {"color": BLUE, "bold": True})]],
         size=12)

    card(d, 4.40, 4.25, 8.04, 2.35)
    picture(d, fig("miss_causes.png"), 4.55, 4.37, h=2.10)
    text(d, 9.25, 4.42, 3.05, 0.26, "What each miss came from", size=14, color=INK, bold=True)
    text(d, 9.25, 4.72, 3.05, 1.20,
         "Parts the app named above noise in 44 misses. The flight (39) and the slide on the board (31) are close.",
         size=12)
    text(d, 9.25, 5.95, 3.05, 0.50, [[("→ Train board feel, not only the arm.", {"color": RED, "bold": True})]],
         size=12)
    d.notes_slide.notes_text_frame.text = (
        "ELIAM (0:35). Here is the whole data set in one picture. Left: where every bag first touched the board. "
        "The hole shots, in blue, landed about 18 inches short and slid in, so the slide is part of a good shot. "
        "Top: outcomes per athlete. 18 in the hole, 38 on the board, 36 off. All four release at about 7.5 m/s, "
        "yet points per round run from 1.4 to 6.0, so it is consistency, not power, that sets the score. "
        "Bottom: for the 44 misses the app could explain above noise, which part it named. The carry is the "
        "single biggest part, but the slide along and across the board adds up to 31 against 39 for the flight. "
        "So practice time should go to board feel as well as release speed.")
    move_slide(prs, d, 13)

    # --- conclusion slide before the share-out
    c = new_slide_like(prs, S[14], "CONCLUSION", "What we built, what we found, what comes next")
    cols = [
        ("WE BUILT", "2 phones", "and a Mac, no sensors",
         "A system that links the body to the release, the landing and the score, synced by sound and "
         "checked against gravity, then gives one sentence per throw.", BLUE),
        ("WE FOUND", "13 cm", "per 0.1 m/s of release speed",
         "Speed consistency, not angle or power, drives short and long misses; and the slide on the board "
         "matters almost as much as the flight.", GOLD),
        ("WHAT COMES NEXT", "4–6 weeks", "to prove it raises PPR",
         "Alternate weeks with and without app feedback, 40 throws per athlete per week, plus a blinded "
         "20-throw validation check.", RED),
    ]
    for i, (lab, big, small, body, col) in enumerate(cols):
        x = 0.90 + i * 3.92
        card(c, x, 1.85, 3.70, 3.25)
        text(c, x + 0.22, 2.05, 3.30, 0.26, lab, size=12, color=col, bold=True)
        text(c, x + 0.22, 2.35, 3.30, 0.70, big, size=36, color=col, bold=True, spacing=1.0)
        text(c, x + 0.22, 3.08, 3.30, 0.30, small, size=12, color=INK, italic=True)
        text(c, x + 0.22, 3.55, 3.30, 1.60, body, size=12)
    card(c, 0.90, 5.45, 11.54, 0.95, fill=INK, line=None)
    text(c, 1.15, 5.45, 2.0, 0.95, "TAKE-HOME", size=12, color="C9A45C", bold=True, anchor=MSO_ANCHOR.MIDDLE)
    text(c, 3.00, 5.45, 9.30, 0.95,
         "Measure the throw. Explain the miss. Coach only what the data supports.",
         size=18, color="FFFFFF", italic=True, anchor=MSO_ANCHOR.MIDDLE)
    c.notes_slide.notes_text_frame.text = (
        "ELIAM (0:25). To sum up. We built a two-phone, sensor-free system that links the body to the release, "
        "the landing and the score, and turns each throw into one sentence. We found that speed consistency, not "
        "angle or power, drives short and long misses, and that the slide on the board matters almost as much as "
        "the flight. What comes next is proving it raises scores, with an alternating-weeks study and a blinded "
        "validation check. Measure the throw, explain the miss, coach only what the data supports.")
    move_slide(prs, c, 16)

    # --- slide 7 becomes backup at the end
    s7 = S[6]
    move_slide(prs, s7, len(prs.slides) - 1)
    set_text(shape_by_text(s7, "PART 2 · INTERPRETING"), "BACKUP · INTERPRETING THE NUMBERS")

    # --- page numbers: "Name · N / 16" -> current position / main-deck count
    main = len(prs.slides) - 1
    for i, s in enumerate(prs.slides, start=1):
        for sh in s.shapes:
            if sh.has_text_frame and re.search(r"· \d+ / 16$", sh.text_frame.text):
                new = (re.sub(r"\d+ / 16$", f"{i} / {main}", sh.text_frame.text) if i <= main
                       else re.sub(r"\d+ / 16$", "backup", sh.text_frame.text))
                set_text(sh, new)
    prs.save(a.dst)
    print("saved", a.dst, len(prs.slides), "slides")


if __name__ == "__main__":
    main()
