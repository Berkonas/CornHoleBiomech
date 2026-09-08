"""Offline pose backends with a canonical, confidence-preserving output schema."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Callable
import importlib.metadata
import json

import cv2
import numpy as np

from .models import PointEstimate, PoseFrame, PoseSequence
from .video import VideoMetadata, file_sha256

Progress = Callable[[str, float, str], None]

HALPE26_NAMES = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip", "left_knee",
    "right_knee", "left_ankle", "right_ankle", "head", "neck", "hip_center",
    "left_big_toe", "right_big_toe", "left_small_toe", "right_small_toe",
    "left_heel", "right_heel",
)

COCO17_NAMES = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip", "left_knee",
    "right_knee", "left_ankle", "right_ankle",
)

MEDIAPIPE33_NAMES = (
    "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner",
    "right_eye", "right_eye_outer", "left_ear", "right_ear", "mouth_left",
    "mouth_right", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky", "left_index",
    "right_index", "left_thumb", "right_thumb", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle", "left_heel",
    "right_heel", "left_foot_index", "right_foot_index",
)


def _version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _choose_person(
    keypoints: np.ndarray, scores: np.ndarray, previous_center: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Choose one participant by confidence initially, then nearest tracked center."""
    if keypoints.size == 0 or len(keypoints) == 0:
        return np.empty((0, 2)), np.empty((0,)), previous_center
    points = np.asarray(keypoints, float)
    conf = np.asarray(scores, float)
    if points.ndim == 2:
        points, conf = points[None, ...], conf[None, ...]
    centers = np.nanmedian(points, axis=1)
    if previous_center is None or not np.isfinite(previous_center).all():
        index = int(np.nanargmax(np.nanmean(conf, axis=1)))
    else:
        distance = np.linalg.norm(centers - previous_center, axis=1)
        quality_penalty = 50.0 * (1.0 - np.nanmean(conf, axis=1))
        index = int(np.nanargmin(distance + quality_penalty))
    return points[index], conf[index], centers[index]


