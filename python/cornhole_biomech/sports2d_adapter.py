"""Versioned Sports2D public-API adapter; no console scraping or upstream edits.

0.8.34 writes processed TRC/MOT but does not export raw confidence. A narrowly
version-locked return-frame observer copies its tracked, pre-interpolation
arrays. It never changes upstream locals/code, and is removed in finally.
See docs/SPORTS2D.md for the contract and its limitations.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
import importlib.metadata
import importlib.util
import json
import os
import ssl
import sys

import numpy as np

from .models import PointEstimate, PoseFrame, PoseSequence, utc_now
from .serialization import write_json
from .video import VideoMetadata, file_sha256

PINNED_VERSION = "0.8.34"
NAME_MAP = {f"{side}{joint}": f"{long}_{joint.lower()}"
            for side, long in (("L", "left"), ("R", "right"))
            for joint in ("Shoulder", "Elbow", "Wrist", "Hip", "Knee", "Ankle")}


def availability() -> dict[str, Any]:
    try:
        version = importlib.metadata.version("sports2d")
    except importlib.metadata.PackageNotFoundError:
        return {"available": False, "version": None, "supported": False,
                "message": "Sports2D is not installed. Run scripts/setup.sh, or select RTMPose in Advanced Analysis."}
    return {"available": importlib.util.find_spec("Sports2D") is not None,
            "version": version, "supported": version == PINNED_VERSION,
            "message": f"Sports2D {version}"}


def build_config(video: str | Path, output: str | Path, settings: dict[str, Any],
                 device: str = "cpu", defaults: dict | None = None) -> dict[str, Any]:
    """Explicit 2D settings; no assumed body height, floor, camera or depth."""
    cfg = deepcopy(defaults or {})
    engine = settings.get("sports2d", {})
    model = engine.get("pose_model", "body_with_feet")
    if model not in {"body_with_feet", "whole_body", "whole_body_wrist", "body"}:
        raise ValueError("Unsupported Sports2D pose model for upper-body analysis")
    if device != "cpu":
        raise ValueError("This validated adapter uses CPU. MPS/CoreML requires a separate equivalence check.")
    updates = {
        "base": {"video_input": [str(Path(video).resolve())], "video_dir": "",
                 "result_dir": str(Path(output).resolve()), "nb_persons_to_detect": 1,
                 "person_ordering_method": engine.get("person_ordering_method", "highest_likelihood"),
                 "visible_side": ["none"], "time_range": [], "load_trc_px": "",
                 "show_realtime_results": False, "save_vid": True, "save_img": False,
                 "save_pose": True, "calculate_angles": True, "save_angles": True},
        "pose": {"pose_model": model, "mode": engine.get("mode", "balanced"),
                 "device": "cpu", "backend": "onnxruntime", "det_frequency": 1,
                 "tracking_mode": "sports2d", "keypoint_likelihood_threshold": 0.0,
                 "average_likelihood_threshold": 0.0, "keypoint_number_threshold": 0.0},
        "px_to_meters_conversion": {"to_meters": False, "make_c3d": False, "save_calib": False,
                                   "floor_angle": 0.0, "xy_origin": [0.0, 0.0], "calib_file": ""},
        "angles": {"joint_angles": ["Right elbow", "Left elbow", "Right shoulder", "Left shoulder"],
                   "segment_angles": ["Right arm", "Left arm", "Right forearm", "Left forearm", "Trunk"],
                   "flip_left_right": False, "correct_segment_angles_with_floor_angle": False},
        "post-processing": {"interpolate": True,
                            "interp_gap_smaller_than": int(settings["max_interpolation_gap_frames"]),
                            "fill_large_gaps_with": "nan", "sections_to_keep": "all", "min_chunk_size": 3,
                            "reject_outliers": False, "filter": settings["filter"]["enabled"],
                            "filter_type": engine.get("export_filter", "butterworth"),
                            "butterworth": {"order": settings["filter"]["order"],
                                            "cut_off_frequency": settings["filter"]["cutoff_hz"]},
                            "show_graphs": False, "save_graphs": False},
        "kinematics": {"do_augmentation": False, "do_ik": False},
        "logging": {"use_custom_logging": False},
    }
    for key, value in updates.items():
        cfg.setdefault(key, {}).update(value)
    return cfg


def read_trc(path: str | Path) -> dict[str, Any]:
    """Read TRC without interpreting its units as physical scale automatically."""
    lines = Path(path).read_text().splitlines()
    header_index = next((i for i, line in enumerate(lines) if line.startswith("Frame#")), None)
    if header_index is None or header_index < 2:
        raise ValueError("TRC has no Frame#/Time header")
    header = lines[header_index].split("\t")
    markers = [name.strip() for name in header[2::3] if name.strip()]
    data = []
    for line in lines[header_index + 2:]:
        if not line.strip():
            continue
        fields = line.split("\t")
        try:
            row = [float(v) if v.strip() else float("nan") for v in fields[:2 + 3*len(markers)]]
        except ValueError as error:
            raise ValueError("TRC contains a non-numeric sample") from error
        if len(row) != 2 + 3*len(markers):
            raise ValueError("TRC sample width does not match marker header")
        data.append(row)
    if not data:
        raise ValueError("TRC contains no samples")
    array = np.asarray(data)
    metadata = dict(zip(lines[header_index-2].split(), lines[header_index-1].split()))
    return {"frames": array[:, 0], "time": array[:, 1], "markers": markers,
            "coordinates": array[:, 2:].reshape(len(array), len(markers), 3),
            "units": metadata.get("Units", "unknown"), "metadata": metadata}


def correct_pixel_trc_units(path: str | Path) -> dict[str, Any] | None:
    """Repair the pinned upstream writer's hardcoded m header for pixel exports.

    Coordinates are untouched; preserve original bytes alongside the export.
    Only call when the configuration explicitly disables metric conversion.
    """
    path = Path(path)
    original = path.read_bytes()
    lines = original.decode().splitlines(keepends=True)
    header = next((i for i, line in enumerate(lines) if line.startswith("DataRate")), None)
    if header is None or header+1 >= len(lines):
        raise ValueError("TRC is missing unit metadata")
    columns = lines[header].strip().split("\t")
    values = lines[header+1].strip().split("\t")
    index = columns.index("Units")
    previous = values[index]
    if previous == "px": return None
    archive = path.with_suffix(".trc.original")
    archive.write_bytes(original)
    values[index] = "px"
    lines[header+1] = "\t".join(values) + "\n"
    path.write_text("".join(lines))
    return {"file":path.name,"original":archive.name,"original_header_units":previous,
            "corrected_units":"px","coordinates_changed":False,
            "original_sha256":file_sha256(archive),"corrected_sha256":file_sha256(path)}


def read_mot(path: str | Path) -> dict[str, np.ndarray]:
    lines = Path(path).read_text().splitlines()
    end = next((i for i, line in enumerate(lines) if line.strip().lower() == "endheader"), None)
    if end is None:
        raise ValueError("MOT has no endheader marker")
    rows = [line for line in lines[end+1:] if line.strip()]
    if len(rows) < 2:
        raise ValueError("MOT contains no samples")
    columns = rows[0].split("\t") if "\t" in rows[0] else rows[0].split()
    parsed = [[float(v) for v in line.split()] for line in rows[1:]]
    if any(len(r) > len(columns) for r in parsed):
        raise ValueError("MOT sample width exceeds its header")
    # Sports2D can omit trailing values when angles are unavailable: pad as missing.
    data = np.asarray([r + [np.nan] * (len(columns) - len(r)) for r in parsed])
    return dict(zip(columns, data.T))


def elbow_included_from_sports2d(flexion: np.ndarray | float) -> np.ndarray:
    """Sports2D's signed flexion -> unsigned included angle (straight = 180°)."""
    return 180.0 - np.abs((np.asarray(flexion, float) + 180.0) % 360.0 - 180.0)


