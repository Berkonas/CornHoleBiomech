"""Apply the presentation edits to the team's deck (keeps its wording and look).

    python3 scripts/presentation_edit_deck.py IN.pptx OUT.pptx [--figures docs/presentation/figures]

Result: 12 main slides (about 8.5 min by the speaker notes) and the rest as backup.
New: two-camera slide (what each phone sees, why we sync), pose-model + calculations
slide, biomechanics statistics slide, data slide, conclusion with lessons. The pipeline
table becomes a storyboard of one real throw. Front camera is 30 fps (take.json).
Figures come from scripts/presentation_figures.py.
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


def fit_picture(slide, path, x, y, w, h):
    """Largest picture that fits the box, centred in it."""
    from PIL import Image
    iw, ih = Image.open(path).size
    s = min(w / iw, h / ih)
    return picture(slide, path, x + (w - iw * s) / 2, y + (h - ih * s) / 2, w=iw * s)


def picture(slide, path, x, y, w=None, h=None):
    return slide.shapes.add_picture(path, Inches(x), Inches(y),
                                    Inches(w) if w else None, Inches(h) if h else None)


def set_footer(slide, name, page):
    for sh in slide.shapes:
        if sh.has_text_frame and re.search(r"· (\d+ / \d+|backup)$", sh.text_frame.text):
            set_text(sh, f"{name} · {page}")
            return
    raise KeyError("footer")


def notes(slide, text_):
    slide.notes_slide.notes_text_frame.text = text_


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--figures", default=os.path.join(ROOT, "docs", "presentation", "figures"))
    a = ap.parse_args()
    fig = lambda n: os.path.join(a.figures, n)  # noqa: E731

    prs = Presentation(a.src)
    O = {i + 1: s for i, s in enumerate(prs.slides)}  # original slides, 1-based

    # --- fixes on kept slides
    replace_in_runs(O[4], "Front phone (60 fps)", "Front phone (30 fps)")
    replace_in_runs(O[4], "front (60 fps)", "front (30 fps)")
    for sh in O[7].shapes:  # bottom cards sat on the table's last row
        if Inches(4.3) < sh.top < Inches(6.0):
            sh.top = sh.top + Inches(0.55)
    set_text(shape_by_text(O[13], "The slide was named"),
             "The slide was named 31 times; the carry 23 (44 explained misses).")
    n13 = O[13].notes_slide.notes_text_frame
    n13.text = re.sub(r"\s*\[Check per-athlete values[^\]]*\]", "", n13.text)

    # --- pipeline (orig 9): table -> storyboard of one real throw
    s9 = O[9]
    replace_in_runs(s9, "front 60 fps", "front 30 fps")
    set_text(shape_by_text(s9, "PART 3"), "PART 3 · HOW THE APP WORKS")
    table = [sh for sh in s9.shapes if sh.has_table][0]
    table._element.getparent().remove(table._element)
    pic = picture(s9, fig("pipeline_storyboard.png"), 0.90, 3.12, w=11.54)
    text(s9, 0.90, 3.12 + pic.height / 914400 + 0.08, 11.54, 0.25,
         [[("One real throw through the six steps: ", {"bold": True, "color": INK}),
           ("Player 1, Take 6, Throw 1. Every number on this strip is the engine's own output for that throw.", {})]],
         size=11)
    notes(s9, "BERK (0:40). This is the app end to end, on one real throw. The coach drops a take folder on the Mac; "
              "a Python engine runs about two minutes per throw. One: sync the phones by sound, here a 213 ms shift. "
              "Two: Sports2D finds the body on every frame and we smooth it at 6 Hz. Three: find the bag; we keep only "
              "a path that falls like a real bag, 68 points here, against the dashed drag-free fit. Four: turn pixels "
              "into metres, 211 px per metre, checked by the bag's own fall: 10.0 m/s², close to gravity. Five: "
              "release 7.7 m/s at 41 degrees, 0.95 m high; it landed short and slid into the hole. Six: the advice. "
              "A made throw gets no corrections: in the hole, nothing to change.")

    # --- NEW: two cameras, two jobs, one timeline (Emily)
    cam = new_slide_like(prs, O[4], "PART 2 · OUR SOLUTION AND WHY", "Two cameras, two jobs, one timeline")
    hc = 2.75
    picture(cam, fig("camera_side.png"), 0.90, 1.85, h=hc)
    xr = 12.44 - hc * 1.202
    picture(cam, fig("camera_front.png"), xr, 1.85, h=hc)
    text(cam, 0.90, 4.68, xr - 1.15, 0.8, [
        [("SIDE PHONE · beside the lane · 1080p, 60 fps", {"bold": True, "color": BLUE})],
        "Sees the throw plane (sagittal): arm swing, trunk lean, wrist speed, release speed, angle and height, "
        "the flight arc, short / long and the slide."], size=11.5, spacing=1.15)
    text(cam, xr, 4.68, 12.44 - xr, 0.8, [
        [("FRONT PHONE · behind the board · 720p, 30 fps", {"bold": True, "color": GOLD})],
        "Sees across the lane (frontal): side lean, shoulder tilt, hand across the body, left / right, "
        "hole / board / off."], size=11, spacing=1.1)
    card(cam, 0.90, 5.60, 11.54, 1.05)
    text(cam, 1.10, 5.68, 4.6, 0.9, [
        [("WHY WE SYNC ", {"bold": True, "color": RED}),
         ("Release comes from the side; left / right and the result from the front. To explain one throw both must "
          "mean the same instant: the clap and bag thuds line the soundtracks up to ±17.5 ms.", {})]],
        size=11, spacing=1.12)
    fit_picture(cam, fig("sync_timeline.png"), 5.85, 5.63, 6.45, 0.99)
    notes(cam, "EMILY (0:45). Our solution is two phones on tripods and a Mac, no markers and no sensors, and each "
               "camera has a job. The side phone sits beside the lane and sees the throw plane: arm swing, trunk lean, "
               "wrist speed, and the bag's release speed, angle and height from its arc, then how far short or long "
               "it landed and slid. The front phone sits behind the board and sees what the side can't: left and "
               "right, trunk side lean, the hand crossing the body, and whether the bag went in the hole. To explain "
               "one throw, both must describe the same instant, so we sync them by sound: the athlete claps, every bag "
               "thuds, and the app lines up the two soundtracks to plus or minus 17.5 ms. On this throw, side frame "
               "167 is front frame 85. We filmed 4 athletes, 23 takes, 92 throws. Why not alternatives: a mocap lab "
               "can't come to practice, wearables see the arm but not the bag, and a sensor in the bag isn't allowed.")

    # --- NEW: what the pose model sees, and the calculations (John)
    body = new_slide_like(prs, O[5], "PART 2 · WHAT WE MEASURE ON THE ATHLETE",
                          "What the pose model sees, and what we calculate")
    h = 3.85
    picture(body, fig("body_side.png"), 0.90, 1.85, h=h)
    picture(body, fig("body_front.png"), 0.90 + h + 0.18, 1.85, h=h)
    xe = 0.90 + h + 0.18 + h * 0.682 + 0.25
    picture(body, fig("equations.png"), xe, 1.85, w=12.44 - xe)
    text(body, 0.90, 1.85 + h + 0.06, h, 0.25, [[("SIDE · Sports2D keypoints at release", {"bold": True, "color": BLUE})]],
         size=11)
    text(body, 0.90 + h + 0.18, 1.85 + h + 0.06, h * 0.682 + 0.2, 0.25,
         [[("FRONT · same instant", {"bold": True, "color": GOLD})]], size=11)
    card(body, 0.90, 6.05, 11.54, 0.60, fill=INK, line=None)
    text(body, 1.10, 6.05, 11.2, 0.60, [[("Every number carries its noise. ", {"bold": True, "color": "C9A45C"}),
         ("Markerless joint centres are good to about 16–48 mm (Needham et al., 2021), so each metric has a noise "
          "floor, a status and a grade, and a change smaller than its noise is never coached.", {"color": "FFFFFF"})]],
         size=11.5, anchor=MSO_ANCHOR.MIDDLE, spacing=1.15)
    notes(body, "JOHN (0:50). This is what the computer actually sees. Sports2D, an open-source pose model, puts "
                "keypoints on the athlete in every frame, from both cameras, with no markers. From those 2D points we "
                "compute joint angles with the dot product: here the elbow is at 162 degrees at release, the trunk "
                "leans 24 degrees forward, and the arm is 75 degrees from vertical. The front camera at the same "
                "instant gives a 9 degree side lean and a 4 degree shoulder tilt. Points are filtered with a 6 Hz "
                "zero-phase Butterworth, the biomechanics standard, before any angle or speed, and speeds are central "
                "differences normalised by arm length so athletes compare fairly. The bag is pure physics: we fit "
                "constant velocity plus gravity to the first 0.12 seconds of flight, giving release speed and angle, "
                "and the camera scale is fixed by the board's size and by gravity on the bag's own fall. Every number "
                "carries its noise floor, because markerless joint centres are only good to a few centimetres.")

    # --- NEW: biomechanics statistics (John)
    st = new_slide_like(prs, O[7], "PART 2 · BIOMECHANICS STATISTICS", "Signal or noise? The statistics behind every cue")
    for i, (img, ratio, head, body_txt) in enumerate([
        ("stats_signal_noise.png", 1.186, "Which metrics can explain a single throw",
         "Release speed varies almost only within each athlete (ICC 0.01, spread 2.1× its noise): train it. "
         "Backswing and trunk lean are stable styles (ICC 0.90–0.96): leave them."),
        ("stats_evidence_chain.png", 1.569, "Does the body → release → outcome chain show up?",
         "Release angle → apex height is clear for all four (ρ 0.80–0.97). No release value predicts points yet "
         "at 20–28 throws each: an honest null, not a hidden effect."),
    ]):
        x = 0.90 + i * 5.89
        card(st, x, 1.85, 5.65, 4.10)
        text(st, x + 0.2, 1.97, 5.25, 0.26, head, size=14, color=INK, bold=True)
        fit_picture(st, fig(img), x + 0.15, 2.30, 5.35, 2.88)
        text(st, x + 0.2, 5.22, 5.25, 0.7, body_txt, size=11, spacing=1.15)
    card(st, 0.90, 6.05, 11.54, 0.60, fill=INK, line=None)
    text(st, 1.10, 6.05, 11.2, 0.60, [[("Evidence gate. ", {"bold": True, "color": "C9A45C"}),
         ("A body cue reaches the coach only with ≥ 5 throws per group, Cliff's |δ| above the Bonferroni chance level "
          "(never below 0.474), a difference larger than the noise floor, and a bootstrap 95% CI that excludes 0.",
          {"color": "FFFFFF"})]], size=11.5, anchor=MSO_ANCHOR.MIDDLE, spacing=1.15)
    notes(st, "JOHN (0:50). For a sport scientist the key question is: is a difference real, or noise? Left: every "
              "metric, plotted by how much it varies throw to throw compared with its measurement noise, against the "
              "ICC, the share of variation that is between athletes. Release speed is the striking one: an ICC near "
              "zero and a spread twice its noise, so every athlete wobbles in speed from throw to throw, and that is "
              "trainable. Backswing and trunk lean have ICCs of 0.9 and above: they are each athlete's style, stable, "
              "so we don't coach them away. Right: within-athlete Spearman correlations with bootstrap intervals. "
              "Physics shows up clearly: release angle predicts apex height for all four. But no release value "
              "predicts points yet with 20 to 28 throws each, and we report that honestly. That is why advice passes "
              "an evidence gate: enough throws, a large Cliff's delta after Bonferroni, bigger than noise, and a "
              "bootstrap interval that excludes zero.")

    # --- NEW: what the 92 throws showed (Eliam)
    d = new_slide_like(prs, O[13], "PART 4 · WHERE THE 92 THROWS WENT", "Same release, very different results")
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
    notes(d, "ELIAM (0:35). Here is the whole data set. Left: where every bag first touched the board. The hole "
             "shots, in blue, landed about 18 inches short and slid in, so the slide is part of a good shot. Top: "
             "18 in the hole, 38 on the board, 36 off. All four release at about 7.5 m/s, yet points per round run "
             "from 1.4 to 6.0: consistency, not power, sets the score. Bottom: for the 44 misses the app could explain "
             "above noise, the carry is the single biggest part, but the slide along and across the board adds up to "
             "31 against 39 for the flight. So practice should include board feel, not only the arm.")

    # --- NEW: conclusion + what we learned + questions (Eliam)
    c = new_slide_like(prs, O[15], "CONCLUSION AND WHAT WE LEARNED", "What we built, what we found, what we learned")
    cols = [("WE BUILT", "2 phones", "and a Mac, no sensors",
             "Body → release → landing → score, synced by sound, checked against gravity, one sentence per throw.", BLUE),
            ("WE FOUND", "13 cm", "per 0.1 m/s of release speed",
             "Speed consistency, not angle or power, drives short and long; the slide matters almost as much as the flight.",
             GOLD),
            ("WHAT COMES NEXT", "4–6 weeks", "to prove it raises PPR",
             "Alternate weeks with and without feedback, 40 throws per athlete per week, plus a blinded validation check.",
             RED)]
    for i, (lab, big, small, body_txt, col) in enumerate(cols):
        x = 0.90 + i * 3.92
        card(c, x, 1.85, 3.70, 2.30)
        text(c, x + 0.2, 1.97, 3.3, 0.24, lab, size=11, color=col, bold=True)
        text(c, x + 0.2, 2.20, 3.3, 0.55, big, size=28, color=col, bold=True, spacing=1.0)
        text(c, x + 0.2, 2.78, 3.3, 0.26, small, size=11, color=INK, italic=True)
        text(c, x + 0.2, 3.10, 3.3, 1.0, body_txt, size=11, spacing=1.15)
    lessons = [("Hardest part", "A red bag on a red board in a busy gym: one tracking error spreads into every metre."),
               ("What surprised us", "All four release at the same speed; they differ in consistency. 4K tracked worse than 1080p."),
               ("Do differently", "Contrasting bag, 120 fps side camera, regulation distance, 40+ throws, a left-hander."),
               ("Kept us up at night", "Advice from noise, and no gold standard yet. Hence the evidence gate.")]
    for i, (head, body_txt) in enumerate(lessons):
        x = 0.90 + i * 2.925
        card(c, x, 4.30, 2.765, 1.30)
        text(c, x + 0.15, 4.40, 2.47, 0.24, head, size=12, color=INK, bold=True)
        text(c, x + 0.15, 4.68, 2.47, 0.85, body_txt, size=10.5, spacing=1.1)
    card(c, 0.90, 5.75, 11.54, 0.85, fill=INK, line=None)
    text(c, 1.15, 5.75, 8.5, 0.85, "Measure the throw. Explain the miss. Coach only what the data supports.",
         size=17, color="FFFFFF", italic=True, anchor=MSO_ANCHOR.MIDDLE)
    text(c, 9.80, 5.75, 2.45, 0.85, "Questions?", size=26, color="C9A45C", bold=True, align=PP_ALIGN.RIGHT,
         anchor=MSO_ANCHOR.MIDDLE)
    notes(c, "ELIAM (0:30). To sum up: we built a two-phone, sensor-free system that links the body to the release, "
             "landing and score. We found speed consistency drives short and long, and the slide matters almost as "
             "much as the flight. Next is proving it raises scores. What we learned: the hardest part was a red bag "
             "on a red board; the surprise was that everyone throws at the same speed; we'd use a contrasting bag "
             "and a 120 fps camera; and what kept us up was giving advice from noise, which is why we built the "
             "evidence gate. Measure the throw, explain the miss, coach only what the data supports. Questions? "
             "Q&A owners: Emily (sport and coaching), John (metrics and statistics), Berk (app, tracking, sync), "
             "Eliam (results and limits).")

    # --- order: 12 main slides, then backup
    main = [(O[1], None), (O[3], "Emily Park"), (cam, "Emily Park"), (body, "John Wilson"), (O[6], "John Wilson"),
            (st, "John Wilson"), (O[9], "Berk Kasimcan"), (O[11], "Berk Kasimcan"), (O[12], "Berk Kasimcan"),
            (d, "Eliam Chang"), (O[14], "Eliam Chang"), (c, "Eliam Chang")]
    backup = [O[2], O[4], O[5], O[7], O[8], O[10], O[13], O[15], O[16]]
    for i, (s, _) in enumerate(main + [(b, None) for b in backup]):
        move_slide(prs, s, i)
    for i, (s, who) in enumerate(main, start=1):
        if who:
            set_footer(s, who, f"{i} / {len(main)}")
    for s in backup:
        for sh in s.shapes:
            if sh.has_text_frame and re.search(r"· \d+ / 16$", sh.text_frame.text):
                set_text(sh, re.sub(r"\d+ / 16$", "backup", sh.text_frame.text))
        lab = s.shapes[0]
        if lab.has_text_frame and lab.text_frame.text.isupper() and not lab.text_frame.text.startswith("BACKUP"):
            set_text(lab, "BACKUP · " + re.sub(r"^PART \d · ", "", lab.text_frame.text))
    prs.save(a.dst)
    print("saved", a.dst, len(prs.slides), "slides,", len(main), "main")


if __name__ == "__main__":
    main()
