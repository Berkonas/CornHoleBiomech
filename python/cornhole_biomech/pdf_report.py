"""Printable athlete report (US Letter PDF, vector) built only from saved analysis outputs.

Nothing here analyses video or writes into the library except the PDF itself. The report reads
project.json, each throw's results.json / two_view.json / manifest.json, and reuses the engine's own
definitions so every number matches the app:

* which throws are pooled: the athlete dashboard's comparable group (``cli.dashboard_base_trial`` with
  ``insights.compatible_key``; needs-reanalysis and < 80 % body tracking are left out with the reason);
* per-throw rows: as ``pipeline.analyze_relationships`` builds them (summaries, coach metrics with
  unreliable values withheld, front-camera values from ``pipeline.two_view_row``);
* scored vs missed: ``performance.performance_summary`` and ``performance.minimum_claim_group``;
* ACL statistics: ``zones.sports_stats``; noise floors: ``performance.VARIABLES`` and ``reliability.BY_KEY``;
* usual group: median ± robust SD (1.4826 × MAD) from ≥ 8 located throws, as ``attribution.py``;
* miss explanations: two_view.json ``explanation`` (sentence) and ``attribution`` (named parts) as saved.

Missing stays missing: a value that was not measured is counted as unavailable, never drawn as 0.
Measured values are filled marks, estimated values hollow marks; outcomes also differ by marker shape
so the pages read in grayscale.
"""
from __future__ import annotations

import json
import math
import textwrap
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .regulation import Board

REPORT_VERSION = "athlete_report_pdf_v1"
PAGE_SIZE_IN = (8.5, 11.0)
MARGIN_IN = 0.6

# Outcome inks are the app's (DesignSystem.swift scoredInk / missInk, BoardEndsMap hole green); marker shapes
# keep the groups apart when printed in grayscale.
HOLE_INK = (0.10, 0.62, 0.25)
BOARD_INK = (0.165, 0.471, 0.839)
MISS_INK = (0.922, 0.408, 0.204)
UNKNOWN_INK = (0.50, 0.50, 0.50)
ATHLETE_INK = (0.15, 0.51, 0.56)
TEXT_INK = (0.10, 0.10, 0.10)
MUTED_INK = (0.40, 0.40, 0.40)
NOISE_FILL = (0.86, 0.86, 0.86)
OUTCOMES: tuple[tuple[int | None, str, tuple[float, float, float], str], ...] = (
    (3, "Hole · 3", HOLE_INK, "^"),
    (1, "Board · 1", BOARD_INK, "o"),
    (0, "Miss · 0", MISS_INK, "s"),
    (None, "Not recorded", UNKNOWN_INK, "D"),
)
OUTCOME_STYLE = {score: (label, ink, marker) for score, label, ink, marker in OUTCOMES}

BOARD = Board()
INCH = 0.0254
HOLE_X_IN = BOARD.width_m / 2 / INCH                     # 12 in across
HOLE_Y_IN = BOARD.hole_along / INCH                      # 39 in from the front edge
HOLE_R_IN = BOARD.hole_radius_m / INCH                   # 3 in
BOARD_W_IN, BOARD_L_IN = BOARD.width_m / INCH, BOARD.length_m / INCH

RELEASE_KEYS = ("bag_release_speed_m_s", "bag_release_angle_deg", "bag_release_height_m")
# Release quantities whose measured/estimated state the engine records in results["chain"]["quantities"].
CHAIN_STATE = {"bag_release_speed_m_s": "release_speed_m_s", "bag_release_angle_deg": "release_angle_deg",
               "bag_release_height_m": "release_height_m"}
# Front-camera row keys without a performance.Variable (labels from two_view.json "frontal", no noise floor).
FRONT_EXTRA = {
    "front_follow_through_across_sw": ("Hand across the body 0.15 s later", "shoulder widths"),
    "front_shoulder_tilt_deg": ("Shoulder tilt at release", "°"),
    "front_stance_offset_m": ("Stance offset from centre line", "m"),
    "front_hand_path_range_sw": ("Hand path sideways range", "shoulder widths"),
    "front_trunk_lean_change_deg": ("Trunk lean change, set-up→release", "°"),
}

LIMITATIONS = (
    "Side-camera body angles are 2D projections into the image plane, not 3D joint angles; the front camera "
    "adds left/right but its body measures are projections too.",
    "Release speed, angle and height come from a drag-free flight fit; metres rely on a scale that is "
    "sometimes estimated (hollow marks).",
    "Small samples: one athlete's throws from a few sessions. Medians and spreads will move as more throws "
    "are recorded (target 20–40).",
    "Every comparison is within this athlete and observational: differences between scored throws and misses "
    "are associations, not causes.",
    "Values that were not measured are left out and counted as unavailable; nothing is filled in.",
)


# ------------------------------------------------------------------------------------------------
# Data


