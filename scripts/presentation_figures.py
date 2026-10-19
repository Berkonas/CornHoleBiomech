"""Figures for the class presentation, drawn only from existing engine outputs.

Reads the athlete library (dashboards, per-throw outcome.json / two_view.json,
and one throw's replay, keypoints and results). Runs no video analysis.

    python3 scripts/presentation_figures.py [--library PATH] [--out docs/presentation/figures]
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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library", default=DEFAULT_LIBRARY)
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
    fig_pipeline(args.library, args.out)


if __name__ == "__main__":
    main()
