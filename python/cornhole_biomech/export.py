"""Research-oriented CSV, plot, summary, and annotated-video exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import csv

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .serialization import json_ready


SKELETON_EDGES = (
    ("left_shoulder", "right_shoulder"),
    ("left_hip", "right_hip"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
)


def export_keypoints_csv(
    path: str | Path,
    times: np.ndarray,
    landmarks: tuple[str, ...],
    raw: np.ndarray,
    confidence: np.ndarray,
    effective: np.ndarray,
    filtered: np.ndarray,
    manual_mask: np.ndarray,
    interpolated_mask: np.ndarray,
) -> None:
    fields = ["frame", "time_seconds", "landmark", "raw_x_px", "raw_y_px", "confidence",
              "effective_x_px", "effective_y_px", "filtered_x_px", "filtered_y_px",
              "manually_corrected", "interpolated"]
    with Path(path).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for frame in range(len(times)):
            for j, name in enumerate(landmarks):
                writer.writerow({
                    "frame": frame,
                    "time_seconds": f"{times[frame]:.9g}",
                    "landmark": name,
                    "raw_x_px": _cell(raw[frame, j, 0]),
                    "raw_y_px": _cell(raw[frame, j, 1]),
                    "confidence": _cell(confidence[frame, j]),
                    "effective_x_px": _cell(effective[frame, j, 0]),
                    "effective_y_px": _cell(effective[frame, j, 1]),
                    "filtered_x_px": _cell(filtered[frame, j, 0]),
                    "filtered_y_px": _cell(filtered[frame, j, 1]),
                    "manually_corrected": str(bool(manual_mask[frame, j])).lower(),
                    "interpolated": str(bool(interpolated_mask[frame, j])).lower(),
                })


def _cell(value: float) -> str:
    return "" if not np.isfinite(value) else f"{float(value):.9g}"


def export_kinematics_csv(path: str | Path, times: np.ndarray, values: dict[str, np.ndarray]) -> None:
    scalar_fields = [name for name, value in values.items() if np.asarray(value).ndim == 1]
    vector_fields = [name for name, value in values.items() if np.asarray(value).ndim == 2]
    headers = ["frame", "time_seconds", *scalar_fields]
    for field in vector_fields:
        headers.extend((f"{field}_x", f"{field}_y"))
    with Path(path).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        for frame in range(len(times)):
            row: dict[str, Any] = {"frame": frame, "time_seconds": _cell(times[frame])}
            for field in scalar_fields:
                row[field] = _cell(values[field][frame])
            for field in vector_fields:
                row[f"{field}_x"] = _cell(values[field][frame, 0])
                row[f"{field}_y"] = _cell(values[field][frame, 1])
            writer.writerow(row)


def plot_angles_angles(path: str | Path, tau: np.ndarray, values: dict[str, np.ndarray], title: str) -> None:
    angle_fields = [name for name in values if name.endswith("_deg") and not name.endswith("velocity_deg")]
    fig, ax = plt.subplots(figsize=(9, 5.2), layout="constrained")
    for field in angle_fields:
        ax.plot(100 * tau, values[field], label=field.replace("_", " ").replace(" deg", ""))
    ax.set(title=title, xlabel="Movement cycle (%)", ylabel="Projected angle (degrees)")
    ax.grid(alpha=0.22)
    ax.legend(loc="best", fontsize=8)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_wrist_trajectory(path: str | Path, trajectory: np.ndarray, title: str) -> None:
    fig, ax = plt.subplots(figsize=(6.6, 5.2), layout="constrained")
    data = np.asarray(trajectory, float)
    valid = np.isfinite(data).all(axis=-1)
    if np.any(valid):
        ax.plot(data[valid, 0], data[valid, 1], color="#174A7E", linewidth=2)
        ax.scatter(data[valid, 0][0], data[valid, 1][0], label="Start", color="#8B1E2D", zorder=3)
        ax.scatter(data[valid, 0][-1], data[valid, 1][-1], label="End", color="#B8863B", zorder=3)
    ax.axhline(0, color="0.8", linewidth=0.8)
    ax.axvline(0, color="0.8", linewidth=0.8)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set(title=title, xlabel="Toward target (arm lengths)", ylabel="Up (arm lengths)")
    ax.grid(alpha=0.22)
    ax.legend(loc="best", fontsize=8)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_comparison(
    path: str | Path,
    tau: np.ndarray,
    test: np.ndarray,
    reference_mean: np.ndarray,
    reference_sd: np.ndarray,
    field_label: str,
    reference_n: int,
) -> None:
    fig, ax = plt.subplots(figsize=(9, 5.2), layout="constrained")
    x = 100 * tau
    ax.plot(x, reference_mean, label=f"Reference mean (n={reference_n})", color="#174A7E")
    if reference_n > 1:
        ax.fill_between(x, reference_mean - reference_sd, reference_mean + reference_sd,
                        color="#174A7E", alpha=0.16, label="Reference +/- 1 SD")
    ax.plot(x, test, label="Athlete trial", color="#8B1E2D")
    ax.set(title=f"Time-preserving comparison: {field_label}", xlabel="Movement cycle (%)",
           ylabel="Projected angle (degrees)")
    ax.grid(alpha=0.22)
    ax.legend(loc="best")
    fig.savefig(path, dpi=180)
    plt.close(fig)


def annotate_video(
    source_video: str | Path,
    output_path: str | Path,
    filtered: np.ndarray,
    confidence: np.ndarray,
    landmarks: tuple[str, ...],
    confidence_threshold: float,
    manually_corrected: np.ndarray,
) -> None:
    capture = cv2.VideoCapture(str(source_video))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("Could not create annotated MP4 with the available OpenCV codec")
    lookup = {name: index for index, name in enumerate(landmarks)}
    frame = 0
    try:
        while frame < len(filtered):
            ok, image = capture.read()
            if not ok:
                break
            for a_name, b_name in SKELETON_EDGES:
                if a_name not in lookup or b_name not in lookup:
                    continue
                a, b = filtered[frame, lookup[a_name]], filtered[frame, lookup[b_name]]
                if np.isfinite(a).all() and np.isfinite(b).all():
                    cv2.line(image, tuple(np.round(a).astype(int)), tuple(np.round(b).astype(int)), (232, 225, 208), 2, cv2.LINE_AA)
            for name, index in lookup.items():
                point = filtered[frame, index]
                if not np.isfinite(point).all():
                    continue
                corrected = bool(manually_corrected[frame, index])
                reliable = confidence[frame, index] >= confidence_threshold or corrected
                color = (38, 46, 139) if corrected else ((126, 74, 23) if reliable else (64, 64, 180))
                cv2.circle(image, tuple(np.round(point).astype(int)), 5, color, -1, cv2.LINE_AA)
            cv2.putText(image, f"Frame {frame}", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (245, 245, 245), 2, cv2.LINE_AA)
            writer.write(image)
            frame += 1
    finally:
        capture.release()
        writer.release()


def markdown_summary(results: dict[str, Any]) -> str:
    quality = results.get("quality", {})
    summaries = results.get("summaries", {})
    lines = [
        f"# Trial analysis: {results.get('trial_id', 'unknown')}",
        "",
        "This report describes projected 2D measurements, not true 3D anatomical rotations.",
        "",
        "## Measurement quality",
        "",
        f"- Usable frames: {quality.get('usable_frame_percentage', 'unavailable')}%",
        f"- Average model confidence: {quality.get('average_pose_confidence', 'unavailable')}",
        f"- Manual corrections: {quality.get('manual_correction_count', 0)}",
        f"- Missing landmark samples: {quality.get('missing_data_percentage', 'unavailable')}%",
        "",
        "## Kinematic summary",
        "",
    ]
    for name, value in sorted(summaries.items()):
        lines.append(f"- {name.replace('_', ' ')}: {value if value is not None else 'unavailable'}")
    warnings = quality.get("warnings", []) + results.get("warnings", [])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {item}" for item in warnings] or ["- No automatic warnings."])
    lines.extend(["", "Reference similarity, when present, is not a performance-quality claim.", ""])
    return "\n".join(lines)