class Sports2DAdapter:
    def analyze(self, video: VideoMetadata, output: Path, settings: dict[str, Any],
                progress: Callable, device: str = "cpu") -> PoseSequence:
        info = availability()
        if not info["available"] or not info["supported"]:
            raise RuntimeError(info["message"] + f" The adapter requires Sports2D {PINNED_VERSION}.")
        output.mkdir(parents=True, exist_ok=True)
        # Sports2D changes the global SSL context at import. Restore verified TLS
        # immediately; model downloads must never inherit that upstream override.
        verified_context = ssl._create_default_https_context
        import matplotlib
        from unittest.mock import patch
        matplotlib.use("Agg", force=True)
        real_use = matplotlib.use
        try:
            with redirect_stdout(sys.stderr), patch.object(matplotlib, "use", side_effect=lambda *a, **k: real_use("Agg", force=True)):
                from Sports2D import Sports2D
                import Sports2D.process as engine
        finally:
            ssl._create_default_https_context = verified_context
        import matplotlib
        matplotlib.use("Agg", force=True)
        cfg = build_config(video.path, output, settings, device, Sports2D.DEFAULT_CONFIG)
        write_json(output / "configuration.json", cfg)
        snapshot = {}
        target = engine.process_fun.__code__
        old_profile = sys.getprofile()
        def capture(frame, event, arg):
            if event == "return" and frame.f_code is target:
                fields = ("all_frames_X_homog", "all_frames_Y_homog", "all_frames_scores_homog",
                          "new_keypoints_names", "selected_persons", "pose_tracker")
                for key in fields:
                    value = frame.f_locals.get(key)
                    snapshot[key] = value.copy() if isinstance(value, np.ndarray) else value
        progress("detecting_pose", 0.03, "Sports2D is tracking the athlete locally; first use may download pose models")
        try:
            sys.setprofile(capture)
            with redirect_stdout(sys.stderr):
                Sports2D.process(deepcopy(cfg))
        except Exception as error:
            raise RuntimeError(f"Sports2D could not finish this video: {error}. Check the recording and engine log, or select RTMPose in Advanced Analysis.") from error
        finally:
            sys.setprofile(old_profile)
            ssl._create_default_https_context = verified_context
        selected = snapshot.get("selected_persons")
        if selected is None or not len(selected):
            raise RuntimeError("Sports2D did not find a trackable person. Use a clear recording with the full throwing arm visible.")
        person = int(selected[0])
        names = snapshot.get("new_keypoints_names")
        try:
            x = np.asarray(snapshot["all_frames_X_homog"], float)[:, person, :]
            y = np.asarray(snapshot["all_frames_Y_homog"], float)[:, person, :]
            conf = np.asarray(snapshot["all_frames_scores_homog"], float)[:, person, :]
        except (IndexError, TypeError, KeyError) as error:
            raise RuntimeError("Sports2D raw-confidence export contract changed; analysis stopped without substituting confidence.") from error
        frames = []
        for i in range(len(x)):
            landmarks = {}
            for j, name in enumerate(names):
                key = NAME_MAP.get(name, name)
                present = np.isfinite([x[i,j], y[i,j], conf[i,j]]).all()
                landmarks[key] = PointEstimate(float(x[i,j]) if present else None,
                                               float(y[i,j]) if present else None,
                                               float(np.clip(conf[i,j], 0, 1)) if present else 0.0)
            frames.append(PoseFrame(i, i/video.fps, landmarks))
        files = sorted(p for p in output.rglob('*') if p.is_file())
        trcs = [p for p in files if p.suffix == '.trc']
        mots = [p for p in files if p.suffix == '.mot']
        if not trcs or not mots:
            raise RuntimeError("Sports2D did not create the expected TRC and MOT files. Review sports2d/logs.txt before retrying.")
        unit_repairs = []
        for trc in trcs:
            repair = correct_pixel_trc_units(trc)
            if repair: unit_repairs.append(repair)
            read_trc(trc)
        diagnostic_warnings = []
        for mot in mots:
            try:
                read_mot(mot)   # diagnostic export only; our angles come from the landmarks
            except ValueError as error:
                diagnostic_warnings.append(f"{mot.name}: {error}")
        model_files = {}
        tracker = snapshot.get("pose_tracker")
        for component in ("pose_model", "det_model"):
            model = getattr(tracker, component, None)
            filename = getattr(model, "onnx_model", None)
            if isinstance(filename, (str, Path)) and Path(filename).is_file():
                model_files[component] = {"name": Path(filename).name, "sha256": file_sha256(filename)}
        metadata = {"sports2d_version": info["version"], "sports2d_commit": None,
                    "diagnostic_export_warnings": diagnostic_warnings,
                    "sports2d_source_sha256": file_sha256(engine.__file__),
                    "pose2sim_version": importlib.metadata.version("pose2sim"),
                    "rtmlib_version": importlib.metadata.version("rtmlib"),
                    "configuration": cfg, "model_files": model_files, "device": device,
                    "analyzed_at": utc_now(), "selected_person_index": person,
                    "raw_contract": "Sports2D tracked pre-interpolation pixels/confidence; upstream detection and person rejection still apply",
                    "confidence_threshold": settings["confidence_threshold"],
                    "calibration": "uncalibrated_image_plane; metric scale, C3D and IK disabled",
                    "trc_unit_repairs": unit_repairs,
                    "export_notes": "TRC coordinates are uncalibrated pixels (zero Z), not meters. Original upstream headers are preserved as .trc.original. Use the cornhole annotated.mp4 for frame-complete overlays; the upstream diagnostic video can omit the last frame.",
                    "outputs": [str(p.relative_to(output)) for p in output.rglob('*') if p.is_file()]}
        write_json(output / "provenance.json", metadata)
        return PoseSequence(1, video.fps, video.width, video.height, len(frames), "sports2d",
                            f"{cfg['pose']['pose_model']}-{cfg['pose']['mode']}",
                            info["version"], frames, model_files.get("pose_model", {}).get("sha256"), metadata)
