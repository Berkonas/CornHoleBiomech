"""Figures for the class presentation, drawn only from existing engine outputs.

Reads the athlete library (dashboards, per-throw outcome.json / two_view.json,
and one throw's replay, keypoints and results). Runs no video analysis.

    .venv/bin/python scripts/presentation_figures.py [--library PATH] [--out docs/presentation/figures]

The camera and body figures read single frames from the stored clips with OpenCV (in the
engine's .venv); nothing is re-analysed. The deck's numbers are the committed 92-throw library:
while the working copy is being re-analysed, export it first and pass it as --library, e.g.
    git archive HEAD -- "data/libraries/Cornhole Biomechanics Lab Data/dashboards" \
        ':(glob)data/libraries/Cornhole Biomechanics Lab Data/Athletes/*/analyses/*/outcome.json' \
        ':(glob)data/libraries/Cornhole Biomechanics Lab Data/Athletes/*/analyses/*/two_view.json' | tar -x -C /tmp/lib
"""

from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import os

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LIBRARY = os.path.join(ROOT, "data", "libraries", "Cornhole Biomechanics Lab Data")

# Deck palette (matches the slides)
INK, MUTED, RULE, CARD, BG = "#1C1A17", "#57514A", "#E3DCCF", "#FFFEFB", "#FAF8F3"
BLUE, GOLD, RED, SAND = "#2F5D8A", "#8A6A2B", "#A8432A", "#E8D9B5"
OUTCOME = {3: ("Hole", BLUE), 1: ("Board", "#C9A45C"), 0: ("Off", RED)}

# Demo throw: Player 1, Take 6, Throw 1
DEMO_ATHLETE = "Player-1-93B49584"
DEMO_TRIAL = "FAA512D6-A411-433B-B93A-CDC7C39FF5C4"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 13,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "savefig.dpi": 220,
    "mathtext.fontset": "stix",
})


def load(path):
    with open(path) as f:
        return json.load(f)


def athlete_name(folder):
    return " ".join(os.path.basename(folder).split("-")[:2])


def collect_throws(library):
    rows = []
    for d in sorted(glob.glob(os.path.join(library, "Athletes", "*", "analyses", "Throw-*"))):
        athlete = athlete_name(d.split(os.sep + "analyses")[0])
        outcome = load(os.path.join(d, "outcome.json")) if os.path.exists(os.path.join(d, "outcome.json")) else {}
        tv_path = os.path.join(d, "two_view.json")
        att = (load(tv_path).get("attribution") or {}) if os.path.exists(tv_path) else {}
        named = []
        for axis in ("depth", "lateral"):
            block = att.get(axis) or {}
            for comp in block.get("components", []):
                if comp.get("named"):
                    named.append((axis, comp["key"]))
        fc = outcome.get("first_contact_point") or {}
        rows.append({
            "athlete": athlete,
            "score": outcome.get("score_category"),
            "source": outcome.get("source"),
            "fc": (fc.get("x_inches"), fc.get("y_inches")) if fc.get("x_inches") is not None else None,
            "named": named,
        })
    return rows


def save(fig, out, name):
    path = os.path.join(out, name)
    fig.savefig(path, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    print("wrote", os.path.relpath(path, ROOT))


# ---------------------------------------------------------------- outcomes
def fig_outcomes(library, out):
    dashes = [load(f) for f in glob.glob(os.path.join(library, "dashboards", "*.json"))]
    dashes.sort(key=lambda d: d["athlete"], reverse=True)
    fig, ax = plt.subplots(figsize=(5.4, 2.8), facecolor=CARD)
    ax.set_facecolor(CARD)
    for i, d in enumerate(dashes):
        c = d["performance"]["counts"]
        n = sum(c.values())
        left = 0
        for key, score in (("hole", 3), ("board", 1), ("miss", 0)):
            label, color = OUTCOME[score]
            v = c.get(key, 0)
            if v:
                ax.barh(i, v / n * 100, left=left, color=color, height=0.62, edgecolor=CARD, linewidth=1.5)
                if v / n > 0.08:
                    ax.text(left + v / n * 50, i, str(v), ha="center", va="center",
                            color="white" if score != 1 else INK, fontsize=15, fontweight="bold")
                left += v / n * 100
        ppr = d["performance"]["sports"]["ppr"]
        ax.text(103, i, f"PPR {ppr:.1f}", va="center", ha="left", color=INK, fontsize=15)
    ax.set_yticks(range(len(dashes)), [f"{d['athlete']}  ({d['throws']})" for d in dashes])
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 50, 100], ["0%", "50%", "100%"])
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0, labelsize=15, labelcolor=INK)
    handles = [plt.Rectangle((0, 0), 1, 1, color=OUTCOME[s][1]) for s in (3, 1, 0)]
    ax.legend(handles, ["Hole (3)", "Board (1)", "Off (0)"], ncol=3, frameon=False,
              loc="lower center", bbox_to_anchor=(0.5, 1.0), fontsize=15)
    save(fig, out, "outcomes_by_athlete.png")


