"""Which metrics a coach should see for this throw, and why others are hidden.

The engine computes >100 summary values (results.summaries, kept for research).
Coaches see only the curated `COACH_METRICS` below, each checked on every throw:

1. Visible: the defining landmarks have model confidence ≥ the configured threshold
   in every frame of the release window (release ± 2 frames).
2. In plane: for angles, each defining segment's projected length at the event is
   ≥ 70% of its median length in the clip. A shorter segment points toward the
   camera, and its 2D direction is dominated by noise (e.g. a 350° "forearm range").
3. Stable after filtering: the filtered landmark stays within 0.1 arm lengths of the
   raw one over the release window (a large difference means the filter is smoothing
   over a tracking error).
4. Physiologically plausible: velocities inside wide sanity bounds.
5. Release-timing sensitivity: for "at release" values, the change across the release
   window (the two release cues; see quality.py) is compared with the metric's noise
   floor. A value that depends on which frame is called release is marked CAUTION.
6. Interpretable: segment-orientation ranges and velocities are never shown to coaches.

Statuses: reliable · caution (shown with a note) · unreliable (value withheld:
"Insufficient tracking quality") · not_measured.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

IN_PLANE_FRACTION = 0.7
FILTER_DEVIATION_ARM_LENGTHS = 0.10
RELEASE_WINDOW = 2


@dataclass(frozen=True)
class CoachMetric:
    key: str
    label: str
    unit: str
    group: str             # Release · Hand & wrist · Arm · Trunk · Timing
    definition: str
    landmarks: tuple[str, ...] = ()   # "{side}" is replaced by the throwing side
    segments: tuple[tuple[str, str], ...] = ()
    event: str | None = "release"     # frame the value refers to (for seeking and checks)
    at_release: bool = False
    noise_floor: float | None = None
    plausible: tuple[float, float] | None = None
    source: str = "body"              # body · bag · derived
    modifiable: bool = True
    exploratory: bool = False


S = "{side}"
COACH_METRICS: tuple[CoachMetric, ...] = (
    CoachMetric("bag_release_speed_m_s", "Release speed", "m/s", "Release",
                "Bag speed at release from a gravity-constrained fit of the first ~0.12 s of flight.",
                source="bag", noise_floor=0.15),
    CoachMetric("bag_release_angle_deg", "Release angle", "°", "Release",
                "Bag launch direction above horizontal, from the same fit.", source="bag", noise_floor=3.0),
    CoachMetric("bag_release_height_m", "Release height", "m", "Release",
                "Bag centre above the lowest foot point at release.", source="bag", noise_floor=0.03,
                modifiable=True),
    CoachMetric("bag_release_position_forward_arm_lengths", "Release point", "arm lengths", "Release",
                "How far in front of the throwing shoulder the bag leaves the hand.", (f"{S}_shoulder",),
                source="bag", noise_floor=0.05),
    CoachMetric("wrist_speed_at_release_arm_lengths_s", "Wrist speed at release", "arm lengths/s", "Hand & wrist",
                "Speed of the throwing wrist at release (camera motion removed).", (f"{S}_wrist",),
                at_release=True, noise_floor=0.3, plausible=(0.0, 30.0)),
    CoachMetric("wrist_peak_speed_arm_lengths_s", "Peak wrist speed", "arm lengths/s", "Hand & wrist",
                "Fastest wrist speed between the top of the backswing and just after release.", (f"{S}_wrist",),
                event="peak_wrist_speed", noise_floor=0.3, plausible=(0.0, 30.0)),
    CoachMetric("wrist_peak_speed_time_rel_release_ms", "Peak wrist speed timing", "ms", "Timing",
                "When the wrist was fastest, relative to release (negative = before release).", (f"{S}_wrist",),
                event="peak_wrist_speed", noise_floor=35.0, plausible=(-600.0, 150.0)),
    CoachMetric("wrist_direction_at_release_deg", "Hand direction at release", "°", "Hand & wrist",
                "Direction the wrist was moving at release, degrees above horizontal.", (f"{S}_wrist",),
                at_release=True, noise_floor=5.0, plausible=(-90.0, 120.0)),
    CoachMetric("swing_release_arm_angle_deg", "Arm angle at release", "°", "Arm",
                "Shoulder-to-wrist line from straight down (0°) toward the board (90°).",
                (f"{S}_shoulder", f"{S}_wrist"), ((f"{S}_shoulder", f"{S}_wrist"),), at_release=True, noise_floor=5.0),
    CoachMetric("swing_backswing_angle_deg", "Backswing", "°", "Arm",
                "Arm angle at the top of the backswing (negative = behind the body).",
                (f"{S}_shoulder", f"{S}_wrist"), ((f"{S}_shoulder", f"{S}_wrist"),), event="peak_backswing",
                noise_floor=5.0, plausible=(-170.0, 10.0)),
    CoachMetric("elbow_angle_deg_at_release", "Elbow angle at release", "°", "Arm",
                "2D projected shoulder–elbow–wrist angle; 180° = straight as seen by the camera.",
                (f"{S}_shoulder", f"{S}_elbow", f"{S}_wrist"),
                ((f"{S}_shoulder", f"{S}_elbow"), (f"{S}_elbow", f"{S}_wrist")), at_release=True, noise_floor=10.0),
    CoachMetric("elbow_peak_extension_velocity_deg_s", "Peak elbow extension speed", "°/s", "Arm",
                "Fastest straightening of the 2D elbow angle in the forward swing.",
                (f"{S}_shoulder", f"{S}_elbow", f"{S}_wrist"),
                ((f"{S}_shoulder", f"{S}_elbow"), (f"{S}_elbow", f"{S}_wrist")), event="peak_elbow_extension",
                noise_floor=150.0, plausible=(0.0, 2500.0), exploratory=True),
    CoachMetric("elbow_peak_extension_time_rel_release_ms", "Elbow extension timing", "ms", "Timing",
                "When the elbow straightened fastest, relative to release.",
                (f"{S}_shoulder", f"{S}_elbow", f"{S}_wrist"),
                ((f"{S}_shoulder", f"{S}_elbow"), (f"{S}_elbow", f"{S}_wrist")), event="peak_elbow_extension",
                noise_floor=50.0, plausible=(-600.0, 150.0), exploratory=True),
    CoachMetric("swing_forward_duration_s", "Forward swing time", "s", "Timing",
                "Top of the backswing to release.", (f"{S}_wrist",), event="peak_backswing", noise_floor=0.035,
                plausible=(0.15, 1.5)),
    CoachMetric("swing_tempo_ratio", "Tempo", "back ÷ forward", "Timing",
                "Backswing time divided by forward-swing time.", (f"{S}_wrist",), event="peak_backswing",
                noise_floor=0.15, plausible=(0.3, 4.0)),
    CoachMetric("trunk_inclination_deg_at_release", "Trunk lean at release", "°", "Trunk",
                "Hip-midpoint to shoulder-midpoint line from vertical; positive = toward the board.",
                ("left_shoulder", "right_shoulder", "left_hip", "right_hip"),
                (("left_hip", "left_shoulder"), ("right_hip", "right_shoulder")), at_release=True, noise_floor=5.0),
)
BY_KEY = {m.key: m for m in COACH_METRICS}
# Summaries that must never be shown to coaches: 2D segment directions are undefined when
# the segment points at the camera, so their ranges and velocities can be absurd.
NEVER_FOR_COACHING_PREFIXES = ("upper_arm_orientation_", "forearm_orientation_", "arm_to_trunk_velocity_")


def _segment_ratio(filtered: np.ndarray, lookup: dict[str, int], a: str, b: str, frame: int) -> float | None:
    if a not in lookup or b not in lookup:
        return None
    lengths = np.linalg.norm(filtered[:, lookup[a]] - filtered[:, lookup[b]], axis=1)
    median = float(np.nanmedian(lengths)) if np.isfinite(lengths).any() else float("nan")
    if not (0 <= frame < len(lengths)) or not math.isfinite(lengths[frame]) or not median > 0:
        return None
    return float(lengths[frame] / median)


def assess_metrics(values: dict[str, float | None], raw: np.ndarray, confidence: np.ndarray, filtered: np.ndarray,
                   landmarks: tuple[str, ...], side: str, event_frames: dict[str, int | None],
                   confidence_threshold: float, arm_length_px: float,
                   release_window: tuple[int, int] | None = None,
                   at_other_release: dict[str, float | None] | None = None,
                   bag_grade: str | None = None, release_grade: str | None = None,
                   calibration_grade: str | None = None) -> dict[str, Any]:
    """Per coach metric: value (withheld when unreliable), status, reasons, event frame and definition."""
    lookup = {name: i for i, name in enumerate(landmarks)}
    out: dict[str, Any] = {}
    for metric in COACH_METRICS:
        value = values.get(metric.key)
        frame = event_frames.get(metric.event) if metric.event else None
        row: dict[str, Any] = {"label": metric.label, "unit": metric.unit, "group": metric.group,
                               "definition": metric.definition, "event": metric.event, "frame": frame,
                               "noise_floor": metric.noise_floor, "exploratory": metric.exploratory,
                               "status": "not_measured", "reasons": [], "value": None}
        if value is None or not math.isfinite(value):
            row["reasons"].append("Not measured for this throw.")
            out[metric.key] = row
            continue
        problems, cautions = [], []
        names = [n.replace(S, side) for n in metric.landmarks]
        if metric.source == "bag":
            if bag_grade == "POOR":
                problems.append("Bag tracking is POOR for this throw.")
            if release_grade == "POOR":
                problems.append("Release could not be confirmed.")
            if metric.unit == "m/s" or metric.unit == "m":
                if calibration_grade == "POOR":
                    problems.append("No physical scale.")
                elif calibration_grade == "WARNING":
                    cautions.append("Metres come from a single scale source (see calibration).")
        if frame is not None and names:
            window = range(max(0, frame - RELEASE_WINDOW), min(len(confidence), frame + RELEASE_WINDOW + 1))
            low = [n for n in names if n in lookup
                   and any(not (np.isfinite(confidence[f, lookup[n]]) and confidence[f, lookup[n]] >= confidence_threshold)
                           for f in window)]
            if low:
                problems.append("Low pose confidence near the event: " + ", ".join(n.replace("_", " ") for n in low) + ".")
            deviations = [float(np.linalg.norm(raw[f, lookup[n]] - filtered[f, lookup[n]])) / arm_length_px
                          for n in names if n in lookup for f in window
                          if np.isfinite(raw[f, lookup[n]]).all() and np.isfinite(filtered[f, lookup[n]]).all()]
            if deviations and max(deviations) > FILTER_DEVIATION_ARM_LENGTHS:
                problems.append("Filtered and raw landmarks disagree near the event (possible tracking error).")
            for a, b in metric.segments:
                ratio = _segment_ratio(filtered, lookup, a.replace(S, side), b.replace(S, side), frame)
                if ratio is not None and ratio < IN_PLANE_FRACTION:
                    problems.append(f"{a.replace(S, side).replace('_', ' ')}–{b.replace(S, side).replace('_', ' ')} "
                                    f"segment is foreshortened ({ratio:.0%} of its usual length): out of the camera plane.")
        if metric.plausible and not metric.plausible[0] <= value <= metric.plausible[1]:
            problems.append("Value outside the physiologically plausible range.")
        if metric.at_release and at_other_release and release_window and release_window[0] != release_window[1]:
            other = at_other_release.get(metric.key)
            if other is not None and metric.noise_floor and abs(other - value) > metric.noise_floor:
                cautions.append(f"Depends on the exact release frame: changes by {abs(other - value):.1f} {metric.unit} "
                                f"across the release window (frames {release_window[0]}–{release_window[1]}).")
        if metric.exploratory:
            cautions.append("Exploratory: a derivative of a 2D angle, sensitive to landmark noise.")
        if problems:
            row.update(status="unreliable", reasons=problems + cautions)
        else:
            row.update(status="caution" if cautions else "reliable", reasons=cautions, value=float(value))
        out[metric.key] = row
    return out


def hidden_for_coaching(summary_key: str) -> bool:
    return summary_key.startswith(NEVER_FOR_COACHING_PREFIXES)