def analyze_rtmpose(
    video: VideoMetadata,
    progress: Progress,
    model_mode: str = "balanced",
    device: str = "cpu",
) -> PoseSequence:
    """Run RTMPose through RTMLib, preserving raw pixel points and scores."""
    try:
        from rtmlib import BodyWithFeet, PoseTracker
    except ImportError as error:
        raise RuntimeError(
            "RTMPose backend is not installed. Run ./setup.sh or install cornhole-biomech[pose]."
        ) from error
    try:
        tracker = PoseTracker(
            BodyWithFeet,
            det_frequency=1,
            mode=model_mode,
            backend="onnxruntime",
            device=device,
        )
    except TypeError:
        tracker = PoseTracker(BodyWithFeet, det_frequency=1, mode=model_mode, backend="onnxruntime")
    pose_model_path = Path(getattr(tracker.pose_model, "onnx_model", ""))
    detector_model_path = Path(getattr(tracker.det_model, "onnx_model", ""))
    capture = cv2.VideoCapture(video.path)
    frames: list[PoseFrame] = []
    previous_center: np.ndarray | None = None
    try:
        for frame_index in range(video.frame_count):
            ok, image = capture.read()
            if not ok:
                break
            keypoints, scores = tracker(image)
            points, confidence, previous_center = _choose_person(keypoints, scores, previous_center)
            landmarks: dict[str, PointEstimate] = {}
            for index, name in enumerate(HALPE26_NAMES):
                if index < len(points) and index < len(confidence) and np.isfinite(points[index]).all():
                    landmarks[name] = PointEstimate(
                        x=float(points[index, 0]),
                        y=float(points[index, 1]),
                        confidence=float(np.clip(confidence[index], 0.0, 1.0)),
                    )
                else:
                    landmarks[name] = PointEstimate(None, None, 0.0)
            frames.append(PoseFrame(frame_index, frame_index / video.fps, landmarks))
            if frame_index % max(1, video.frame_count // 100) == 0:
                progress("detecting_pose", frame_index / video.frame_count, "Running RTMPose locally")
    finally:
        capture.release()
    if not frames:
        raise RuntimeError("Pose analysis produced no readable video frames")
    return PoseSequence(
        schema_version=1,
        fps=video.fps,
        width=video.width,
        height=video.height,
        frame_count=len(frames),
        backend="rtmpose_rtmlib",
        model_name=f"BodyWithFeet-{model_mode}",
        model_version=_version("rtmlib"),
        model_sha256=file_sha256(pose_model_path) if pose_model_path.is_file() else None,
        backend_metadata={
            "runtime": "onnxruntime",
            "device": device,
            "pose_model_file": pose_model_path.name if pose_model_path.name else None,
            "detector_model_file": detector_model_path.name if detector_model_path.name else None,
            "detector_model_sha256": file_sha256(detector_model_path) if detector_model_path.is_file() else None,
        },
        frames=frames,
    )


def _mediapipe_legacy(video: VideoMetadata, progress: Progress) -> PoseSequence:
    import mediapipe as mp

    pose_namespace = getattr(getattr(mp, "solutions", None), "pose", None)
    if pose_namespace is None:
        raise RuntimeError("Installed MediaPipe does not expose the legacy Pose API")
    capture = cv2.VideoCapture(video.path)
    frames: list[PoseFrame] = []
    with pose_namespace.Pose(
        static_image_mode=False,
        model_complexity=2,
        smooth_landmarks=False,
        min_detection_confidence=0.35,
        min_tracking_confidence=0.35,
    ) as detector:
        try:
            for frame_index in range(video.frame_count):
                ok, image = capture.read()
                if not ok:
                    break
                result = detector.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
                landmarks: dict[str, PointEstimate] = {}
                detected = result.pose_landmarks.landmark if result.pose_landmarks else []
                for index, name in enumerate(MEDIAPIPE33_NAMES):
                    if index < len(detected):
                        item = detected[index]
                        confidence = float(min(getattr(item, "visibility", 0.0), getattr(item, "presence", 1.0)))
                        landmarks[name] = PointEstimate(
                            x=float(item.x * video.width),
                            y=float(item.y * video.height),
                            confidence=float(np.clip(confidence, 0.0, 1.0)),
                        )
                    else:
                        landmarks[name] = PointEstimate(None, None, 0.0)
                frames.append(PoseFrame(frame_index, frame_index / video.fps, landmarks))
                if frame_index % max(1, video.frame_count // 100) == 0:
                    progress("detecting_pose", frame_index / video.frame_count, "Running MediaPipe locally")
        finally:
            capture.release()
    if not frames:
        raise RuntimeError("Pose analysis produced no readable video frames")
    return PoseSequence(
        schema_version=1,
        fps=video.fps,
        width=video.width,
        height=video.height,
        frame_count=len(frames),
        backend="mediapipe",
        model_name="BlazePose-heavy-legacy",
        model_version=_version("mediapipe"),
        frames=frames,
    )


def analyze_mediapipe(video: VideoMetadata, progress: Progress) -> PoseSequence:
    """Run the local MediaPipe fallback and retain per-landmark visibility."""
    try:
        import mediapipe as mp
        if hasattr(mp, "solutions"):
            return _mediapipe_legacy(video, progress)
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        model_path = Path(
            __import__("os").environ.get(
                "CORNHOLE_MEDIAPIPE_MODEL",
                str(Path(__file__).resolve().parents[2] / "models" / "pose_landmarker_heavy.task"),
            )
        )
        if not model_path.is_file():
            raise RuntimeError(
                f"MediaPipe model is missing at {model_path}. Run ./setup.sh or set CORNHOLE_MEDIAPIPE_MODEL."
            )
        options = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=str(model_path), delegate=mp_python.BaseOptions.Delegate.CPU
            ),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.35,
            min_pose_presence_confidence=0.35,
            min_tracking_confidence=0.35,
            output_segmentation_masks=False,
        )
        capture = cv2.VideoCapture(video.path)
        frames: list[PoseFrame] = []
        with vision.PoseLandmarker.create_from_options(options) as detector:
            try:
                for frame_index in range(video.frame_count):
                    ok, image = capture.read()
                    if not ok:
                        break
                    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    result = detector.detect_for_video(mp_image, int(round(1000 * frame_index / video.fps)))
                    detected = result.pose_landmarks[0] if result.pose_landmarks else []
                    landmarks: dict[str, PointEstimate] = {}
                    for index, name in enumerate(MEDIAPIPE33_NAMES):
                        if index < len(detected):
                            item = detected[index]
                            confidence = float(min(getattr(item, "visibility", 0.0), getattr(item, "presence", 1.0)))
                            landmarks[name] = PointEstimate(
                                x=float(item.x * video.width), y=float(item.y * video.height),
                                confidence=float(np.clip(confidence, 0.0, 1.0)),
                            )
                        else:
                            landmarks[name] = PointEstimate(None, None, 0.0)
                    frames.append(PoseFrame(frame_index, frame_index / video.fps, landmarks))
                    if frame_index % max(1, video.frame_count // 100) == 0:
                        progress("detecting_pose", frame_index / video.frame_count, "Running MediaPipe locally")
            finally:
                capture.release()
        if not frames:
            raise RuntimeError("Pose analysis produced no readable video frames")
        return PoseSequence(
            schema_version=1, fps=video.fps, width=video.width, height=video.height,
            frame_count=len(frames), backend="mediapipe", model_name=model_path.name,
            model_version=_version("mediapipe"), model_sha256=file_sha256(model_path),
            backend_metadata={
                "running_mode": "VIDEO", "delegate": "CPU",
                "coordinates": "normalized_image_converted_to_pixels",
            },
            frames=frames,
        )
    except ImportError as error:
        raise RuntimeError(
            "MediaPipe backend is not installed. Run ./setup.sh or install cornhole-biomech[pose]."
        ) from error


def analyze_pose(
    video: VideoMetadata,
    backend: str,
    progress: Progress,
    pose_input: str | Path | None = None,
    device: str = "cpu",
) -> PoseSequence:
    """Dispatch a local backend or import a previously generated raw pose file."""
    if pose_input is not None:
        imported = PoseSequence.load(pose_input)
        if abs(imported.fps - video.fps) > 1e-3:
            raise ValueError("Imported pose FPS does not match source video FPS")
        if (imported.width, imported.height, imported.frame_count) != (video.width, video.height, video.frame_count):
            raise ValueError("Imported pose dimensions/frame count do not match the source video")
        if [f.frame_index for f in imported.frames] != list(range(video.frame_count)):
            raise ValueError("Imported pose frames must be consecutive, starting at zero")
        return imported
    if backend == "rtmpose":
        return analyze_rtmpose(video, progress, device=device)
    if backend == "mediapipe":
        return analyze_mediapipe(video, progress)
    raise ValueError(f"Unknown pose backend: {backend}")


def pose_sequence_to_jsonable(sequence: PoseSequence) -> dict[str, object]:
    return asdict(sequence)


def model_file_hash(path: str | Path | None) -> str | None:
    return file_sha256(path) if path is not None and Path(path).is_file() else None