def _read(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except (OSError, ValueError):
        return default


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _date_of(trial: dict[str, Any]) -> str | None:
    value = trial.get("recordingDate") or trial.get("createdAt")
    return str(value)[:10] if value else None


def _order_key(trial: dict[str, Any]) -> tuple:
    return (_date_of(trial) or "", trial.get("takeNumber") or 0, trial.get("throwInTake") or 0,
            trial.get("createdAt") or "", trial.get("name") or "")


def _quantity_state(results: dict[str, Any], key: str) -> str:
    """'measured' / 'estimated' for a release value: the engine's chain state, else the scale's for metres."""
    name = CHAIN_STATE.get(key)
    state = (((results.get("chain") or {}).get("quantities") or {}).get(name) or {}).get("state") if name else None
    if state in ("measured", "estimated"):
        return state
    if key.endswith("_m_s") or key.endswith("_m"):
        return "measured" if (results.get("scale") or {}).get("status") == "measured" else "estimated"
    return "measured"


def _front_state(two_view: dict[str, Any], key: str) -> str:
    from .pipeline import TWO_VIEW_ROW_KEYS
    section, name = TWO_VIEW_ROW_KEYS[key]
    item = (two_view.get(section) or {})
    item = item if section == "heading" else item.get(name)
    status = item.get("status") if isinstance(item, dict) else None
    return "estimated" if status == "estimated" else "measured"


def _landing(two_view: dict[str, Any] | None, outcome: dict[str, Any]) -> dict[str, Any]:
    """First contact and rest in board inches (x across 0–24 left→right, y along 0–48 from the front)."""
    out: dict[str, Any] = {"contact": None, "rest": None, "state": None, "source": None}
    landing = (two_view or {}).get("landing") or {}
    if (two_view or {}).get("status") == "measured" and landing:
        contact, rest = landing.get("contact") or {}, landing.get("rest") or {}
        c = (_num(contact.get("x_in")), _num(contact.get("y_in")))
        r = (_num(rest.get("x_in")), _num(rest.get("y_in")))
        out["contact"] = c if None not in c else None
        out["rest"] = r if None not in r else None
        miss_status = ((two_view or {}).get("miss") or {}).get("status")
        out["state"] = "estimated" if miss_status in ("estimated", "partial") else "measured"
        out["source"] = "front + side camera"
        if out["contact"] or out["rest"]:
            return out
    points = []
    for key in ("first_contact_point", "final_resting_point"):
        p = outcome.get(key) or {}
        xy = (_num(p.get("x_inches")), _num(p.get("y_inches")))
        points.append((xy if None not in xy else None, p.get("precision")))
    out["contact"], out["rest"] = points[0][0], points[1][0]
    precisions = {p for _, p in points if p}
    out["state"] = "measured" if precisions and precisions <= {"board_camera_homography"} else "estimated"
    out["source"] = "recorded outcome"
    return out


def _named_parts(attribution: dict[str, Any] | None) -> list[str] | None:
    """Parts the engine named (attribution.py naming rule); None when the throw has no attribution."""
    if not isinstance(attribution, dict):
        return None
    names = []
    for axis in ("lateral", "depth"):
        for c in ((attribution.get(axis) or {}).get("components") or []):
            if c.get("named"):
                share = _num(c.get("share"))
                names.append(c.get("label", c.get("key", "part")) + (f" ({share:.0%})" if share is not None else ""))
    for d in attribution.get("drivers") or []:
        if d.get("named"):
            names.append(str(d.get("label", d.get("key", "driver"))))
    return names


def _row(trial: dict[str, Any], directory: Path, results: dict[str, Any]) -> dict[str, Any]:
    """One per-throw comparison row, as pipeline.analyze_relationships builds it."""
    from .pipeline import two_view_row
    row = {"trial_id": trial["id"], "score_category": (trial.get("outcome") or {}).get("score_category")}
    row.update(results.get("summaries") or {})
    row.update(two_view_row(directory))
    for key, metric in (results.get("coach_metrics") or {}).items():
        row[key] = (metric or {}).get("value")
    return row


def collect(library: str | Path, athlete_id: str) -> dict[str, Any]:
    """Everything the report draws for one athlete, read from the library (no video, no writes)."""
    from .cli import dashboard_base_trial
    from .insights import compatible_key, incompatibility_reason
    from .performance import performance_summary
    from .zones import sports_stats

    root = Path(library).expanduser().resolve()
    project = _read(root / "project.json")
    if not project:
        raise ValueError(f"No athlete library at {root} (project.json is missing).")
    athlete = next((a for a in project.get("athletes", []) if a.get("id") == athlete_id), None)
    if athlete is None:
        raise ValueError("This athlete is not in the library.")
    trials = sorted((t for t in project.get("trials", []) if t.get("athleteID") == athlete_id), key=_order_key)
    labels = {t["id"]: (t.get("name") or t.get("originalFilename") or t["id"]) for t in trials}
    analysed = [t for t in trials if t.get("analysisRelativePath")
                and (root / t["analysisRelativePath"] / "results.json").exists()]
    if not analysed:
        raise ValueError("Analyze at least one throw for this athlete first.")

    base = dashboard_base_trial(root, analysed)
    base_manifest = _read(root / base["analysisRelativePath"] / "manifest.json", {}) or {}
    base_key = compatible_key(base, base_manifest)
    excluded = [{"label": labels[t["id"]], "reason": "not analysed yet"} for t in trials if t not in analysed]
    throws: list[dict[str, Any]] = []
    all_versions: dict[str, int] = {}
    for t in analysed:
        directory = root / t["analysisRelativePath"]
        manifest = _read(directory / "manifest.json", {}) or {}
        version = manifest.get("method_version") or "unversioned (pre-method-version)"
        all_versions[version] = all_versions.get(version, 0) + 1
        if (directory / "needs_reanalysis.json").exists():
            excluded.append({"label": labels[t["id"]], "reason": "needs re-analysis"})
            continue
        if compatible_key(t, manifest) != base_key:
            excluded.append({"label": labels[t["id"]],
                             "reason": incompatibility_reason(t, manifest, base, base_manifest)})
            continue
        results = _read(directory / "results.json", {}) or {}
        two_view = _read(directory / "two_view.json")
        outcome = t.get("outcome") or {}
        usable = _num((results.get("quality") or {}).get("usable_frame_percentage"))
        throws.append({
            "id": t["id"], "label": labels[t["id"]], "date": _date_of(t), "take": t.get("takeNumber"),
            "session": t.get("sessionID"), "score": outcome.get("score_category"),
            "method_version": version, "two_view_version": (two_view or {}).get("method_version"),
            "two_view_status": (two_view or {}).get("status"),
            "camera_result": ((two_view or {}).get("result") or {}).get("category"),
            "movement_ok": usable is not None and usable >= 80,
            "row": _row(t, directory, results),
            "state": {**{k: _quantity_state(results, k) for k in RELEASE_KEYS},
                      **({k: _front_state(two_view, k) for k in _front_keys()} if two_view else {})},
            "landing": _landing(two_view, outcome),
            "miss": (two_view or {}).get("miss") or {},
            "explanation": (two_view or {}).get("explanation") or {},
            "attribution": (two_view or {}).get("attribution"),
            "slide_in": _num((results.get("summaries") or {}).get("board_slide_in")),
        })
        if not throws[-1]["movement_ok"]:
            excluded.append({"label": labels[t["id"]],
                             "reason": "body tracking covered less than 80% of the frames (outcome and landing kept)"})
    for number, th in enumerate(throws, 1):
        th["number"] = number
    rows = [th["row"] for th in throws if th["movement_ok"]]
    dates = sorted(d for d in (th["date"] for th in throws) if d)
    takes = {(th["session"], th["take"]) for th in throws if th["take"] is not None}
    two_view_versions: dict[str, int] = {}
    for th in throws:
        if th["two_view_version"]:
            two_view_versions[th["two_view_version"]] = two_view_versions.get(th["two_view_version"], 0) + 1
    return {
        "root": str(root), "athlete": athlete.get("participantCode") or "Athlete", "athlete_id": athlete_id,
        "throws": throws, "rows": rows, "labels": labels, "excluded": excluded,
        "all_throw_count": len(trials), "analysed_count": len(analysed),
        "date_range": (dates[0], dates[-1]) if dates else None, "take_count": len(takes),
        "method_versions": all_versions, "included_method_version": base_manifest.get("method_version"),
        "two_view_versions": two_view_versions, "pose_model": base_manifest.get("pose_model"),
        "performance": performance_summary(rows, labels),
        "sports": sports_stats([th["score"] for th in throws]),
        "engine_version": base_manifest.get("python_package_version"),
    }


def _front_keys() -> tuple[str, ...]:
    from .pipeline import TWO_VIEW_ROW_KEYS
    return tuple(TWO_VIEW_ROW_KEYS)


# ------------------------------------------------------------------------------------------------
# Small statistics (descriptive only)


def _finite(values) -> np.ndarray:
    a = np.asarray([v for v in values if v is not None], float)
    return a[np.isfinite(a)]


def _robust(values) -> tuple[float | None, float | None]:
    """Median and robust SD (1.4826 × MAD), as attribution.usual_from_siblings."""
    from .attribution import MAD_TO_SD
    a = _finite(values)
    if not a.size:
        return None, None
    median = float(np.median(a))
    return median, float(MAD_TO_SD * np.median(np.abs(a - median))) if a.size > 1 else None


def _fmt(value: float | None, decimals: int = 2, unit: str = "") -> str:
    if value is None:
        return "—"
    text = f"{value:.{decimals}f}"
    if float(text) == 0:
        text = text.lstrip("-")
    text = text.replace("-", "−")
    return text + ("" if not unit else unit if unit == "°" else f" {unit}")


def _signed_in(value: float | None, negative: str, positive: str) -> str:
    if value is None:
        return "—"
    if abs(value) < 0.5:
        return "0 in"
    return f"{abs(value):.0f} in {negative if value < 0 else positive}"


# ------------------------------------------------------------------------------------------------
# Page helpers


def _style() -> dict[str, Any]:
    return {"font.family": "DejaVu Sans", "font.size": 8.5, "axes.titlesize": 9.5, "axes.labelsize": 8.5,
            "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5, "axes.edgecolor": "0.35",
            "axes.linewidth": 0.6, "xtick.color": "0.25", "ytick.color": "0.25", "axes.labelcolor": "0.1",
            "pdf.fonttype": 42, "ps.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False,
            "lines.linewidth": 1.0, "hatch.linewidth": 0.5}


class _Page:
    """One US Letter page with a header, a footer and inch-based placement helpers."""

    def __init__(self, title: str, subtitle: str | None, data: dict[str, Any]):
        from matplotlib.figure import Figure
        self.fig = Figure(figsize=PAGE_SIZE_IN)
        self.data = data
        w, h = PAGE_SIZE_IN
        self.fig.text(MARGIN_IN / w, 1 - 0.55 / h, title, fontsize=15, weight="bold", color=TEXT_INK, va="baseline")
        lines = textwrap.wrap(subtitle, 128) if subtitle else []
        if lines:
            self.fig.text(MARGIN_IN / w, 1 - 0.68 / h, "\n".join(lines), fontsize=8.2, color=MUTED_INK, va="top",
                          linespacing=1.3)
        rule = 0.9 + max(0, len(lines) - 1) * 0.15
        self.fig.add_artist(_hline(self.fig, 1 - rule / h))
        self.top = rule + 0.15     # inches from the top already used

    def axes(self, left: float, top: float, width: float, height: float, **kwargs):
        """Axes placed in inches from the page's top-left corner."""
        w, h = PAGE_SIZE_IN
        return self.fig.add_axes((left / w, 1 - (top + height) / h, width / w, height / h), **kwargs)

    def text(self, left: float, top: float, text: str, **kwargs):
        w, h = PAGE_SIZE_IN
        if "\n" not in text:
            kwargs.pop("linespacing", None)       # a single line with linespacing sits lower than one without
        kwargs.setdefault("va", "top")
        kwargs.setdefault("color", TEXT_INK)
        return self.fig.text(left / w, 1 - top / h, text, **kwargs)

    def paragraph(self, left: float, top: float, text: str, width_chars: int = 105, size: float = 8.5,
                  line_in: float | None = None, **kwargs) -> float:
        """Wrapped text; returns the inches it used."""
        lines = textwrap.wrap(text, width_chars) or [""]
        line_in = line_in or size * 1.45 / 72
        self.text(left, top, "\n".join(lines), fontsize=size, linespacing=1.35, **kwargs)
        return len(lines) * line_in

    def finish(self, number: int, total: int):
        w, h = PAGE_SIZE_IN
        d = self.data
        self.fig.add_artist(_hline(self.fig, 0.55 / h))
        self.fig.text(MARGIN_IN / w, 0.38 / h,
                      f"{d['athlete']} · Cornhole Biomechanics Lab {d.get('engine_version') or ''} · "
                      f"generated {date.today().isoformat()} · {REPORT_VERSION}",
                      fontsize=7, color=MUTED_INK)
        self.fig.text(1 - MARGIN_IN / w, 0.38 / h, f"Page {number} of {total}", fontsize=7, color=MUTED_INK,
                      ha="right")


def _hline(fig, y: float):
    from matplotlib.lines import Line2D
    w = PAGE_SIZE_IN[0]
    return Line2D([MARGIN_IN / w, 1 - MARGIN_IN / w], [y, y], transform=fig.transFigure, color="0.6", lw=0.6)


def _scatter(ax, x, y, score, state, size=34, zorder=3, **kwargs):
    label, ink, marker = OUTCOME_STYLE.get(score, OUTCOME_STYLE[None])
    hollow = state == "estimated"
    ax.scatter([x], [y], s=size, marker=marker, facecolors="white" if hollow else [ink],
               edgecolors=[ink if hollow else "black"], linewidths=1.1 if hollow else 0.4, zorder=zorder, **kwargs)


def _legend_handles(include_states: bool = True, scores=(3, 1, 0, None)):
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], ls="", marker=OUTCOME_STYLE[s][2], markerfacecolor=OUTCOME_STYLE[s][1],
                      markeredgecolor="black", markeredgewidth=0.4, markersize=6.5, label=OUTCOME_STYLE[s][0])
               for s in scores]
    if include_states:
        handles += [Line2D([], [], ls="", marker="o", markerfacecolor="0.45", markeredgecolor="black",
                           markeredgewidth=0.4, markersize=6.5, label="filled = measured"),
                    Line2D([], [], ls="", marker="o", markerfacecolor="white", markeredgecolor="0.3",
                           markeredgewidth=1.1, markersize=6.5, label="hollow = estimated")]
    return handles