# ---------------------------------------------------------------- landing map
def fig_landing(rows, out):
    fig, ax = plt.subplots(figsize=(3.6, 6.0), facecolor=CARD)
    ax.set_facecolor(CARD)
    ax.add_patch(Rectangle((0, 0), 24, 48, facecolor=SAND, edgecolor=GOLD, linewidth=1.6, zorder=0))
    ax.add_patch(Circle((12, 39), 3, facecolor=INK, edgecolor=GOLD, linewidth=1.2, zorder=1))
    for score in (1, 0, 3):
        pts = [r["fc"] for r in rows if r["fc"] and r["score"] == score]
        if pts:
            xs, ys = zip(*pts)
            ax.scatter(xs, ys, s=60, color=OUTCOME[score][1], edgecolor="white", linewidth=0.7,
                       zorder=3, label=f"{OUTCOME[score][0]} ({len(pts)})")
    ax.set_xlim(-14, 38)
    ax.set_ylim(-14, 56)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(12, -4, "front of board", ha="center", va="top", color=MUTED, fontsize=15)
    ax.annotate("", xy=(-9, 30), xytext=(-9, 6), arrowprops=dict(arrowstyle="->", color=MUTED))
    ax.text(-11, 18, "throw", rotation=90, ha="center", va="center", color=MUTED, fontsize=15)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.04), ncol=3, fontsize=12,
              handletextpad=0.2, columnspacing=0.8)
    save(fig, out, "landing_map.png")


# ---------------------------------------------------------------- miss causes
def fig_miss_causes(rows, out):
    count = collections.Counter(k for r in rows for k in r["named"])
    bars = [
        ("Carry (flight length)", count[("depth", "carry")], BLUE),
        ("Aim (sideways launch)", count[("lateral", "aim")], BLUE),
        ("Release position", count[("lateral", "release_position")], BLUE),
        ("Slide along the board", count[("depth", "slide")], GOLD),
        ("Slide sideways", count[("lateral", "slide_drift")], GOLD),
    ]
    fig, ax = plt.subplots(figsize=(5.4, 2.8), facecolor=CARD)
    ax.set_facecolor(CARD)
    ys = list(range(len(bars)))[::-1]
    for y, (label, v, color) in zip(ys, bars):
        ax.barh(y, v, color=color, height=0.6)
        ax.text(v + 0.5, y, str(v), va="center", color=INK, fontsize=15)
    ax.set_yticks(ys, [b[0] for b in bars])
    ax.tick_params(axis="y", length=0, labelsize=15, labelcolor=INK)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("times named (one miss can name two parts)", color=MUTED, fontsize=15)
    air = sum(b[1] for b in bars if b[2] == BLUE)
    board = sum(b[1] for b in bars if b[2] == GOLD)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (BLUE, GOLD)]
    ax.legend(handles, [f"In the air ({air})", f"On the board ({board})"], frameon=False,
              ncol=2, loc="lower center", bbox_to_anchor=(0.4, 1.0), fontsize=15)
    save(fig, out, "miss_causes.png")
    return count


# ---------------------------------------------------------------- pipeline storyboard
SKELETON = [("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"), ("left_shoulder", "left_elbow"),
            ("left_elbow", "left_wrist"), ("right_shoulder", "left_shoulder"), ("right_hip", "left_hip"),
            ("right_shoulder", "right_hip"), ("left_shoulder", "left_hip"), ("right_hip", "right_knee"),
            ("right_knee", "right_ankle"), ("left_hip", "left_knee"), ("left_knee", "left_ankle"), ("Neck", "Head")]


def keypoints_at(path, frames):
    pts = {f: {} for f in frames}
    with open(path) as fh:
        for row in csv.DictReader(fh):
            f = int(row["frame"])
            if f in pts and row["filtered_x_px"]:
                pts[f][row["landmark"]] = (float(row["filtered_x_px"]), float(row["filtered_y_px"]))
    return pts


def card(ax, title, step, built):
    ax.set_facecolor(CARD)
    for s in ax.spines.values():
        s.set_visible(True)
        s.set_color(RULE)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"{step}  {title}", loc="left", fontsize=13, color=INK, fontweight="bold", pad=6)
    ax.text(0.0, -0.06, built, transform=ax.transAxes, ha="left", va="top", fontsize=10.5,
            color=MUTED, style="italic", wrap=True)