def _jitter(n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).uniform(-0.18, 0.18, n)


# ------------------------------------------------------------------------------------------------
# Pages


def _page_cover(data: dict[str, Any]) -> _Page:
    throws, sports, perf = data["throws"], data["sports"], data["performance"]
    span = data["date_range"]
    when = "no recording dates" if not span else span[0] if span[0] == span[1] else f"{span[0]} to {span[1]}"
    page = _Page(f"Athlete report · {data['athlete']}", f"Recorded {when}", data)
    x, y = MARGIN_IN, page.top + 0.1

    counts = perf["counts"]
    tiles = [("Throws in this report", str(len(throws)),
              f"{data['analysed_count']} analysed of {data['all_throw_count']} imported"),
             ("Takes", str(data["take_count"]) if data["take_count"] else "—", "distinct takes in these throws"),
             ("Points per round", _fmt(sports.get("ppr"), 1), f"PPR = 4 × points per bag · n = {sports['bags']}"),
             ("In / On / Off", " / ".join("—" if sports.get(k) is None else f"{sports[k]:.0f}%"
                                         for k in ("in_percent", "on_percent", "off_percent")),
              f"of {sports['bags']} bags with a recorded result")]
    tile_w = (PAGE_SIZE_IN[0] - 2 * MARGIN_IN - 0.45) / 4
    for i, (title, value, note) in enumerate(tiles):
        left = x + i * (tile_w + 0.15)
        ax = page.axes(left, y, tile_w, 0.95)
        ax.set_axis_off()
        from matplotlib.patches import FancyBboxPatch
        ax.add_patch(FancyBboxPatch((0.02, 0.02), 0.96, 0.96, boxstyle="round,pad=0,rounding_size=0.06",
                                    transform=ax.transAxes, fc="0.965", ec="0.75", lw=0.6))
        ax.text(0.08, 0.86, title, fontsize=8, color=MUTED_INK, transform=ax.transAxes, va="top")
        ax.text(0.08, 0.58, value, fontsize=17 if len(value) < 9 else 11.5, weight="bold", transform=ax.transAxes,
                va="center")
        ax.text(0.08, 0.2, note, fontsize=6.6, color=MUTED_INK, transform=ax.transAxes, va="center")
    y += 1.2

    # Outcome counts as a bar (shape-coded legend keeps it readable in grayscale).
    page.text(x, y, "Outcomes", fontsize=11, weight="bold")
    y += 0.25
    ax = page.axes(x + 0.95, y, 3.4, 1.25)
    names = [OUTCOME_STYLE[s][0] for s in (3, 1, 0, None)]
    values = [counts["hole"], counts["board"], counts["miss"], counts["unknown"]]
    hatches = ["", "....", "////", ""]
    bars = ax.barh(names[::-1], values[::-1], color=[OUTCOME_STYLE[s][1] for s in (None, 0, 1, 3)],
                   edgecolor="black", linewidth=0.4)
    for bar, hatch in zip(bars, hatches[::-1]):
        bar.set_hatch(hatch)
    for bar, v in zip(bars, values[::-1]):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2, str(v), va="center", fontsize=8)
    ax.set_xlabel("Throws (count)")
    ax.set_xlim(0, max(values + [1]) * 1.2 + 1)
    ax.xaxis.get_major_locator().set_params(integer=True)
    page.paragraph(x + 4.6, y + 0.05,
                   "Per-bag result as recorded in the app: 3 through the hole, 1 on the board, 0 off. "
                   "Throws without a recorded result are counted separately and left out of every scored/missed "
                   "statistic (never treated as misses).", width_chars=48, size=7.8)
    y += 1.65

    # Summary in three lines (performance.performance_summary feedback, unchanged).
    feedback = perf["feedback"]
    page.text(x, y, "Summary", fontsize=11, weight="bold")
    y += 0.27
    for head, body in (("Result", feedback["result"]), ("What differed", feedback["why"]),
                       ("Next practice", feedback["next"])):
        page.text(x, y, head, fontsize=8.5, weight="bold")
        y += page.paragraph(x + 1.15, y, body, width_chars=96, size=8.5) + 0.08
    y += page.paragraph(x + 1.15, y, feedback["caveat"], width_chars=96, size=7.8, color=MUTED_INK) + 0.2

    # Methods and versions, with the mixing warning.
    page.text(x, y, "Methods and versions", fontsize=11, weight="bold")
    y += 0.27
    engine = ", ".join(f"{v} ({n})" for v, n in sorted(data["method_versions"].items())) or "—"
    front = ", ".join(f"{v} ({n})" for v, n in sorted(data["two_view_versions"].items())) or "no two-camera throws"
    for head, body in (("Engine method", engine), ("Two-camera method", front),
                       ("Body tracking", data.get("pose_model") or "—"),
                       ("Pooled group", "the throws the app's athlete summary pools: same session set-up, camera "
                                        "view, throwing side, throw type, target and method version")):
        page.text(x, y, head, fontsize=8.5, weight="bold")
        y += page.paragraph(x + 1.5, y, body, width_chars=90, size=8.2) + 0.05
    warnings = []
    if len(data["method_versions"]) > 1:
        warnings.append(f"Throws were analysed with {len(data['method_versions'])} different engine method versions. "
                        f"Only {data['included_method_version']} throws are pooled here; re-analyse the others "
                        "(Re-analyze All) to include them.")
    if len(data["two_view_versions"]) > 1:
        warnings.append(f"Front-camera results come from {len(data['two_view_versions'])} different two-camera "
                        "method versions, so miss explanations are not all built the same way.")
    if warnings:
        y += 0.08
        for w_text in warnings:
            ax = page.axes(x, y, PAGE_SIZE_IN[0] - 2 * MARGIN_IN, 0.42)
            ax.set_axis_off()
            ax.add_patch(_box(ax, fc=(1.0, 0.95, 0.85), ec=MISS_INK))
            ax.text(0.015, 0.5, "Warning: " + w_text, transform=ax.transAxes, va="center", fontsize=8,
                    wrap=True)
            y += 0.5
    y += 0.15

    excluded = data["excluded"]
    page.text(x, y, f"Left out of the statistics ({len(excluded)})", fontsize=11, weight="bold")
    y += 0.27
    if not excluded:
        page.text(x, y, "None: every analysed throw of this athlete is in the pooled group.", fontsize=8.2)
    else:
        reasons: dict[str, list[str]] = {}
        for item in excluded:
            reasons.setdefault(item["reason"], []).append(item["label"])
        for reason, items in list(reasons.items())[:8]:
            shown = ", ".join(items[:6]) + (f" and {len(items) - 6} more" if len(items) > 6 else "")
            y += page.paragraph(x, y, f"{reason[0].upper() + reason[1:]}: {shown}.", width_chars=110, size=8) + 0.04
    return page


def _box(ax, fc, ec):
    from matplotlib.patches import FancyBboxPatch
    return FancyBboxPatch((0.003, 0.04), 0.994, 0.92, boxstyle="round,pad=0,rounding_size=0.02",
                          transform=ax.transAxes, fc=fc, ec=ec, lw=0.8)


def _page_board(data: dict[str, Any]) -> _Page:
    from matplotlib.patches import Circle, Ellipse, Rectangle
    from .attribution import USUAL_MIN_THROWS
    throws = data["throws"]
    page = _Page("Where the bags landed", "Board to scale (24 × 48 in, hole 6 in across, centre 12 in across and "
                 "39 in up the deck). Thrower's view: front edge at the bottom.", data)
    located_rest = [th for th in throws if th["landing"]["rest"]]
    located_contact = [th for th in throws if th["landing"]["contact"]]
    xs = [p for th in throws for p in (th["landing"]["rest"], th["landing"]["contact"]) if p]
    lo_x = min([-6.0] + [p[0] - 3 for p in xs]); hi_x = max([BOARD_W_IN + 6] + [p[0] + 3 for p in xs])
    lo_y = min([-8.0] + [p[1] - 3 for p in xs]); hi_y = max([BOARD_L_IN + 6] + [p[1] + 3 for p in xs])
    lo_x, hi_x, lo_y, hi_y = max(lo_x, -30), min(hi_x, 54), max(lo_y, -36), min(hi_y, 90)
    aspect = (hi_x - lo_x) / (hi_y - lo_y)
    height_in = min(6.3, 4.3 / aspect)
    width_in = height_in * aspect
    ax = page.axes(MARGIN_IN + 0.45, page.top + 0.15, width_in, height_in)
    ax.set_aspect("equal")
    ax.set_xlim(lo_x, hi_x); ax.set_ylim(lo_y, hi_y)
    ax.add_patch(Rectangle((0, 0), BOARD_W_IN, BOARD_L_IN, fc="0.93", ec="0.25", lw=1.0, zorder=0))
    ax.add_patch(Circle((HOLE_X_IN, HOLE_Y_IN), HOLE_R_IN, fc="white", ec="0.25", lw=1.0, zorder=1))
    ax.axvline(HOLE_X_IN, color="0.7", lw=0.5, ls=(0, (2, 3)), zorder=0.5)
    ax.text(BOARD_W_IN / 2, -1.2, "front edge", ha="center", va="top", fontsize=7, color=MUTED_INK)
    ax.text(BOARD_W_IN / 2, BOARD_L_IN + 1.0, "back edge", ha="center", va="bottom", fontsize=7, color=MUTED_INK)
    ax.set_xlabel("Across the board (in): thrower's left → right")
    ax.set_ylabel("Along the board from the front edge (in)")
    ax.spines[["top", "right"]].set_visible(True)

    def clip(p):
        return (min(max(p[0], lo_x + 0.8), hi_x - 0.8), min(max(p[1], lo_y + 0.8), hi_y - 0.8))

    clipped = 0
    for th in throws:
        landing = th["landing"]
        c, r, state = landing["contact"], landing["rest"], landing["state"]
        if c and r:
            ax.plot([c[0], r[0]], [c[1], r[1]], color="0.45", lw=0.6, zorder=2)
        if c:
            label, ink, _ = OUTCOME_STYLE.get(th["score"], OUTCOME_STYLE[None])
            cc = clip(c)
            ax.scatter([cc[0]], [cc[1]], s=14, marker="o", facecolors="white", edgecolors=[ink],
                       linewidths=0.9, zorder=3)
        if r:
            rc = clip(r)
            clipped += rc != r
            _scatter(ax, rc[0], rc[1], th["score"], state, size=40, zorder=4)

    def ellipse(points, style):
        mx, sx = _robust([p[0] for p in points]); my, sy = _robust([p[1] for p in points])
        if None in (mx, sx, my, sy) or len(points) < USUAL_MIN_THROWS:
            return None
        ax.add_patch(Ellipse((mx, my), 2 * max(sx, 0.2), 2 * max(sy, 0.2), fill=False, ec=ATHLETE_INK, lw=1.4,
                             ls=style, zorder=5))
        ax.plot([mx], [my], marker="+", color=ATHLETE_INK, ms=9, mew=1.4, zorder=5)
        return mx, sx, my, sy

    rest_group = ellipse([th["landing"]["rest"] for th in located_rest], "-")
    contact_group = ellipse([th["landing"]["contact"] for th in located_contact], (0, (4, 2)))

    # Right column: legend and the numbers behind the picture; below: the signed miss at rest by axis.
    from matplotlib.lines import Line2D
    rx = MARGIN_IN + 0.45 + 4.3 + 0.35
    rw = PAGE_SIZE_IN[0] - MARGIN_IN - rx
    lax = page.axes(rx, page.top + 0.15, rw, 2.3)
    lax.set_axis_off()
    handles = _legend_handles() + [
        Line2D([], [], ls="", marker="o", markerfacecolor="white", markeredgecolor="0.3", markersize=4.5,
               label="small ring = first contact"),
        Line2D([], [], color="0.45", lw=0.6, label="line = slide to rest"),
        Line2D([], [], color=ATHLETE_INK, lw=1.4, label="usual group at rest\n(median ± robust SD)"),
        Line2D([], [], color=ATHLETE_INK, lw=1.4, ls=(0, (4, 2)), label="usual group at\nfirst contact")]
    lax.legend(handles=handles, loc="upper left", frameon=False, ncol=1, handletextpad=0.6, borderaxespad=0,
               fontsize=7.3, labelspacing=0.45)

    y = page.top + 2.75
    lines = [f"Where it stopped: located for {len(located_rest)} of {len(throws)} throws; "
             f"first contact for {len(located_contact)}."]
    if rest_group:
        mx, sx, my, sy = rest_group
        lines.append(f"Usual group at rest: centre {mx - HOLE_X_IN:+.0f} in across (+ right) and "
                     f"{my - HOLE_Y_IN:+.0f} in along (+ long) from the hole centre; robust SD {sx:.1f} in across, "
                     f"{sy:.1f} in along.".replace("-", "−"))
    else:
        lines.append(f"No usual group is drawn: it needs at least {USUAL_MIN_THROWS} throws with a located rest.")
    if contact_group:
        mx, sx, my, sy = contact_group
        lines.append(f"Usual first contact: {my:.0f} in up the deck (robust SD {sy:.1f} in along, {sx:.1f} in "
                     "across).")
    slides = _finite(th["slide_in"] for th in throws)
    if slides.size:
        lines.append(f"Slide on the board (side camera): median {np.median(slides):.0f} in, middle half "
                     f"{np.percentile(slides, 25):.0f}–{np.percentile(slides, 75):.0f} in (n = {slides.size}).")
    if clipped:
        lines.append(f"{clipped} bag(s) stopped beyond the drawn area and are pinned to its edge.")
    for line in lines:
        y += page.paragraph(rx, y, line, width_chars=int(rw * 14.5), size=7.8) + 0.07

    rest_x = [(th["landing"]["rest"][0] - HOLE_X_IN, th) for th in located_rest]
    rest_y = [(th["landing"]["rest"][1] - HOLE_Y_IN, th) for th in located_rest]
    top = page.top + 0.15 + max(height_in, 5.6) + 0.75
    half = (PAGE_SIZE_IN[0] - 2 * MARGIN_IN - 2.0 - 0.3) / 2
    for i, (title, values, xlabel) in enumerate((
            ("Left / right of the hole at rest", rest_x, "Left (−) / right (+) of hole centre (in)"),
            ("Short / long of the hole at rest", rest_y, "Short (−) / long (+) of hole centre (in)"))):
        hax = page.axes(MARGIN_IN + 1.0 + i * (half + 1.3), top, half, 1.35)
        hax.set_title(f"{title} (n = {len(values)})", loc="left", fontsize=8.5)
        _strip_by_outcome(hax, values, seed=len(values) + i)
        hax.axvspan(-HOLE_R_IN, HOLE_R_IN, color=NOISE_FILL, zorder=0)
        hax.axvline(0, color="0.3", lw=0.6)
        hax.set_xlabel(xlabel)
    page.paragraph(MARGIN_IN, top + 1.95, "Grey band: within the hole radius (±3 in). Rest and contact come from the "
                   "front camera's deck homography (left/right about ±0.3 in) and the side camera (along about ±2 in); "
                   "throws without a front camera use the recorded outcome point. The usual group needs at least "
                   f"{USUAL_MIN_THROWS} located throws.", width_chars=125, size=7.2, color=MUTED_INK)
    return page