def fig_pipeline(library, out):
    adir = os.path.join(library, "Athletes", DEMO_ATHLETE)
    tdir = os.path.join(adir, "analyses", "Throw-" + DEMO_TRIAL.split("-")[0])
    take = load(glob.glob(os.path.join(adir, "takes", "Take-06-*", "take.json"))[0])
    res = load(os.path.join(tdir, "results.json"))
    replay = load(os.path.join(tdir, "replay.json"))
    outcome = load(os.path.join(tdir, "outcome.json"))
    att = load(os.path.join(tdir, "two_view.json"))["attribution"]
    ev = res["event_frames"]
    cm = res["coach_metrics"]
    g = res["flight"]["gravity_scale"]

    fig, axes = plt.subplots(1, 6, figsize=(16, 3.3), facecolor=BG,
                             gridspec_kw={"width_ratios": [1, 1, 1.25, 1, 1, 1.15], "wspace": 0.16})

    # 1 import and sync: two sound tracks drawn from the take's measured offset
    ax = axes[0]
    card(ax, "Sync", "1", "Audio cross-correlation\nof clap + bag impacts")
    off = take["sync"]["offset_s"]
    t = np.linspace(-0.3, 1.6, 600)
    events = [0.0, 0.35, 0.7, 1.05, 1.4]
    def track(shift):
        return sum(np.exp(-((t - e - shift) / 0.018) ** 2) for e in events)
    ax.plot(t, track(0) + 1.3, color=BLUE, lw=1.4)
    ax.plot(t, track(abs(off)), color=GOLD, lw=1.4)
    ax.text(-0.28, 2.45, "side", color=BLUE, fontsize=10.5)
    ax.text(-0.28, 1.12, "front", color=GOLD, fontsize=10.5)
    ax.set_ylim(-0.7, 2.8)
    ax.text(0.5, 0.04, f"shift {abs(off) * 1000:.0f} ms, ±{take['sync']['uncertainty_s'] * 1000:.1f} ms",
            transform=ax.transAxes, ha="center", fontsize=11, color=INK)

    # 2 body tracking: skeleton at backswing, release, follow-through
    ax = axes[1]
    card(ax, "Body", "2", "Sports2D / RTMPose pose,\n6 Hz Butterworth filter")
    frames = [ev["peak_backswing"], ev["release"], ev["peak_follow_through"]]
    kp = keypoints_at(os.path.join(tdir, "keypoints.csv"), frames)
    shades = [RULE, INK, "#B8AE9C"]
    for f, col, lw in zip(frames, shades, (1.6, 2.4, 1.6)):
        p = kp[f]
        for a, b in SKELETON:
            if a in p and b in p:
                ax.plot([p[a][0], p[b][0]], [p[a][1], p[b][1]], color=col, lw=lw, solid_capstyle="round")
    rw = kp[ev["release"]].get("right_wrist")
    if rw:
        ax.scatter(*rw, s=40, color=RED, zorder=5)
    ax.invert_yaxis()
    ax.set_aspect("equal", adjustable="datalim")
    ax.margins(0.12)
    ax.text(0.5, 0.04, "backswing · release · follow-through", transform=ax.transAxes,
            ha="center", fontsize=10, color=MUTED)

    # 3 bag tracking on the empty-scene plate
    ax = axes[2]
    card(ax, "Bag", "3", "Motion + gravity check,\nKalman / RTS smoother")
    img = plt.imread(os.path.join(tdir, "plate.jpg"))
    ax.imshow(img, alpha=0.55)
    mx = [p["x"] for p in replay["measured"]]
    my = [p["y"] for p in replay["measured"]]
    ax.plot([p["x"] for p in replay["model"]], [p["y"] for p in replay["model"]], "--", color=INK, lw=1.2)
    ax.scatter(mx, my, s=7, color=RED, zorder=4)
    ax.set_xlim(150, 1900)
    ax.set_ylim(720, 120)
    ax.set_aspect("auto")
    ax.text(0.03, 0.05, f"{len(mx)} measured points (red)\ndashed = drag-free fit", transform=ax.transAxes,
            fontsize=10, color=INK, backgroundcolor=CARD)

    # 4 scale: pixels to metres, checked against gravity
    ax = axes[3]
    card(ax, "Scale", "4", "Board geometry (PnP)\n+ gravity calibration")
    ax.text(0.5, 0.70, f"{g['pixels_per_meter']:.0f} px/m", ha="center", fontsize=24, color=BLUE,
            transform=ax.transAxes)
    ax.text(0.5, 0.52, "from the bag's own fall", ha="center", fontsize=11, color=MUTED, transform=ax.transAxes)
    ax.text(0.5, 0.30, f"g = {g['apparent_gravity_m_s2']:.2f} m/s²", ha="center", fontsize=17, color=INK,
            transform=ax.transAxes)
    ax.text(0.5, 0.10, "near 9.81, or the\nflight is rejected", ha="center", fontsize=10,
            color=MUTED, transform=ax.transAxes)

    # 5 release and landing
    ax = axes[4]
    card(ax, "Release + land", "5", "Physics fit of first 0.12 s;\nfront camera for the board")
    sp, an, h = (cm["bag_release_speed_m_s"]["value"], cm["bag_release_angle_deg"]["value"],
                 cm["bag_release_height_m"]["value"])
    ax.text(0.06, 0.80, f"{sp:.1f} m/s", fontsize=20, color=BLUE, transform=ax.transAxes)
    ax.text(0.06, 0.64, f"{an:.0f}° · {h:.2f} m high", fontsize=13, color=INK, transform=ax.transAxes)
    inset = ax.inset_axes([0.58, 0.05, 0.36, 0.55])
    inset.add_patch(Rectangle((0, 0), 24, 48, facecolor=SAND, edgecolor=GOLD))
    inset.add_patch(Circle((12, 39), 3, color=INK))
    fc = outcome["first_contact_point"]
    inset.scatter([fc["x_inches"]], [fc["y_inches"]], s=30, color=RED, zorder=3)
    inset.annotate("", xy=(12, 39), xytext=(fc["x_inches"], fc["y_inches"]),
                   arrowprops=dict(arrowstyle="->", color=RED, lw=1))
    inset.set_xlim(-2, 26)
    inset.set_ylim(-2, 50)
    inset.set_aspect("equal")
    inset.axis("off")
    ax.text(0.06, 0.40, "landed, slid", fontsize=11, color=MUTED, transform=ax.transAxes)
    ax.text(0.06, 0.28, "into the hole", fontsize=11, color=MUTED, transform=ax.transAxes)

    # 6 feedback
    ax = axes[5]
    card(ax, "Advice", "6", "Miss split into parts;\nevidence gate on every claim")
    ax.add_patch(FancyBboxPatch((0.06, 0.40), 0.88, 0.42, boxstyle="round,pad=0.02",
                                transform=ax.transAxes, facecolor=INK, edgecolor="none"))
    ax.text(0.5, 0.61, "“" + att['sentence'].replace('. ', '.\n') + "”", ha="center", va="center", fontsize=13, color="white",
            style="italic", transform=ax.transAxes, wrap=True)
    ax.text(0.5, 0.22, "a made throw gets\nno corrections", ha="center", va="center", fontsize=11,
            color=MUTED, transform=ax.transAxes)

    for i in range(5):
        a, b = axes[i].get_position(), axes[i + 1].get_position()
        fig.patches.append(matplotlib.patches.FancyArrowPatch(
            (a.x1 + 0.002, a.y0 + a.height / 2), (b.x0 - 0.002, b.y0 + b.height / 2),
            transform=fig.transFigure, arrowstyle="-|>", mutation_scale=14, color=GOLD))
    save(fig, out, "pipeline_storyboard.png")