def _strip_by_outcome(ax, values: list[tuple[float, dict[str, Any]]], seed: int = 0):
    """Horizontal strip: one row per outcome present, jittered vertically."""
    order = [s for s in (3, 1, 0, None) if any(th["score"] == s for _, th in values)] or [None]
    for i, score in enumerate(order):
        group = [(v, th) for v, th in values if th["score"] == score]
        jitter = _jitter(len(group), seed + i)
        for (v, th), j in zip(group, jitter):
            _scatter(ax, v, i + j, th["score"], th["landing"]["state"], size=22)
    ax.set_yticks(range(len(order)), [f"{OUTCOME_STYLE[s][0]} ({sum(th['score'] == s for _, th in values)})"
                                      for s in order])
    ax.set_ylim(-0.6, len(order) - 0.4)
    ax.invert_yaxis()
    ax.tick_params(axis="y", length=0)


def _page_release(data: dict[str, Any]) -> _Page:
    from .performance import VARIABLES, _noise_floor
    by_key = {v.key: v for v in VARIABLES}
    throws = [th for th in data["throws"] if th["movement_ok"]]
    rows = data["rows"]
    page = _Page("Release conditions", "Bag release speed, angle and height on every throw, by outcome and in "
                 "recording order. Grey band: the variable's noise floor (smaller differences are not interpretable).",
                 data)
    col_w = (PAGE_SIZE_IN[0] - 2 * MARGIN_IN - 0.35 - 2 * 0.55 + 0.1) / 3
    top = page.top + 0.45
    groups = [s for s in (3, 1, 0, None) if s is not None or any(th["score"] is None for th in throws)]
    for i, key in enumerate(RELEASE_KEYS):
        variable = by_key[key]
        floor = _noise_floor(variable, rows)
        unit = variable.unit
        values = [(th["row"].get(key), th) for th in throws]
        present = [(float(v), th) for v, th in values if _num(v) is not None]
        missing = len(values) - len(present)
        left = MARGIN_IN + 0.35 + i * (col_w + 0.55)
        ax = page.axes(left, top, col_w - 0.1, 3.4)
        ax.set_title(f"{variable.label} ({unit})", loc="left", fontsize=9.5, weight="bold", pad=16)
        ax.text(0, 1.02, f"n = {len(present)} · unavailable {missing} · noise floor "
                f"{_fmt(floor, 2 if unit != '°' else 1, unit)}", transform=ax.transAxes, fontsize=7.0,
                color=MUTED_INK, va="bottom")
        all_values = _finite(v for v, _ in present)
        if all_values.size and floor:
            median = float(np.median(all_values))
            ax.axhspan(median - floor / 2, median + floor / 2, color=NOISE_FILL, zorder=0, lw=0)
            ax.axhline(median, color="0.55", lw=0.5, ls=(0, (2, 2)), zorder=0.5)
        for g, score in enumerate(groups):
            group = [(v, th) for v, th in present if th["score"] == score]
            for (v, th), j in zip(group, _jitter(len(group), 7 * i + g)):
                _scatter(ax, g + j, v, score, th["state"].get(key, "measured"), size=26)
            if group:
                m = float(np.median([v for v, _ in group]))
                ax.plot([g - 0.3, g + 0.3], [m, m], color="black", lw=1.6, zorder=5, solid_capstyle="butt")
        ax.set_xticks(range(len(groups)),
                      [f"{'No result' if s is None else OUTCOME_STYLE[s][0].split(' ·')[0]}"
                       f"\nn={sum(th['score'] == s for _, th in present)}"
                       for s in groups])
        ax.set_xlim(-0.6, len(groups) - 0.4)
        ax.set_ylabel(f"{variable.label} ({unit})")
        ax.tick_params(axis="x", length=0)
        if not present:
            ax.text(0.5, 0.5, "Not measured on any throw", transform=ax.transAxes, ha="center", color=MUTED_INK)

        # Recording order: drift within and between takes.
        if i == 0:
            page.text(MARGIN_IN, top + 4.05, "Throw by throw, in recording order", fontsize=10, weight="bold")
        sax = page.axes(left, top + 4.6, col_w - 0.1, 2.25)
        order = [(th["number"], v, th) for v, th in present]
        if order:
            sax.plot([o[0] for o in order], [o[1] for o in order], color="0.75", lw=0.6, zorder=1)
        for n, v, th in order:
            _scatter(sax, n, v, th["score"], th["state"].get(key, "measured"), size=20)
        if all_values.size and floor:
            sax.axhspan(median - floor / 2, median + floor / 2, color=NOISE_FILL, zorder=0, lw=0)
        _take_boundaries(sax, throws)
        sax.set_xlabel("Throw number (recording order)")
        sax.set_ylabel(f"{variable.label} ({unit})")
        sax.set_xlim(0.3, max([th["number"] for th in throws] + [1]) + 0.7)
        sd = float(np.std(all_values, ddof=1)) if all_values.size > 1 else None
        stats = (f"median {_fmt(float(np.median(all_values)) if all_values.size else None, variable.decimals + 1, unit)}"
                 f" · SD {_fmt(sd, variable.decimals + 1, unit)}"
                 + (f" · {sd / floor:.1f}× noise" if sd is not None and floor else ""))
        sax.text(0, 1.03, stats, transform=sax.transAxes, fontsize=7.0, color=MUTED_INK, va="bottom")

    lax = page.axes(MARGIN_IN, top + 7.45, PAGE_SIZE_IN[0] - 2 * MARGIN_IN, 0.4)
    lax.set_axis_off()
    lax.legend(handles=_legend_handles(), loc="center left", ncol=3, frameon=False, borderaxespad=0,
               columnspacing=2.0)
    page.paragraph(MARGIN_IN, top + 7.95,
                   "Black bars are group medians. Hollow marks: metres from an estimated camera scale (the engine's "
                   "chain state). Values withheld for poor tracking count as unavailable. Thin vertical lines separate "
                   "takes. Release angle's noise floor is twice the median per-throw fit standard error.",
                   width_chars=125, size=7.2, color=MUTED_INK)
    return page


def _take_boundaries(ax, throws: list[dict[str, Any]]):
    previous = None
    for th in throws:
        key = (th["session"], th["take"])
        if previous is not None and key != previous and th["take"] is not None:
            ax.axvline(th["number"] - 0.5, color="0.85", lw=0.6, zorder=0)
        previous = key


def _consistency_metrics(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Side-camera coach metrics of the per_throw and profile tiers (reliability.METRIC_TIERS; advanced ones are
    left out) and the front-camera comparison-row measures (pipeline.TWO_VIEW_ROW_KEYS)."""
    from .performance import VARIABLES
    from .reliability import COACH_METRICS
    variables = {v.key: v for v in VARIABLES}
    side = tuple(m.key for m in COACH_METRICS if getattr(m, "tier", "per_throw") in ("per_throw", "profile"))
    tiers = {m.key: getattr(m, "tier", None) for m in COACH_METRICS}
    labels = {m.key: (m.label, m.unit, m.noise_floor) for m in COACH_METRICS}
    out = []
    for view, keys in (("Side camera", side), ("Front camera", _front_keys())):
        for key in keys:
            if key in labels:
                label, unit, floor = labels[key]
                decimals = variables[key].decimals if key in variables else 2
            elif key in variables:
                v = variables[key]
                label, unit, floor, decimals = v.label, v.unit, v.noise_floor, v.decimals
            else:
                label, unit = FRONT_EXTRA.get(key, (key.removeprefix("front_").replace("_", " ").capitalize(), ""))
                floor, decimals = None, 2
            values = [(th["row"].get(key), th) for th in data["throws"] if th["movement_ok"]]
            present = [(float(v), th) for v, th in values if _num(v) is not None]
            out.append({"view": view, "key": key, "label": label, "unit": unit, "floor": floor,
                        "tier": tiers.get(key), "decimals": max(decimals, 1) if unit != "°" else 0,
                        "present": present, "unavailable": len(values) - len(present)})
    return out


def _page_consistency(data: dict[str, Any]) -> _Page:
    metrics = _consistency_metrics(data)
    page = _Page("Movement consistency", "Each measure on every pooled throw: dots by outcome, box = middle half "
                 "(IQR), bar = median. SD / noise: throw-to-throw SD over the measure's noise floor.", data)
    shown = [m for m in metrics if m["present"] or m["view"] == "Side camera"]
    hidden_front = [m for m in metrics if m not in shown]
    from matplotlib.ticker import MaxNLocator
    views = len({m["view"] for m in shown})
    available = PAGE_SIZE_IN[1] - 0.75 - page.top - 0.2 - 1.25 - 0.3 * views
    row_h = min(0.5, available / max(1, len(shown))) - 0.04
    y = page.top + 0.2
    label_w, plot_w = 1.95, 2.35
    stats_x = MARGIN_IN + label_w + plot_w + 0.2
    columns = (0, 0.28, 0.78, 1.72, 2.2)
    ratios = {m["key"]: (float(np.std(_finite(v for v, _ in m["present"]), ddof=1)) / m["floor"])
              for m in shown if len(m["present"]) > 1 and m["floor"]}
    worst = max(ratios, key=ratios.get) if ratios else None
    view = None
    for m in shown:
        if m["view"] != view:
            view = m["view"]
            page.text(MARGIN_IN, y + 0.02, view, fontsize=10, weight="bold")
            for cx, head in zip(columns, ("n", "median", "IQR", "SD", "SD / noise")):
                page.text(stats_x + cx, y + 0.05, head, fontsize=7, color=MUTED_INK)
            y += 0.3
        values = _finite(v for v, _ in m["present"])
        unit = m["unit"]
        bold = m["key"] == worst
        label = m["label"] if len(m["label"]) <= 34 else m["label"][:32].rstrip() + "…"
        page.text(MARGIN_IN, y + 0.02, label, fontsize=7.6, weight="bold" if bold else "normal")
        tier = {"per_throw": " · per throw", "profile": " · profile"}.get(m.get("tier"), "")
        page.text(MARGIN_IN, y + 0.17, (unit or "ratio") + tier, fontsize=6.4, color=MUTED_INK)
        ax = page.axes(MARGIN_IN + label_w, y, plot_w, row_h * 0.6)
        ax.spines[["left"]].set_visible(False)
        ax.set_yticks([])
        ax.tick_params(axis="x", labelsize=6.0, length=2, pad=1)
        ax.xaxis.set_major_locator(MaxNLocator(5))
        if values.size:
            q25, q50, q75 = np.percentile(values, [25, 50, 75])
            ax.add_patch(_iqr_patch(q25, q75))
            ax.plot([q50, q50], [-0.45, 0.45], color="black", lw=1.6, zorder=4)
            for (v, th), j in zip(m["present"], _jitter(len(m["present"]), len(m["key"]))):
                _scatter(ax, v, j * 1.5, th["score"], th["state"].get(m["key"], "measured"), size=11)
            span = float(values.max() - values.min()) or (m["floor"] or 1.0)
            ax.set_xlim(values.min() - 0.12 * span, values.max() + 0.12 * span)
            ax.set_ylim(-0.6, 0.6)
            sd = float(np.std(values, ddof=1)) if values.size > 1 else None
            d = m["decimals"]
            ratio = ratios.get(m["key"])
            words = ("" if ratio is None else " within" if ratio <= 1 else " variable" if ratio > 2 else " moderate")
            cells = [f"{values.size}", _fmt(float(q50), d), f"{_fmt(float(q25), d)} – {_fmt(float(q75), d)}",
                     _fmt(sd, d + 1), "—" if ratio is None else f"{ratio:.1f}×{words}"]
        else:
            ax.set_xticks([])
            ax.text(0.5, 0.5, "not measured", transform=ax.transAxes, ha="center", va="center", fontsize=7,
                    color=MUTED_INK)
            cells = ["0", "—", "—", "—", "—"]
        for cx, cell in zip(columns, cells):
            page.text(stats_x + cx, y + 0.05, cell, fontsize=7.2, weight="bold" if bold else "normal")
        if m["unavailable"]:
            page.text(stats_x, y + 0.19, f"{m['unavailable']} unavailable", fontsize=6.2, color=MUTED_INK)
        y += row_h + 0.04
    y += 0.1
    lax = page.axes(MARGIN_IN, y, PAGE_SIZE_IN[0] - 2 * MARGIN_IN, 0.3)
    lax.set_axis_off()
    lax.legend(handles=_legend_handles(), loc="center left", ncol=3, frameon=False, borderaxespad=0,
               columnspacing=2.0)
    y += 0.4
    note = ("SD / noise ≤ 1 (within): the spread is within what the measurement can resolve; > 2: clearly variable "
            "(coaching.release_profile). Side-camera measures are the per-throw and profile tiers of reliability.py "
            "(per throw: resolves one throw's difference from usual; profile: describes how this athlete throws, "
            "not why one throw differed); advanced measures are left out. Noise floors are those documented in "
            "docs/METRICS.md; measures without one show —.")
    if worst:
        m = next(x for x in metrics if x["key"] == worst)
        note = (f"Least repeatable relative to its noise: {m['label'].lower()} (bold, SD {ratios[worst]:.1f}× its "
                f"noise floor). ") + note
    if hidden_front:
        note += " No front-camera measures for this athlete (side camera only)." if len(hidden_front) == len(
            _front_keys()) else f" Not measured: {', '.join(m['label'].lower() for m in hidden_front)}."
    page.paragraph(MARGIN_IN, y, note, width_chars=135, size=6.9, color=MUTED_INK)
    return page


def _iqr_patch(q25: float, q75: float):
    from matplotlib.patches import Rectangle
    return Rectangle((q25, -0.42), max(q75 - q25, 1e-9), 0.84, fc=(0.84, 0.91, 0.92), ec=ATHLETE_INK, lw=0.7,
                     zorder=1)


def _miss_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for th in data["throws"]:
        miss = th["miss"]
        label = OUTCOME_STYLE.get(th["score"], OUTCOME_STYLE[None])[0]
        if th["score"] is None and th["camera_result"]:
            camera = {"throughHole": "hole", "onBoard": "board", "offBoard": "off"}.get(th["camera_result"],
                                                                                        th["camera_result"])
            label = f"Not recorded (camera: {camera})"
        status = miss.get("status")
        short_long = _num(miss.get("short_long_in")) if status not in (None, "unavailable") else None
        left_right = _num(miss.get("left_right_in")) if status not in (None, "unavailable") else None
        attribution = th["attribution"] if isinstance(th["attribution"], dict) else None
        block = (attribution or {}).get("explanation") if attribution else None
        lines: list[tuple[str, str]] = []
        phase = "—"
        if th["two_view_status"] is None:
            lines.append(("", "No front camera on this throw: no left/right and no miss explanation."))
        elif isinstance(block, dict):
            phase = {"flight": "flight", "after_landing": "after landing", "both": "both"}.get(
                block.get("phase"), block.get("phase") or "—")
            evidence = [str(e) for e in block.get("evidence") or [] if e]
            named = _named_parts(attribution) or []
            if evidence:
                lines.append(("Evidence", " ".join(evidence)))
            elif named:
                lines.append(("Evidence", ", ".join(named) + "."))
            if block.get("possible_explanation"):
                lines.append(("Possible explanation", str(block["possible_explanation"])))
            if block.get("suggestion"):
                lines.append(("Look at", str(block["suggestion"])))
            if not lines and block.get("observed"):
                lines.append(("", str(block["observed"])))
        else:
            sentence = (th["explanation"] or {}).get("sentence")
            lines.append(("", sentence or "No explanation was saved for this throw."))
        rows.append({"number": th["number"], "label": th["label"], "result": label, "score": th["score"],
                     "short_long": short_long, "left_right": left_right, "phase": phase,
                     "estimated": status in ("estimated", "partial"), "lines": lines})
    return rows


MISS_COLUMNS = (("#", 0.0), ("Throw", 0.28), ("Result", 1.2), ("Short/long", 2.25), ("Left/right", 2.95),
                ("Phase", 3.65), ("Evidence · possible explanation · what to look at", 4.35))
TEXT_COL_CHARS = 60


def _cell_lines(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for head, body in row["lines"]:
        text = f"{head}: {body}" if head else body
        out += textwrap.wrap(text, TEXT_COL_CHARS) or [""]
    return out or ["—"]


def _miss_pages(data: dict[str, Any]) -> list[_Page]:
    rows = _miss_rows(data)
    pages: list[_Page] = []
    have_block = any(isinstance(th["attribution"], dict) and th["attribution"].get("explanation")
                     for th in data["throws"])
    available = PAGE_SIZE_IN[1] - 1.05 - 1.75
    chunks: list[list[tuple[dict[str, Any], list[str]]]] = [[]]
    used = 0.0
    for row in rows:
        cell = _cell_lines(row)
        h = max(len(cell), len(textwrap.wrap(row["label"], 16)), 1) * 0.125 + 0.1
        if used + h > available and chunks[-1]:
            chunks.append([]); used = 0.0
        chunks[-1].append((row, cell)); used += h
    for index, chunk in enumerate(chunks):
        title = "Miss explanations" + (f" (continued, {index + 1} of {len(chunks)})" if index else "")
        page = _Page(title, "Per throw, as the engine saved it (two_view.json): signed miss at rest from the hole "
                     "centre and the attribution's evidence and explanation. Nothing is recomputed here.", data)
        y = page.top + 0.15
        x = MARGIN_IN
        for head, cx in MISS_COLUMNS:
            page.text(x + cx, y, head, fontsize=7.6, weight="bold")
        y += 0.2
        page.fig.add_artist(_hline_at(page.fig, y - 0.05))
        for k, (row, cell) in enumerate(chunk):
            label_lines = textwrap.wrap(row["label"], 16) or [""]
            h = max(len(cell), len(label_lines), 1) * 0.125 + 0.1
            if k % 2 == 0:
                bax = page.axes(x - 0.05, y - 0.04, PAGE_SIZE_IN[0] - 2 * MARGIN_IN + 0.1, h)
                bax.set_axis_off()
                bax.add_patch(_plain_rect(0.955))
            ink = OUTCOME_STYLE.get(row["score"], OUTCOME_STYLE[None])
            page.text(x, y, str(row["number"]), fontsize=7.4)
            page.text(x + 0.28, y, "\n".join(label_lines), fontsize=7.4, linespacing=1.3)
            mark = page.axes(x + 1.2, y - 0.005, 0.12, 0.12)
            mark.set_axis_off(); mark.set_xlim(-1, 1); mark.set_ylim(-1, 1)
            mark.scatter([0], [0], marker=ink[2], s=22, c=[ink[1]], edgecolors="black", linewidths=0.4)
            page.text(x + 1.36, y, "\n".join(textwrap.wrap(row["result"], 14)), fontsize=7.2, linespacing=1.3)
            suffix = "\n(est.)" if row["estimated"] else ""
            page.text(x + 2.25, y, _signed_in(row["short_long"], "short", "long") + suffix, fontsize=7.4,
                      linespacing=1.3)
            page.text(x + 2.95, y, _signed_in(row["left_right"], "left", "right") + suffix, fontsize=7.4,
                      linespacing=1.3)
            page.text(x + 3.65, y, "\n".join(textwrap.wrap(row["phase"], 9)), fontsize=7.2, linespacing=1.3)
            page.text(x + 4.35, y, "\n".join(cell), fontsize=7.0, linespacing=1.3)
            y += h
        y += 0.12
        note = ("Short / long and left / right: where the bag stopped relative to the hole centre, thrower's frame; "
                "(est.) marks an estimated or partial position; — is not measured. Phase: the miss was made in the "
                "flight or after landing (the slide). One throw is an observation, not a cause. ")
        if not have_block:
            note += ("These throws were analysed before the miss attribution (two-camera method two_view_v6 or "
                     "later), so only the engine's one-sentence explanation is shown. Re-analyse to add the evidence.")
        else:
            note += ("Evidence names only parts at least twice their noise, 3 in and 40 % of that direction's miss "
                     "(docs/METRICS.md, Miss attribution).")
        page.paragraph(x, y, note, width_chars=125, size=7.2, color=MUTED_INK)
        pages.append(page)
    return pages


def _hline_at(fig, top_in: float):
    from matplotlib.lines import Line2D
    w, h = PAGE_SIZE_IN
    yy = 1 - top_in / h
    return Line2D([MARGIN_IN / w, 1 - MARGIN_IN / w], [yy, yy], transform=fig.transFigure, color="0.5", lw=0.6)


def _plain_rect(grey: float):
    from matplotlib.patches import Rectangle
    return Rectangle((0, 0), 1, 1, fc=(grey,) * 3, ec="none")


def _page_scored_vs_missed(data: dict[str, Any]) -> _Page:
    from .performance import MIN_CLAIM_PER_GROUP, minimum_claim_group
    perf = data["performance"]
    variables = perf["variables"]
    counts = perf["counts"]
    n_scored, n_miss = counts["hole"] + counts["board"], counts["miss"]
    needed = minimum_claim_group(2 * len(variables)) if variables else MIN_CLAIM_PER_GROUP
    page = _Page("Scored throws vs misses", "Within this athlete: scored (hole or board) against misses (off), "
                 "one pre-chosen list of release and body measures (performance.py).", data)
    y = page.top + 0.15
    message = (f"{n_scored} scored and {n_miss} missed throws with a recorded result. With {len(variables)} measures "
               f"checked (a shift and a spread test each), a difference can only be claimed from about {needed} "
               f"throws in each group, even if the two groups do not overlap at all.")
    if n_scored >= needed and n_miss >= needed:
        message += (" This athlete has enough throws in both groups for the engine's claim gate to pass when a "
                    "difference is large and above the noise floor.")
    else:
        message += " This athlete does not have that many yet, so nothing below is a finding."
    msg_lines = textwrap.wrap(message, 112)
    ax = page.axes(MARGIN_IN, y, PAGE_SIZE_IN[0] - 2 * MARGIN_IN, 0.16 * len(msg_lines) + 0.18)
    ax.set_axis_off()
    ax.add_patch(_box(ax, fc=(0.93, 0.96, 0.97), ec=ATHLETE_INK))
    ax.text(0.015, 0.5, "\n".join(msg_lines), transform=ax.transAxes, va="center", fontsize=8.0, linespacing=1.3)
    y += 0.16 * len(msg_lines) + 0.35

    keys = list(variables)
    row = 0.22
    plot_h = max(1.0, row * len(keys))
    label_w = 2.45
    dax = page.axes(MARGIN_IN + label_w, y + 0.25, 2.1, plot_h)
    dax.set_title("Cliff's δ, scored vs missed", loc="left", fontsize=8.5)
    for i, k in enumerate(keys):
        a = variables[k]
        dax.fill_betweenx([i - 0.4, i + 0.4], -a["critical_delta"], a["critical_delta"], color=NOISE_FILL, lw=0)
        delta, spread = a["cliffs_delta"], a.get("spread_cliffs_delta")
        if delta is None:
            dax.text(0, i, "too few throws", ha="center", va="center", fontsize=6.4, color=MUTED_INK,
                     bbox={"fc": NOISE_FILL, "ec": "none", "pad": 0.6}, zorder=4)
            continue
        dax.plot([delta], [i - 0.12], marker="o", color="black", ms=5,
                 mfc="black" if a["distinguishes"] else "white", mew=0.9, zorder=3)
        if spread is not None:
            dax.plot([spread], [i + 0.14], marker="s", color="0.25", ms=4.2,
                     mfc="0.25" if a.get("spread_distinguishes") else "white", mew=0.9, zorder=3)
    dax.axvline(0, color="0.4", lw=0.6)
    dax.set_xlim(-1.05, 1.05)
    dax.set_ylim(len(keys) - 0.5, -0.5)
    dax.set_yticks(range(len(keys)), ["" for _ in keys])
    dax.tick_params(axis="y", length=0)
    dax.set_xlabel("Cliff's δ (−1 … +1)")
    tx = MARGIN_IN + label_w + 2.3
    for cx, head in zip((0, 0.95, 1.9), ("Scored median (n)", "Missed median (n)", "Noise floor")):
        page.text(tx + cx, y + 0.08, head, fontsize=6.8, color=MUTED_INK)
    for i, k in enumerate(keys):
        a = variables[k]
        d = a["decimals"]
        yy = y + 0.25 + plot_h * (i + 0.5) / len(keys) - 0.065
        label = f"{a['label']} ({a['unit'] or 'ratio'})"
        page.text(MARGIN_IN, yy, label if len(label) <= 46 else label[:44].rstrip() + "…", fontsize=7.2)
        page.text(tx, yy, f"{_fmt(a['scored']['median'], d)} ({a['n_scored']})", fontsize=7.2)
        page.text(tx + 0.95, yy, f"{_fmt(a['miss']['median'], d)} ({a['n_miss']})", fontsize=7.2)
        floor = a["noise_floor"]
        page.text(tx + 1.9, yy, _fmt(floor, max(d, 1) + (1 if floor is not None and floor < 0.1 else 0)),
                  fontsize=7.2)
    if not keys:
        page.text(MARGIN_IN, y + 0.3, "No release or body measure was available on these throws.", fontsize=8.2)
    y += plot_h + 0.75
    y += page.paragraph(MARGIN_IN, y, "Circle: shift (+ = scored throws higher). Square: spread (+ = misses lie further "
                        "from this athlete's scored median, i.e. too high and too low both miss). Grey band: |δ| below "
                        "the chance level for this sample size (Bonferroni across all tests, never below 0.474). Filled: "
                        "the engine's claim gate passed (≥ 5 per group, |δ| above the band, difference above the noise "
                        "floor); hollow: shown, not a finding.", width_chars=132, size=7.0, color=MUTED_INK) + 0.12
    feedback = perf["feedback"]
    for head, body in (("What differed", feedback["why"]), ("Next practice", feedback["next"])):
        page.text(MARGIN_IN, y, head, fontsize=8.2, weight="bold")
        y += page.paragraph(MARGIN_IN + 1.15, y, body, width_chars=104, size=7.9) + 0.06

    # Limitations box at the foot of the last page.
    wrapped = [textwrap.wrap(t, 128) for t in LIMITATIONS]
    line = 7.4 * 1.3 / 72
    box_h = 0.38 + sum(line * len(w) + 0.04 for w in wrapped)
    top = max(y + 0.15, PAGE_SIZE_IN[1] - 0.7 - box_h)
    lax = page.axes(MARGIN_IN, top, PAGE_SIZE_IN[0] - 2 * MARGIN_IN, box_h)
    lax.set_axis_off()
    lax.add_patch(_box(lax, fc="0.97", ec="0.45"))
    page.text(MARGIN_IN + 0.12, top + 0.09, "Limitations", fontsize=9, weight="bold")
    yy = top + 0.3
    for lines in wrapped:
        page.text(MARGIN_IN + 0.15, yy, "•", fontsize=7.4)
        page.text(MARGIN_IN + 0.3, yy, "\n".join(lines), fontsize=7.4, linespacing=1.3)
        yy += line * len(lines) + 0.04
    return page


# ------------------------------------------------------------------------------------------------
# Entry point


def build_pages(data: dict[str, Any]) -> list[_Page]:
    return [_page_cover(data), _page_board(data), _page_release(data), _page_consistency(data),
            *_miss_pages(data), _page_scored_vs_missed(data)]


def athlete_report_pdf(library: str | Path, athlete_id: str, output: str | Path) -> dict[str, Any]:
    """Write the printable report for one athlete; returns a small summary for the CLI's JSON line."""
    import matplotlib
    from matplotlib.backends.backend_pdf import PdfPages
    data = collect(library, athlete_id)
    target = Path(output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    with matplotlib.rc_context(_style()):
        pages = build_pages(data)
        with PdfPages(partial, metadata={"Title": f"Athlete report · {data['athlete']}",
                                         "Author": "Cornhole Biomechanics Lab",
                                         "Subject": REPORT_VERSION,
                                         "CreationDate": datetime.now()}) as pdf:
            for number, page in enumerate(pages, 1):
                page.finish(number, len(pages))
                pdf.savefig(page.fig)
    partial.replace(target)
    return {"athlete_id": athlete_id, "athlete": data["athlete"], "output": str(target), "pages": len(pages),
            "throws": len(data["throws"]), "left_out": len(data["excluded"]),
            "method_versions": data["method_versions"], "report_version": REPORT_VERSION}