# ---------------------------------------------------------------- video frames (needs OpenCV: run with .venv python)
def video_frame(path, frame):
    import cv2
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
    ok, img = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"could not read frame {frame} of {path}")
    return img[:, :, ::-1]


def read_trc(path, frame):
    """Sports2D .trc (pixels): {marker: (x, y)} for one frame."""
    with open(path) as fh:
        lines = fh.read().splitlines()
    names = [n for n in lines[3].split("\t")[2:] if n]
    for line in lines[5:]:
        cells = line.split("\t")
        if cells and cells[0].strip() == str(frame):
            vals = [float(v) for v in cells[2:] if v.strip()]
            return {n: (vals[3 * i], vals[3 * i + 1]) for i, n in enumerate(names)}
    raise KeyError(frame)


TRC_BONES = [("RShoulder", "RElbow"), ("RElbow", "RWrist"), ("LShoulder", "LElbow"), ("LElbow", "LWrist"),
             ("RShoulder", "LShoulder"), ("RHip", "LHip"), ("Neck", "Hip"), ("RHip", "RKnee"),
             ("RKnee", "RAnkle"), ("LHip", "LKnee"), ("LKnee", "LAnkle"), ("Neck", "Head")]


def demo_paths(library):
    adir = os.path.join(library, "Athletes", DEMO_ATHLETE)
    tdir = os.path.join(adir, "analyses", "Throw-" + DEMO_TRIAL.split("-")[0])
    kdir = glob.glob(os.path.join(adir, "takes", "Take-06-*"))[0]
    return adir, tdir, kdir


def label(ax, xy, text_xy, text, color=INK, size=12, ha="left"):
    ax.annotate(text, xy=xy, xytext=text_xy, fontsize=size, color=color, ha=ha, va="center",
                arrowprops=dict(arrowstyle="-", color=color, lw=1.1, shrinkA=2, shrinkB=2),
                bbox=dict(boxstyle="round,pad=0.25", fc=CARD, ec=color, lw=0.8, alpha=0.95))


# ---------------------------------------------------------------- two cameras, two jobs
def fig_cameras(library, out):
    _, tdir, kdir = demo_paths(library)
    res = load(os.path.join(tdir, "results.json"))
    tv = load(os.path.join(tdir, "two_view.json"))
    replay = load(os.path.join(tdir, "replay.json"))
    rel_s, rel_f = tv["frames"]["release_side"], tv["frames"]["release_front"]

    # side camera, release frame: skeleton + measured bag path
    img = video_frame(os.path.join(kdir, "throw_01_side.mp4"), rel_s)
    kp = keypoints_at(os.path.join(tdir, "keypoints.csv"), [rel_s])[rel_s]
    fig, ax = plt.subplots(figsize=(7.2, 2.6), facecolor=CARD)
    ax.imshow(img)
    for a, b in SKELETON:
        if a in kp and b in kp:
            ax.plot([kp[a][0], kp[b][0]], [kp[a][1], kp[b][1]], color="#38D27A", lw=1.6)
    pts = replay["measured"]
    ax.plot([p["x"] for p in pts], [p["y"] for p in pts], ".", color=RED, ms=3.5)
    ax.set_xlim(0, 1920)
    ax.set_ylim(760, 120)
    ax.axis("off")
    label(ax, kp["right_wrist"], (430, 560), "arm swing, trunk lean,\nrelease point", BLUE, 11)
    apex = replay["events"]["apex"]["position"]
    label(ax, (apex["x"], apex["y"]), (1200, 200), "release speed, angle, height\nfrom the flight arc", RED, 11)
    fcp = replay["events"]["first_contact"]["position"]
    label(ax, (fcp["x"], fcp["y"]), (1350, 560), "short / long + slide", GOLD, 11, ha="right")
    save(fig, out, "camera_side.png")

    # front camera, same instant (synced): skeleton + bag path + board
    img = video_frame(os.path.join(kdir, "throw_01_front.mp4"), rel_f)
    kp = read_trc(glob.glob(os.path.join(tdir, "front_sports2d", "*", "*_px_person00.trc"))[0], rel_f)
    fig, ax = plt.subplots(figsize=(4.7, 2.6), facecolor=CARD)
    ax.imshow(img)
    for a, b in TRC_BONES:
        if a in kp and b in kp:
            ax.plot([kp[a][0], kp[b][0]], [kp[a][1], kp[b][1]], color="#38D27A", lw=1.3)
    fp = tv["front_path"]
    ax.plot([p["px"][0] for p in fp], [p["px"][1] for p in fp], ".", color=RED, ms=3)
    corners = tv["deck_corners_px"] + [tv["deck_corners_px"][0]]
    ax.plot([c[0] for c in corners], [c[1] for c in corners], color=GOLD, lw=1.4)
    ax.set_xlim(250, 1030)
    ax.set_ylim(700, 60)
    ax.axis("off")
    label(ax, kp["Neck"], (300, 150), "trunk side lean,\nhand across body", BLUE, 11)
    label(ax, fp[-1]["px"], (980, 330), "left / right", RED, 11, ha="right")
    label(ax, (568, 490), (330, 620), "hole / board / off", GOLD, 11)
    save(fig, out, "camera_front.png")

    # the shared timeline: frames of both phones on one clock
    side_fps, front_fps = tv["frames"]["side_fps"], tv["frames"]["front_fps"]
    c_s, c_f = tv["frames"]["contact_side"], tv["frames"]["contact_front"]
    t_rel, t_con = rel_s / side_fps, c_s / side_fps
    fig, ax = plt.subplots(figsize=(8.4, 1.55), facecolor=CARD)
    ax.set_facecolor(CARD)
    t0, t1 = t_rel - 0.25, t_con + 0.15
    for y, fps, col, name in ((1.0, side_fps, BLUE, f"side · {side_fps:.0f} fps"),
                              (0.0, front_fps, GOLD, f"front · {front_fps:.0f} fps")):
        ticks = np.arange(np.ceil(t0 * fps), t1 * fps) / fps
        ax.vlines(ticks, y - 0.18, y + 0.18, color=col, lw=0.9)
        ax.text(t0 - 0.02, y, name, ha="right", va="center", color=col, fontsize=11)
    for t, txt, sf, ff in ((t_rel, "release", rel_s, rel_f), (t_con, "first contact", c_s, c_f)):
        ax.plot([t, t], [-0.35, 1.35], color=RED, lw=1.6)
        ax.text(t, 1.55, txt, ha="center", color=RED, fontsize=11, fontweight="bold")
        ax.text(t + 0.012, 0.5, f"side {sf} ↔ front {ff}", ha="left", va="center", color=INK, fontsize=10)
    ax.set_xlim(t0 - 0.30, t1)
    ax.set_ylim(-0.5, 1.85)
    ax.axis("off")
    save(fig, out, "sync_timeline.png")


# ---------------------------------------------------------------- what the pose model sees, and the angles
def angle_arc(ax, centre, p_a, p_b, r, color, text, text_off):
    a1 = np.degrees(np.arctan2(-(p_a[1] - centre[1]), p_a[0] - centre[0]))
    a2 = np.degrees(np.arctan2(-(p_b[1] - centre[1]), p_b[0] - centre[0]))
    lo, hi = sorted((a1, a2))
    if hi - lo > 180:
        lo, hi = hi, lo + 360
    th = np.radians(np.linspace(lo, hi, 40))
    ax.plot(centre[0] + r * np.cos(th), centre[1] - r * np.sin(th), color=color, lw=2)
    ax.text(centre[0] + text_off[0], centre[1] + text_off[1], text, color=color, fontsize=12,
            fontweight="bold", ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.15", fc=CARD, ec="none", alpha=0.9))


def fig_body(library, out):
    _, tdir, kdir = demo_paths(library)
    res = load(os.path.join(tdir, "results.json"))
    tv = load(os.path.join(tdir, "two_view.json"))
    cm = res["coach_metrics"]
    rel_s, rel_f = tv["frames"]["release_side"], tv["frames"]["release_front"]

    # side: Sports2D's own overlay at release, zoomed on the athlete, plus our angle definitions
    img = video_frame(os.path.join(kdir, "throw_01_side.mp4"), rel_s)
    kp = keypoints_at(os.path.join(tdir, "keypoints.csv"), [rel_s])[rel_s]
    fig, ax = plt.subplots(figsize=(4.4, 4.4), facecolor=CARD)
    ax.imshow(img)
    for a, b in SKELETON:
        if a in kp and b in kp:
            ax.plot([kp[a][0], kp[b][0]], [kp[a][1], kp[b][1]], color="#38D27A", lw=1.8, alpha=0.9)
    for xy in kp.values():
        ax.scatter(*xy, s=10, color="#38D27A", zorder=4)
    sh, el, wr = kp["right_shoulder"], kp["right_elbow"], kp["right_wrist"]
    hip, neck = kp["Hip"], kp["Neck"]
    angle_arc(ax, el, sh, wr, 22, BLUE, f"elbow {cm['elbow_angle_deg_at_release']['value']:.0f}°", (10, -45))
    ax.plot([hip[0], hip[0]], [hip[1], hip[1] - 95], ls="--", color=GOLD, lw=1.4)
    ax.plot([hip[0], neck[0]], [hip[1], neck[1]], color=GOLD, lw=2.4)
    angle_arc(ax, hip, (hip[0], hip[1] - 60), neck, 40, GOLD,
              f"trunk lean {cm['trunk_inclination_deg_at_release']['value']:.0f}°", (-95, -40))
    ax.plot([sh[0], sh[0]], [sh[1], sh[1] + 80], ls="--", color=RED, lw=1.2)
    angle_arc(ax, sh, (sh[0], sh[1] + 60), wr, 55, RED,
              f"arm {cm['swing_release_arm_angle_deg']['value']:.0f}°", (60, 95))
    ax.scatter(*wr, s=50, color=RED, zorder=5)
    cx, cy = (sh[0] + hip[0]) / 2, (sh[1] + hip[1]) / 2
    ax.set_xlim(cx - 190, cx + 210)
    ax.set_ylim(cy + 210, cy - 190)
    ax.axis("off")
    save(fig, out, "body_side.png")

    # front: Sports2D overlay at the synced release frame, frontal-plane measures
    img = video_frame(os.path.join(kdir, "throw_01_front.mp4"), rel_f)
    kp = read_trc(glob.glob(os.path.join(tdir, "front_sports2d", "*", "*_px_person00.trc"))[0], rel_f)
    fr = tv["frontal"]
    fig, ax = plt.subplots(figsize=(2.9, 4.4), facecolor=CARD)
    ax.imshow(img)
    for a, b in TRC_BONES:
        if a in kp and b in kp:
            ax.plot([kp[a][0], kp[b][0]], [kp[a][1], kp[b][1]], color="#38D27A", lw=1.6, alpha=0.9)
    ls, rs, hip, neck = kp["LShoulder"], kp["RShoulder"], kp["Hip"], kp["Neck"]
    ax.plot([ls[0], rs[0]], [ls[1], rs[1]], color=RED, lw=2.4)
    ax.plot([hip[0], neck[0]], [hip[1], neck[1]], color=GOLD, lw=2.4)
    ax.plot([hip[0], hip[0]], [hip[1], hip[1] - 45], ls="--", color=GOLD, lw=1.2)
    ax.text(hip[0] + 62, hip[1] - 30, f"side lean\n{fr['trunk_side_lean_deg']['value']:.0f}°", color=GOLD,
            fontsize=12, fontweight="bold", ha="center",
            bbox=dict(boxstyle="round,pad=0.15", fc=CARD, ec="none", alpha=0.9))
    ax.text(hip[0] - 62, rs[1] - 30, f"shoulder\ntilt {fr['shoulder_tilt_deg']['value']:.0f}°", color=RED,
            fontsize=12, fontweight="bold", ha="center",
            bbox=dict(boxstyle="round,pad=0.15", fc=CARD, ec="none", alpha=0.9))
    ax.text(hip[0], hip[1] + 120, f"hand across body\n{fr['arm_across_body_sw']['value']:.2f} shoulder widths",
            color=BLUE, fontsize=11, ha="center",
            bbox=dict(boxstyle="round,pad=0.2", fc=CARD, ec="none", alpha=0.9))
    cx, cy = hip
    ax.set_xlim(cx - 100, cx + 100)
    ax.set_ylim(cy + 160, cy - 140)
    ax.axis("off")
    save(fig, out, "body_front.png")


def fig_equations(out):
    rows = [
        ("Joint angle", r"$\theta=\arccos\,(\mathbf{u}\cdot\mathbf{v}\;/\;|\mathbf{u}|\,|\mathbf{v}|)$",
         "u, v = limb vectors from 2D keypoints"),
        ("Smoothing", r"4th-order zero-phase Butterworth, $f_c=6$ Hz",
         "landmarks with confidence < 0.35 dropped; gaps ≤ 3 frames filled"),
        ("Speed", r"$v_i=|\mathbf{p}_{i+1}-\mathbf{p}_{i-1}|\;/\;2\Delta t$",
         "÷ arm length, so athletes compare fairly"),
        ("Release", r"$x=x_0+v_xt,\;\; y=y_0+v_yt-\frac{1}{2}gt^2$",
         r"first 0.12 s of flight;  $v=\sqrt{v_x^2+v_y^2},\;\theta=\mathrm{atan2}(v_y,v_x)$"),
        ("Scale", r"pixels per metre from the bag's fall: $a_{y,\mathrm{px}}=g\,q$",
         "board size + gravity (9.81 m/s²) fix the camera's field of view"),
        ("Landing", "drag-free flight to the board, then 4-corner homography",
         "board inches: short/long (side), left/right (front)"),
    ]
    fig, ax = plt.subplots(figsize=(5.2, 4.6), facecolor=CARD)
    ax.axis("off")
    for i, (name, eq, note) in enumerate(rows):
        y = 1 - i / len(rows) - 0.04
        ax.text(0.0, y, name, fontsize=12.5, fontweight="bold", color=GOLD, va="top", transform=ax.transAxes)
        ax.text(0.26, y + 0.005, eq, fontsize=13, color=INK, va="top", transform=ax.transAxes)
        ax.text(0.26, y - 0.085, note, fontsize=10.5, color=MUTED, va="top", style="italic", transform=ax.transAxes)
    save(fig, out, "equations.png")


# ---------------------------------------------------------------- biomechanics statistics
# Metric review of the 92-throw library, docs/METRICS.md ("Metric review (2026-10-12)"):
# (label, within-athlete SD / noise floor, ICC, tier)
METRIC_REVIEW = [
    ("Release speed", 2.1, 0.01, "per throw"), ("Release angle", 1.4, 0.38, "per throw"),
    ("Release height", 2.9, 0.31, "per throw"), ("Release point", 2.1, 0.59, "per throw"),
    ("Forward swing time", 1.4, 0.62, "per throw"), ("Tempo", 2.1, 0.42, "per throw"),
    ("Peak wrist speed", 1.4, 0.75, "profile"), ("Peak wrist timing", 0.6, 0.59, "profile"),
    ("Backswing", 0.9, 0.96, "profile"), ("Trunk lean", 0.5, 0.90, "profile"),
    ("Elbow angle", 0.2, 0.77, "advanced"), ("Arm angle", 1.3, 0.50, "advanced"),
]


def fig_stats(library, out):
    fig, ax = plt.subplots(figsize=(6.6, 3.6), facecolor=CARD)
    ax.set_facecolor(CARD)
    ax.axvspan(0, 1, color=SAND, alpha=0.55, lw=0)
    ax.text(0.5, 1.02, "inside the noise", ha="center", fontsize=10.5, color=GOLD)
    colors = {"per throw": BLUE, "profile": RED, "advanced": "#9A9286"}
    offsets = {"Release speed": (8, 4), "Release height": (-8, 10), "Tempo": (8, 0), "Release point": (8, 0),
               "Release angle": (6, -12), "Forward swing time": (6, 9), "Peak wrist speed": (8, 0),
               "Backswing": (8, 0), "Trunk lean": (-8, 0), "Elbow angle": (8, 0), "Arm angle": (8, -2),
               "Peak wrist timing": (6, -12)}
    for name, ratio, icc, tier in METRIC_REVIEW:
        ax.scatter(ratio, icc, s=70, color=colors[tier], edgecolor="white", zorder=3)
        dx, dy = offsets.get(name, (6, 4))
        ax.annotate(name, (ratio, icc), xytext=(dx, dy), textcoords="offset points", fontsize=10.5,
                    color=INK, ha="right" if dx < 0 else "left")
    ax.set_xlim(0, 3.3)
    ax.set_ylim(-0.05, 1.08)
    ax.set_xlabel("throw-to-throw SD ÷ measurement noise", fontsize=12)
    ax.set_ylabel("ICC (share that is athlete-to-athlete)", fontsize=12)
    handles = [plt.Line2D([], [], marker="o", ls="", color=colors[t], ms=8) for t in colors]
    ax.legend(handles, ["explains a single throw", "athlete's style (stable)", "too noisy to coach"],
              frameon=False, fontsize=10.5, loc="upper center", bbox_to_anchor=(0.45, -0.16), ncol=3,
              handletextpad=0.2, columnspacing=0.8)
    save(fig, out, "stats_signal_noise.png")

    # evidence chain: within-athlete Spearman rho with bootstrap 95% CI
    links = [("wrist_speed_at_release_arm_lengths_s", "bag_release_speed_m_s", "Wrist speed → release speed"),
             ("bag_release_angle_deg", "bag_trajectory_apex_height_m", "Release angle → apex height"),
             ("bag_release_speed_m_s", "score", "Release speed → points"),
             ("bag_release_angle_deg", "score", "Release angle → points")]
    dashes = sorted((load(f) for f in glob.glob(os.path.join(library, "dashboards", "*.json"))),
                    key=lambda d: d["athlete"])
    fig, ax = plt.subplots(figsize=(6.6, 3.6), facecolor=CARD)
    ax.set_facecolor(CARD)
    ax.axvline(0, color=MUTED, lw=1)
    y = 0
    yt, yl = [], []
    shades = [BLUE, GOLD, RED, "#6E665C"]
    for frm, to, name in links:
        for k, d in enumerate(dashes):
            e = next((e for e in d["evidence_chain"] if e["from"] == frm and (e["to"] == to or
                      (to == "score" and e["to_label"] == "Points") or
                      (to.startswith("bag_trajectory") and e["to_label"] == "Apex height"))), None)
            if e is None or e.get("rho") is None:
                continue
            yy = y - k * 0.18
            lo, hi = e["ci"]
            ax.plot([lo, hi], [yy, yy], color=shades[k], lw=2)
            ax.scatter(e["rho"], yy, s=40 if e["supported"] else 26, color=shades[k] if e["supported"] else CARD,
                       edgecolor=shades[k], zorder=3, linewidth=1.5)
        yt.append(y - 0.27)
        yl.append(name)
        y -= 1
    ax.set_yticks(yt, yl, fontsize=12)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlim(-1, 1)
    ax.set_xlabel("Spearman ρ within athlete (bar = bootstrap 95% CI; filled = CI excludes 0)", fontsize=11)
    handles = [plt.Line2D([], [], color=shades[k], lw=2) for k in range(len(dashes))]
    ax.legend(handles, [d["athlete"] for d in dashes], frameon=False, fontsize=10, ncol=4,
              loc="lower center", bbox_to_anchor=(0.4, 1.0), handlelength=1.2, columnspacing=0.8)
    save(fig, out, "stats_evidence_chain.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library", default=DEFAULT_LIBRARY, help="library for the 92-throw summaries")
    ap.add_argument("--demo-library", default=DEFAULT_LIBRARY, help="library holding the demo throw and its clips")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "presentation", "figures"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rows = collect_throws(args.library)
    scores = collections.Counter(r["score"] for r in rows)
    sources = collections.Counter(r["source"] for r in rows)
    print(f"{len(rows)} throws; outcomes {dict(scores)}; sources {dict(sources)}; "
          f"located first contact {sum(1 for r in rows if r['fc'])}")
    fig_outcomes(args.library, args.out)
    fig_landing(rows, args.out)
    counts = fig_miss_causes(rows, args.out)
    print("named parts", dict(counts), "misses with a named part", sum(1 for r in rows if r["named"]))
    fig_pipeline(args.demo_library, args.out)
    fig_cameras(args.demo_library, args.out)
    fig_body(args.demo_library, args.out)
    fig_equations(args.out)
    fig_stats(args.library, args.out)


if __name__ == "__main__":
    main()
