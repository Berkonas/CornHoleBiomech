"""Two-camera takes: pair the side and front recordings, synchronise them, split a take into throws.

A *take* (round) is one continuous recording per camera: the athlete claps and shows the round
number with their fingers, then throws several bags (four in the Fall 2026 protocol). Each take
has a side-camera file (release physics, body chain) and a front-camera file (the camera behind
the board looking back at the athlete: left/right, landing spot, frontal-plane body).

Method (docs/METHODS_AND_MATH.md §5.1, "Takes, synchronisation and throws"):

1. **Pairing** — file names are matched case-insensitively (``Take_2_side.mov`` = ``take_2_Side.MOV``).
2. **Camera roles** — each file's camera signature (QuickTime device model, frame size, nominal
   frame rate) is read; within one athlete's folder the signature most "Front"-named files share is
   the front camera. A file whose signature belongs to the other camera is reported as *swapped* and
   used in its true role (the file itself is never renamed).
3. **Synchronisation** — both phones record sound. The clap and every bag impact are sharp
   transients heard by both. Each soundtrack is high-passed (300 Hz), turned into a 5 ms loudness
   envelope (dB), detrended with a 1 s running median, and the two envelopes are cross-correlated
   over ±12 s. The lag with the highest normalised correlation is the offset; it is accepted when
   the peak correlation r ≥ 0.35 and it beats every other lag (outside ±100 ms) by ≥ 0.08.
   On the 23 Final Data Collection pairs r was 0.44–0.74 and the margin 0.10–0.35.
   Sound travels ~3 ms per metre, so the two microphones' different distances to the clap or the
   board add up to ±15 ms; with half the 5 ms envelope hop the stated uncertainty is ±17.5 ms.
4. **Throws** — the side video is streamed once at 480 px width. Three-frame differencing finds
   small moving blobs; blobs are linked frame to frame into tracklets; a tracklet that moves
   towards the board for ≥ 8 frames is part of a bag flight; tracklets that chain within 0.25 s
   form one flight. A flight must cross ≥ 35 % of the frame width. Each flight is one throw.
   Bag impacts in the front camera's soundtrack (it sits beside the board) confirm each flight.
5. **Clips** — each throw becomes a side clip from 2.5 s before the flight starts to 1.6 s after
   it ends, and the matching front clip over the same synchronised time span. The full-length
   originals are untouched; clips are encoded at high quality and their frame mapping is stored.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import struct
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np

TAKE_PATTERN = re.compile(r"take[\s_\-]*(\d+)[\s_\-]*(front|side)\b", re.IGNORECASE)
VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v"}

AUDIO_RATE_HZ = 16000
ENVELOPE_HOP_S = 0.005
HIGHPASS_HZ = 300.0
DETREND_WINDOW_S = 1.0
MAX_SYNC_LAG_S = 12.0
MIN_SYNC_OVERLAP_S = 8.0
MIN_SYNC_R = 0.35
MIN_SYNC_MARGIN = 0.08
SYNC_EXCLUSION_S = 0.10
SOUND_PATH_UNCERTAINTY_S = 0.015

SCAN_WIDTH_PX = 480
DIFF_THRESHOLD = 14
BLOB_AREA_RANGE = (4, 400)
LINK_GATE_PX = 7.0
LINK_MAX_MISSED = 3
MIN_TRACKLET_POINTS = 8
TRACKLET_SPEED_RANGE_PX = (1.5, 20.0)     # per frame at 480 px, towards the board
CHAIN_GAP_S = 0.25
CAMERA_MOTION_MIN_BLOBS = 15         # median blobs per frame over a "flight" that means the camera itself moved
CAMERA_MOTION_FACTOR = 4.0           # ... and at least this many times the take's typical frame
MIN_FLIGHT_SPAN_FRACTION = 0.35
MIN_THROW_SEPARATION_S = 2.0
CLIP_BEFORE_S = 2.5
CLIP_AFTER_S = 1.6
THUD_MATCH_WINDOW_S = 0.45

Progress = Callable[[str, float, str], None]


def _no_progress(stage: str, fraction: float, message: str) -> None:
    return None


# ---------------------------------------------------------------------------------------------
# 1. Pairing


@dataclass
class TakeFiles:
    take: int
    front: str | None = None
    side: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_take_name(name: str) -> tuple[int, str] | None:
    """(take number, 'front' | 'side') from a file name, ignoring case and separators."""
    match = TAKE_PATTERN.search(Path(name).stem)
    if not match:
        return None
    return int(match.group(1)), match.group(2).lower()


def discover_takes(folder: str | Path) -> list[TakeFiles]:
    """Pair every ``Take_<n>_<Front|Side>`` video in a folder (any capitalisation)."""
    root = Path(folder).expanduser()
    takes: dict[int, TakeFiles] = {}
    for path in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file() or path.suffix.lower() not in VIDEO_SUFFIXES or path.name.startswith("."):
            continue
        parsed = parse_take_name(path.name)
        if parsed is None:
            continue
        number, role = parsed
        entry = takes.setdefault(number, TakeFiles(take=number))
        if getattr(entry, role) is not None:
            entry.notes.append(f"Two {role} files for take {number}; kept {Path(getattr(entry, role)).name}, "
                               f"ignored {path.name}.")
            continue
        setattr(entry, role, str(path))
    for entry in takes.values():
        for role in ("front", "side"):
            if getattr(entry, role) is None:
                entry.notes.append(f"Take {entry.take} has no {role} video.")
    return [takes[k] for k in sorted(takes)]


# ---------------------------------------------------------------------------------------------
# 2. Camera roles


def _atoms(f, start: int, end: int):
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        header = f.read(8)
        if len(header) < 8:
            return
        size, kind = struct.unpack(">I4s", header)
        header_len = 8
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
            header_len = 16
        elif size == 0:
            size = end - pos
        if size < header_len:
            return
        yield kind.decode("latin1"), pos + header_len, pos + size
        pos += size


def quicktime_metadata(path: str | Path) -> dict[str, str]:
    """QuickTime ``moov/meta`` key → text value (device model, creation date, …). Empty if absent.

    Only keys and ilst text items are read; location tags are returned too, so callers must pick the
    keys they need (the engine keeps model and creation date only — never location).
    """
    out: dict[str, str] = {}
    path = Path(path)
    try:
        end = path.stat().st_size
        with path.open("rb") as f:
            for kind, start, stop in _atoms(f, 0, end):
                if kind != "moov":
                    continue
                for kind2, start2, stop2 in _atoms(f, start, stop):
                    if kind2 != "meta":
                        continue
                    keys: list[str] = []
                    items: dict[int, str] = {}
                    for kind3, start3, stop3 in _atoms(f, start2, stop2):
                        if kind3 == "keys":
                            f.seek(start3 + 4)
                            count = struct.unpack(">I", f.read(4))[0]
                            position = start3 + 8
                            for _ in range(min(count, 512)):
                                f.seek(position)
                                key_size, _namespace = struct.unpack(">I4s", f.read(8))
                                if key_size < 8:
                                    break
                                keys.append(f.read(key_size - 8).decode("utf-8", "replace"))
                                position += key_size
                        elif kind3 == "ilst":
                            for kind4, start4, stop4 in _atoms(f, start3, stop3):
                                index = struct.unpack(">I", kind4.encode("latin1"))[0]
                                for kind5, start5, stop5 in _atoms(f, start4, stop4):
                                    if kind5 != "data":
                                        continue
                                    f.seek(start5)
                                    value_type = struct.unpack(">I", f.read(4))[0]
                                    f.read(4)
                                    raw = f.read(max(0, stop5 - start5 - 8))
                                    if value_type == 1:
                                        items[index] = raw.decode("utf-8", "replace")
                    for i, key in enumerate(keys, 1):
                        if i in items:
                            out[key] = items[i]
    except (OSError, struct.error):
        return {}
    return out


@dataclass
class CameraSignature:
    model: str | None
    width: int
    height: int
    fps: float
    duration_s: float
    frame_count: int
    created: str | None

    @property
    def key(self) -> str:
        return f"{self.model or 'unknown'}|{self.width}x{self.height}|{round(self.fps)}"


def camera_signature(path: str | Path) -> CameraSignature:
    import cv2
    meta = quicktime_metadata(path)
    capture = cv2.VideoCapture(str(path))
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS)) or 0.0
        width = int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
        height = int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        frames = int(round(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    finally:
        capture.release()
    return CameraSignature(model=meta.get("com.apple.quicktime.model"), width=width, height=height,
                           fps=nominal_fps(fps), duration_s=frames / fps if fps else 0.0, frame_count=frames,
                           created=meta.get("com.apple.quicktime.creationdate"))


def nominal_fps(measured: float) -> float:
    """Snap a container's average rate to the nearest nominal rate when it is within 0.06 %.

    A variable-rate iPhone clip reports 59.96 for 59.94; a true 30 fps clip must stay 30 (29.97 is 0.1 %
    away, which would shift a frame index by one over 33 s).
    """
    nominals = (23.976, 24.0, 25.0, 29.97, 30.0, 47.952, 48.0, 50.0, 59.94, 60.0, 119.88, 120.0, 239.76, 240.0)
    closest = min(nominals, key=lambda n: abs(measured - n))
    return closest if abs(measured - closest) / closest < 0.0006 else measured


def assign_camera_roles(takes: list[TakeFiles], signatures: dict[str, CameraSignature]) -> dict[str, Any]:
    """Decide which camera is the front and which the side, and fix swapped file labels.

    Majority vote: the signature that most "front"-labelled files share is the front camera, the one
    most "side"-labelled files share is the side camera. Returns the role summary; ``takes`` are
    corrected in place and each correction is noted on the take.
    """
    from collections import Counter
    front_votes = Counter(signatures[t.front].key for t in takes if t.front and t.front in signatures)
    side_votes = Counter(signatures[t.side].key for t in takes if t.side and t.side in signatures)
    front_key = front_votes.most_common(1)[0][0] if front_votes else None
    side_key = side_votes.most_common(1)[0][0] if side_votes else None
    summary: dict[str, Any] = {"front_signature": front_key, "side_signature": side_key, "swapped_takes": [],
                               "status": "measured", "reason": None}
    if front_key is None or side_key is None or front_key == side_key:
        summary["status"] = "unavailable"
        summary["reason"] = ("Both cameras have the same device model, size and frame rate, so the file names "
                             "are trusted as given.") if front_key == side_key and front_key else \
            "Not enough labelled files to tell the cameras apart; file names are trusted as given."
        return summary
    for take in takes:
        if not take.front or not take.side:
            continue
        f_key, s_key = signatures[take.front].key, signatures[take.side].key
        if f_key == side_key and s_key == front_key:
            take.front, take.side = take.side, take.front
            take.notes.append(f"Take {take.take}: the files labelled Front and Side were recorded by the other "
                              "camera (device, size and frame rate); they are used in their true roles.")
            summary["swapped_takes"].append(take.take)
        elif f_key != front_key or s_key != side_key:
            take.notes.append(f"Take {take.take}: a file's camera does not match the rest of the session "
                              f"(front {f_key}, side {s_key}); labels kept as given.")
    return summary


# ---------------------------------------------------------------------------------------------
# 3. Audio and synchronisation


def load_audio(path: str | Path, rate: int = AUDIO_RATE_HZ) -> np.ndarray:
    """Mono float audio at ``rate`` Hz from a video's first audio track.

    Tries PyAV (bundled with the app's runtime), then an ``ffmpeg`` executable, then macOS ``afconvert``.
    """
    errors: list[str] = []
    try:
        return _audio_pyav(path, rate)
    except Exception as error:  # noqa: BLE001 - try the next decoder
        errors.append(f"PyAV: {error}")
    for tool in (_audio_ffmpeg, _audio_afconvert):
        try:
            return tool(path, rate)
        except Exception as error:  # noqa: BLE001
            errors.append(f"{tool.__name__}: {error}")
    raise RuntimeError("Could not read the soundtrack (" + "; ".join(errors) + ")")


def _audio_pyav(path: str | Path, rate: int) -> np.ndarray:
    import av  # type: ignore
    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise ValueError("no audio track")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
        chunks: list[np.ndarray] = []
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        raise ValueError("empty audio track")
    return np.concatenate(chunks).astype(np.float64) / 32768.0


def _read_wav(path: Path) -> np.ndarray:
    from scipy.io import wavfile
    sr, data = wavfile.read(str(path))
    data = data.astype(np.float64)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data / 32768.0


def _audio_ffmpeg(path: str | Path, rate: int) -> np.ndarray:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise FileNotFoundError("ffmpeg not installed")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "a.wav"
        subprocess.run([binary, "-v", "error", "-y", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", str(rate),
                        "-c:a", "pcm_s16le", str(out)], check=True, capture_output=True, timeout=120)
        return _read_wav(out)


def _audio_afconvert(path: str | Path, rate: int) -> np.ndarray:
    binary = shutil.which("afconvert")
    if not binary:
        raise FileNotFoundError("afconvert not available")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "a.wav"
        subprocess.run([binary, "-f", "WAVE", "-d", f"LEI16@{rate}", "-c", "1", str(path), str(out)],
                       check=True, capture_output=True, timeout=120)
        return _read_wav(out)


def loudness_envelope(audio: np.ndarray, rate: int = AUDIO_RATE_HZ, hop_s: float = ENVELOPE_HOP_S) -> np.ndarray:
    """5 ms RMS loudness (dB) of the 300 Hz high-passed signal: transients, not hum or speech fundamentals."""
    from scipy import signal
    if len(audio) < rate // 2:
        raise ValueError("soundtrack shorter than half a second")
    b, a = signal.butter(4, HIGHPASS_HZ / (rate / 2), "high")
    filtered = signal.filtfilt(b, a, audio)
    hop = max(1, int(round(rate * hop_s)))
    n = len(filtered) // hop
    rms = np.sqrt(np.mean(filtered[: n * hop].reshape(n, hop) ** 2, axis=1))
    return 20.0 * np.log10(rms + 1e-9)


def detrended(envelope: np.ndarray, hop_s: float = ENVELOPE_HOP_S) -> np.ndarray:
    from scipy.ndimage import median_filter
    window = max(3, int(round(DETREND_WINDOW_S / hop_s)) | 1)
    return envelope - median_filter(envelope, size=window, mode="nearest")


def sync_offset(front_envelope: np.ndarray, side_envelope: np.ndarray, hop_s: float = ENVELOPE_HOP_S,
                max_lag_s: float = MAX_SYNC_LAG_S, coarse_guess_s: float | None = None) -> dict[str, Any]:
    """Offset (s) such that a sound at side time t is heard at front time t + offset.

    ``coarse_guess_s`` (from the files' creation times) only narrows the search when it is given.
    """
    a = detrended(front_envelope, hop_s)
    b = detrended(side_envelope, hop_s)
    max_lag = int(round(max_lag_s / hop_s))
    centre = 0
    if coarse_guess_s is not None and abs(coarse_guess_s) < 60:
        centre = int(round(coarse_guess_s / hop_s))
    lags = np.arange(centre - max_lag, centre + max_lag + 1)
    r = np.full(len(lags), -1.0)
    # Evaluate on a decimated grid first (25 ms), then refine around the best few candidates.
    min_overlap = int(round(MIN_SYNC_OVERLAP_S / hop_s))
    coarse_step = 5
    coarse_idx = np.arange(0, len(lags), coarse_step)
    for i in coarse_idx:
        r[i] = _single_lag(a, b, int(lags[i]), min_overlap)
    for i in np.argsort(r)[::-1][:6]:
        for j in range(max(0, i - coarse_step), min(len(lags), i + coarse_step + 1)):
            if r[j] == -1.0:
                r[j] = _single_lag(a, b, int(lags[j]), min_overlap)
    best = int(np.argmax(r))
    best_r = float(r[best])
    exclusion = int(round(SYNC_EXCLUSION_S / hop_s))
    others = r.copy()
    others[max(0, best - exclusion): best + exclusion + 1] = -1.0
    # Competing peaks are only meaningful where they were evaluated; refine the strongest competitor.
    second = int(np.argmax(others))
    for j in range(max(0, second - coarse_step), min(len(lags), second + coarse_step + 1)):
        if abs(j - best) > exclusion and others[j] == -1.0:
            others[j] = _single_lag(a, b, int(lags[j]), min_overlap)
    second_r = float(others.max())
    # Parabolic interpolation around the peak for sub-hop precision.
    offset_hops = float(lags[best])
    if 0 < best < len(r) - 1 and r[best - 1] > -1 and r[best + 1] > -1:
        y0, y1, y2 = r[best - 1], r[best], r[best + 1]
        denom = y0 - 2 * y1 + y2
        if denom < 0:
            offset_hops += 0.5 * (y0 - y2) / denom
    offset = offset_hops * hop_s
    margin = best_r - second_r
    accepted = best_r >= MIN_SYNC_R and margin >= MIN_SYNC_MARGIN
    return {
        "status": "measured" if accepted else "unavailable",
        "offset_s": offset if accepted else None,
        "candidate_offset_s": offset,
        "correlation": best_r,
        "margin": margin,
        "uncertainty_s": SOUND_PATH_UNCERTAINTY_S + hop_s / 2,
        "convention": "front_time = side_time + offset_s",
        "reason": None if accepted else
        f"The two soundtracks did not line up clearly (r = {best_r:.2f}, margin {margin:.2f}; needs r ≥ "
        f"{MIN_SYNC_R} and margin ≥ {MIN_SYNC_MARGIN}). The views are analysed separately and combined per throw.",
        "method": "Cross-correlation of 300 Hz high-passed 5 ms loudness envelopes (clap and bag impacts).",
    }


def _single_lag(a: np.ndarray, b: np.ndarray, lag: int, min_overlap: int) -> float:
    if lag >= 0:
        x, y = a[lag:], b
    else:
        x, y = a, b[-lag:]
    n = min(len(x), len(y))
    if n < min_overlap:
        return -1.0
    x = x[:n] - x[:n].mean()
    y = y[:n] - y[:n].mean()
    denom = math.sqrt(float(np.dot(x, x)) * float(np.dot(y, y)))
    return float(np.dot(x, y)) / denom if denom > 0 else -1.0


def impact_times(envelope: np.ndarray, hop_s: float = ENVELOPE_HOP_S, rise_db: float = 15.0) -> list[dict[str, float]]:
    """Sharp sound events (bag impacts, the clap): peaks ≥ ``rise_db`` above the median level."""
    from scipy import signal
    background = float(np.median(envelope))
    peaks, props = signal.find_peaks(envelope, height=background + rise_db, distance=int(0.15 / hop_s), prominence=10)
    return [{"time_s": float(p * hop_s), "level_db": float(envelope[p] - background)} for p in peaks]


# ---------------------------------------------------------------------------------------------
# 4. Throws from the side view


@dataclass
class Tracklet:
    frames: list[int]
    xs: list[float]
    ys: list[float]
    areas: list[float]

    @property
    def start(self) -> int:
        return self.frames[0]

    @property
    def end(self) -> int:
        return self.frames[-1]


def scan_motion_blobs(video_path: str | Path, width: int = SCAN_WIDTH_PX, progress: Progress = _no_progress
                      ) -> dict[str, Any]:
    """Stream the video once; return small moving blobs per frame (480 px working width) and timestamps."""
    import cv2
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open {video_path}")
    fps = nominal_fps(float(capture.get(cv2.CAP_PROP_FPS)))
    source_width = float(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    scale = width / source_width
    blobs: list[tuple[int, float, float, float]] = []
    times: list[float] = []
    prev2 = prev = None
    index = -1
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            index += 1
            pos = capture.get(cv2.CAP_PROP_POS_MSEC)
            times.append(pos / 1000.0 if pos and pos > 0 else index / fps)
            small = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (3, 3), 0).astype(np.int16)
            if prev2 is not None:
                diff = np.minimum(np.abs(prev - prev2), np.abs(gray - prev)).astype(np.uint8)
                mask = (diff > DIFF_THRESHOLD).astype(np.uint8)
                count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
                for k in range(1, count):
                    area = int(stats[k, cv2.CC_STAT_AREA])
                    if BLOB_AREA_RANGE[0] <= area <= BLOB_AREA_RANGE[1]:
                        blobs.append((index - 1, float(centroids[k][0]), float(centroids[k][1]), float(area)))
            prev2, prev = prev, gray
            if index % 120 == 0:
                progress("finding_throws", min(0.99, index / total), f"Looking for bag flights ({index}/{total} frames)")
    finally:
        capture.release()
    # Container timestamps can repeat for the first frames; keep them monotone.
    t = np.maximum.accumulate(np.asarray(times, float)) if times else np.zeros(0)
    return {"blobs": blobs, "fps": fps, "frame_count": index + 1, "scale": scale,
            "width_px": width, "times_s": t.tolist()}


def link_tracklets(blobs: Sequence[tuple[int, float, float, float]], direction: int) -> list[Tracklet]:
    """Greedy nearest-neighbour linking with a constant-velocity prediction."""
    by_frame: dict[int, list[tuple[int, float, float, float]]] = {}
    for blob in blobs:
        by_frame.setdefault(int(blob[0]), []).append(blob)
    if not by_frame:
        return []
    active: list[dict[str, Any]] = []
    finished: list[dict[str, Any]] = []
    for f in range(min(by_frame), max(by_frame) + 1):
        candidates = by_frame.get(f, [])
        used: set[int] = set()
        for track in active:
            pts = track["pts"]
            if len(pts) >= 2:
                (f1, x1, y1, _), (f0, x0, y0, _) = pts[-1], pts[-2]
                vx, vy = (x1 - x0) / (f1 - f0), (y1 - y0) / (f1 - f0)
                px, py, gate = x1 + vx * (f - f1), y1 + vy * (f - f1), LINK_GATE_PX
            else:
                f1, x1, y1, _ = pts[-1]
                px, py, gate = x1 + direction * 6 * (f - f1), y1, LINK_GATE_PX * 1.8
            best = None
            for j, c in enumerate(candidates):
                if j in used:
                    continue
                d = math.hypot(c[1] - px, c[2] - py)
                if d < gate and (best is None or d < best[0]):
                    best = (d, j)
            if best is not None:
                used.add(best[1])
                pts.append(candidates[best[1]])
                track["miss"] = 0
            else:
                track["miss"] += 1
        survivors = []
        for track in active:
            (finished if track["miss"] > LINK_MAX_MISSED else survivors).append(track)
        active = survivors
        for j, c in enumerate(candidates):
            if j not in used:
                active.append({"pts": [c], "miss": 0})
    finished.extend(active)
    out = []
    for track in finished:
        pts = track["pts"]
        if len(pts) < MIN_TRACKLET_POINTS:
            continue
        out.append(Tracklet(frames=[int(p[0]) for p in pts], xs=[p[1] for p in pts], ys=[p[2] for p in pts],
                            areas=[p[3] for p in pts]))
    return out


def _moves_to_board(track: Tracklet, direction: int) -> bool:
    t = np.asarray(track.frames, float) - track.frames[0]
    if np.ptp(t) <= 0:
        return False
    vx = float(np.polyfit(t, np.asarray(track.xs), 1)[0])
    return TRACKLET_SPEED_RANGE_PX[0] <= direction * vx <= TRACKLET_SPEED_RANGE_PX[1]


def find_flights(scan: dict[str, Any], target_direction: str) -> list[dict[str, Any]]:
    """Group tracklets moving towards the board into bag flights (one per throw)."""
    direction = 1 if target_direction == "left_to_right" else -1
    fps = float(scan["fps"])
    width = float(scan["width_px"])
    tracks = [t for t in link_tracklets(scan["blobs"], direction) if _moves_to_board(t, direction)]
    tracks.sort(key=lambda t: t.start)
    gap = int(round(CHAIN_GAP_S * fps))
    groups: list[list[Tracklet]] = []
    for track in tracks:
        if groups and track.start <= max(t.end for t in groups[-1]) + gap:
            groups[-1].append(track)
        else:
            groups.append([track])
    # Small moving blobs per frame: a moving camera (bumped or picked up) lights up the whole picture.
    frames_n = int(scan.get("frame_count") or (max((int(b[0]) for b in scan["blobs"]), default=0) + 1))
    counts = np.bincount(np.asarray([int(b[0]) for b in scan["blobs"]], int), minlength=frames_n) \
        if scan["blobs"] else np.zeros(frames_n, int)
    busy_limit = max(CAMERA_MOTION_MIN_BLOBS, CAMERA_MOTION_FACTOR * float(np.median(counts)) if len(counts) else 0.0)
    flights = []
    for group in groups:
        xs = np.concatenate([np.asarray(t.xs) for t in group])
        span = float(xs.max() - xs.min())
        if span < MIN_FLIGHT_SPAN_FRACTION * width:
            continue
        start = min(t.start for t in group)
        end = max(t.end for t in group)
        if len(counts) and float(np.median(counts[start:end + 1])) >= busy_limit:
            continue                       # the camera moved: not a bag flight
        # The leading edge of the flight: the first frame of the tracklet that starts nearest the athlete.
        lead = min(group, key=lambda t: direction * t.xs[0])
        flights.append({"start_frame": int(start), "end_frame": int(end), "x_span_fraction": span / width,
                        "launch_frame": int(lead.start), "tracklets": len(group),
                        "points": int(sum(len(t.frames) for t in group))})
    return flights


def segment_throws(flights: list[dict[str, Any]], times_s: Sequence[float], fps: float,
                   front_impacts_side_time: list[dict[str, float]] | None = None,
                   expected: int | None = None) -> dict[str, Any]:
    """Turn flights into throws, merging flights closer than 2 s and checking them against impact sounds."""
    def t_of(frame: int) -> float:
        return float(times_s[min(max(frame, 0), len(times_s) - 1)]) if len(times_s) else frame / fps
    def heard_landing(flight: dict[str, Any]) -> bool:
        if not front_impacts_side_time:
            return False
        a, b = t_of(flight["launch_frame"]) + 0.15, t_of(flight["end_frame"]) + THUD_MATCH_WINDOW_S
        return any(a <= e["time_s"] <= b for e in front_impacts_side_time)

    merged: list[dict[str, Any]] = []
    for flight in sorted(flights, key=lambda f: f["start_frame"]):
        # A flight already heard landing is finished: a later flight is a new event, however close.
        if merged and t_of(flight["start_frame"]) - t_of(merged[-1]["end_frame"]) < MIN_THROW_SEPARATION_S \
                and not heard_landing(merged[-1]):
            last = merged[-1]
            last["end_frame"] = max(last["end_frame"], flight["end_frame"])
            last["start_frame"] = min(last["start_frame"], flight["start_frame"])
            last["launch_frame"] = min(last["launch_frame"], flight["launch_frame"])
            last["tracklets"] += flight["tracklets"]
            last["points"] += flight["points"]
            last["x_span_fraction"] = max(last["x_span_fraction"], flight["x_span_fraction"])
            continue
        merged.append(dict(flight))
    throws = []
    for number, flight in enumerate(merged, 1):
        start_t, end_t = t_of(flight["launch_frame"]), t_of(flight["end_frame"])
        impact = None
        if front_impacts_side_time:
            near = [e for e in front_impacts_side_time if start_t + 0.15 <= e["time_s"] <= end_t + THUD_MATCH_WINDOW_S]
            impact = max(near, key=lambda e: e["level_db"]) if near else None
        throws.append({"number": number, "flight_start_s": start_t, "flight_end_s": end_t,
                       "flight_start_frame": flight["launch_frame"], "flight_end_frame": flight["end_frame"],
                       "x_span_fraction": round(flight["x_span_fraction"], 3),
                       "impact_heard": impact is not None,
                       "impact_time_s": impact["time_s"] if impact else None})
    notes = []
    if expected and front_impacts_side_time is not None and len(throws) > expected:
        # More flights than throws: drop flights no impact was heard for, latest first, while enough heard ones
        # remain. Final Data Collection: the extra "flights" were the phone being picked up at the end of a take
        # (whole picture moving), never heard at the board.
        heard = sum(1 for t in throws if t["impact_heard"])
        while len(throws) > expected and heard >= expected:
            silent = [t for t in throws if not t["impact_heard"]]
            if not silent:
                break
            dropped = silent[-1]
            throws.remove(dropped)
            notes.append(f"A movement at {dropped['flight_start_s']:.1f} s looked like a bag flight but no landing was "
                         "heard at the board; it was left out.")
        for number, throw in enumerate(throws, 1):
            throw["number"] = number
    if expected and len(throws) != expected:
        notes.append(f"Found {len(throws)} bag flights; this take was expected to have {expected} throws. "
                     "Check the take: a throw may have left the side camera's view or two throws were too close.")
    unheard = [t["number"] for t in throws if front_impacts_side_time is not None and not t["impact_heard"]]
    if unheard:
        notes.append("No impact sound near the board for throw(s) " + ", ".join(map(str, unheard))
                     + " (a soft landing or a miss far from the board camera).")
    return {"throws": throws, "notes": notes}


# ---------------------------------------------------------------------------------------------
# 5. Clips


class _ClipWriter:
    """One output clip. ``kind`` is a PyAV codec name or an OpenCV fourcc (``cv2:avc1``)."""

    def __init__(self, output: Path, kind: str, fps: float, size: tuple[int, int]):
        self.output, self.kind, self.fps, self.size, self.count = output, kind, fps, size, 0
        if kind.startswith("cv2:"):
            import cv2
            self.writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*kind[4:]), fps, size)
            if not self.writer.isOpened():
                raise RuntimeError(f"OpenCV cannot write {kind[4:]}")
            self.container = None
        else:
            import av  # type: ignore
            from fractions import Fraction
            options, bit_rate = PYAV_CODECS[kind]
            self.container = av.open(str(output), "w")
            try:
                self.stream = self.container.add_stream(kind, rate=Fraction(fps).limit_denominator(1001), options=options)
                self.stream.width, self.stream.height = size
                self.stream.pix_fmt = "yuv420p"
                if bit_rate:
                    self.stream.bit_rate = int(bit_rate * (size[0] * size[1]) / (1920 * 1080))
            except Exception:
                self.container.close()
                raise
            self.writer = None

    def write(self, frame: np.ndarray) -> None:
        if self.writer is not None:
            self.writer.write(frame)
        else:
            import av  # type: ignore
            for packet in self.stream.encode(av.VideoFrame.from_ndarray(frame, format="bgr24")):
                self.container.mux(packet)
        self.count += 1

    def close(self) -> None:
        if self.writer is not None:
            self.writer.release()
        else:
            for packet in self.stream.encode():
                self.container.mux(packet)
            self.container.close()


# Best first. CRF 12 / 40 Mb/s at 1080p keep the bag's edges intact for tracking.
PYAV_CODECS: dict[str, tuple[dict[str, str], int | None]] = {
    "libx264": ({"crf": "12", "preset": "medium"}, None),
    "h264_videotoolbox": ({}, 40_000_000),
    "hevc_videotoolbox": ({}, 30_000_000),
}
CLIP_ENCODERS = ("libx264", "h264_videotoolbox", "hevc_videotoolbox", "cv2:avc1", "cv2:mp4v")
_encoder_cache: dict[tuple[int, int], str] = {}


def choose_encoder(fps: float, size: tuple[int, int]) -> str:
    """First encoder in ``CLIP_ENCODERS`` that writes a test clip OpenCV can read back frame-exact."""
    import cv2
    if size in _encoder_cache:
        return _encoder_cache[size]
    errors = []
    with tempfile.TemporaryDirectory() as tmp:
        for kind in CLIP_ENCODERS:
            path = Path(tmp) / f"probe_{kind.replace(':', '_')}.mp4"
            try:
                writer = _ClipWriter(path, kind, fps, size)
                rng = np.random.default_rng(0)
                for i in range(12):
                    frame = np.full((size[1], size[0], 3), 40 + 10 * i, np.uint8)
                    frame[::7, ::5] = rng.integers(0, 255, frame[::7, ::5].shape, dtype=np.uint8)
                    writer.write(frame)
                writer.close()
                check = cv2.VideoCapture(str(path))
                frames = 0
                while check.read()[0]:
                    frames += 1
                check.release()
                if frames == 12:
                    _encoder_cache[size] = kind
                    return kind
                errors.append(f"{kind}: read back {frames}/12 frames")
            except Exception as error:  # noqa: BLE001 - try the next encoder
                errors.append(f"{kind}: {error}")
    raise RuntimeError("No video encoder works in this runtime: " + "; ".join(errors))


def write_clips(source: str | Path, windows: Sequence[tuple[int, int, Path]], fps: float | None = None,
                progress: Progress = _no_progress) -> list[dict[str, Any]]:
    """Copy frames [start, end) of ``source`` into one new clip per window, decoding the source once.

    Decoding starts at frame 0 (seeking compressed video can land on a keyframe). Audio is omitted.
    Every clip is re-opened afterwards and its frames counted.
    """
    import cv2
    source = Path(source)
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError(f"Could not open {source}")
    src_fps = nominal_fps(float(capture.get(cv2.CAP_PROP_FPS)))
    size = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    fps = fps or src_fps
    kind = choose_encoder(fps, size)
    pending = sorted(((int(s), int(e), Path(o)) for s, e, o in windows), key=lambda w: w[0])
    for _, _, out in pending:
        if out.exists():
            raise ValueError(f"{out.name} already exists; clips are never overwritten.")
        out.parent.mkdir(parents=True, exist_ok=True)
    open_writers: dict[Path, _ClipWriter] = {}
    done: dict[Path, int] = {}
    last = max((e for _, e, _ in pending), default=0)
    index = 0
    try:
        while index < last:
            ok, frame = capture.read()
            if not ok:
                break
            for start, end, out in pending:
                if start <= index < end:
                    if out not in open_writers:
                        open_writers[out] = _ClipWriter(out.with_name(f".{out.stem}.partial{out.suffix}"), kind, fps, size)
                    open_writers[out].write(frame)
                elif index == end and out in open_writers:
                    open_writers[out].close()
                    done[out] = open_writers.pop(out).count
            if index % 120 == 0:
                progress("cutting_clips", index / max(1, last), f"Writing throw clips ({index}/{last} frames)")
            index += 1
        for out, writer in list(open_writers.items()):
            writer.close()
            done[out] = writer.count
    finally:
        capture.release()
        for writer in open_writers.values():
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass
    records = []
    for start, end, out in pending:
        partial = out.with_name(f".{out.stem}.partial{out.suffix}")
        written = done.get(out, 0)
        check = cv2.VideoCapture(str(partial))
        count = 0
        while check.read()[0]:
            count += 1
        check.release()
        if written != end - start or count != written:
            partial.unlink(missing_ok=True)
            raise RuntimeError(f"{out.name}: expected {end - start} frames, wrote {written}, read back {count}")
        partial.rename(out)
        records.append({"path": str(out), "start_frame": start, "end_frame_exclusive": end, "frame_count": written,
                        "fps": fps, "codec": kind, "width": size[0], "height": size[1],
                        "source_frame_mapping": "source_frame = clip_frame + start_frame"})
    return records


# ---------------------------------------------------------------------------------------------
# Orchestration


def _creation_seconds(value: str | None) -> float | None:
    if not value:
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def recording_date(signature: CameraSignature | None) -> str | None:
    """ISO date (YYYY-MM-DD) the camera recorded the take, from QuickTime metadata."""
    if signature is None or not signature.created:
        return None
    return signature.created[:10]


def prepare_take(front: str | Path | None, side: str | Path, output_dir: str | Path, *, take_number: int,
                 target_direction: str = "left_to_right", expected_throws: int | None = 4,
                 progress: Progress = _no_progress, scan_cache: dict[str, Any] | None = None) -> dict[str, Any]:
    """Synchronise one take, find its throws and cut a side (and front) clip per throw.

    Writes ``take.json`` in ``output_dir`` with the sync, every throw's time span and the clip files.
    Clips already present are reused (``take.json`` is the record); originals are never modified.
    """
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    record_path = out / "take.json"
    existing = json.loads(record_path.read_text()) if record_path.exists() else None
    side_sig = camera_signature(side)
    front_sig = camera_signature(front) if front else None
    record: dict[str, Any] = {
        "schema_version": 1, "take": take_number, "target_direction": target_direction,
        "side": {"path": str(side), "model": side_sig.model, "size": [side_sig.width, side_sig.height],
                 "fps": side_sig.fps, "frame_count": side_sig.frame_count, "recorded": recording_date(side_sig)},
        "front": None if front_sig is None else {
            "path": str(front), "model": front_sig.model, "size": [front_sig.width, front_sig.height],
            "fps": front_sig.fps, "frame_count": front_sig.frame_count, "recorded": recording_date(front_sig)},
        "notes": [],
    }
    # Synchronisation
    progress("synchronising", 0.02, "Reading both soundtracks")
    front_impacts_side: list[dict[str, float]] | None = None
    if front:
        try:
            side_env = loudness_envelope(load_audio(side))
            front_env = loudness_envelope(load_audio(front))
            guess = None
            t_side, t_front = _creation_seconds(side_sig.created), _creation_seconds(front_sig.created if front_sig else None)
            if t_side is not None and t_front is not None:
                # Creation time marks the start of recording: a sound at side time t is at front time t + (side_start - front_start).
                guess = t_side - t_front
            sync = sync_offset(front_env, side_env, coarse_guess_s=guess if guess is not None and abs(guess) < 8 else None)
            sync["creation_time_offset_s"] = guess
            if sync["status"] != "measured" and guess is not None:
                # A second, unconstrained search before giving up.
                sync = sync_offset(front_env, side_env)
                sync["creation_time_offset_s"] = guess
            record["sync"] = sync
            if sync["status"] == "measured":
                front_impacts_side = [{"time_s": e["time_s"] - sync["offset_s"], "level_db": e["level_db"]}
                                      for e in impact_times(front_env) if e["level_db"] >= 20]
        except Exception as error:  # noqa: BLE001 - analysis continues per view
            record["sync"] = {"status": "unavailable", "offset_s": None, "reason": f"Soundtrack could not be read: {error}"}
    else:
        record["sync"] = {"status": "unavailable", "offset_s": None, "reason": "No front video for this take."}
    # Throws
    progress("finding_throws", 0.05, "Looking for bag flights in the side video")
    scan = scan_cache if scan_cache is not None else scan_motion_blobs(
        side, progress=lambda s, f, m: progress(s, 0.05 + 0.6 * f, m))
    flights = find_flights(scan, target_direction)
    segmented = segment_throws(flights, scan["times_s"], scan["fps"], front_impacts_side, expected_throws)
    record["notes"].extend(segmented["notes"])
    record["scan"] = {"frames": scan["frame_count"], "fps": scan["fps"], "flights_found": len(flights)}
    # Clips: one decoding pass per camera writes every throw's clip.
    side_fps = scan["fps"]
    times = np.asarray(scan["times_s"], float)
    plans = []
    for throw in segmented["throws"]:
        start_t = max(0.0, throw["flight_start_s"] - CLIP_BEFORE_S)
        end_t = throw["flight_end_s"] + CLIP_AFTER_S
        side_start = int(np.searchsorted(times, start_t))
        side_end = int(min(scan["frame_count"], np.searchsorted(times, end_t)))
        entry: dict[str, Any] = {**throw, "side_clip": None, "front_clip": None,
                                 "side_clip_start_s": float(times[side_start]) if side_start < len(times) else start_t,
                                 "side_clip_end_s": float(times[max(0, min(side_end, len(times)) - 1)])}
        plans.append((entry, side_start, side_end))
    old_by_number = {t.get("number"): t for t in (existing or {}).get("throws", [])}

    def reuse(entry: dict[str, Any], key: str, path: Path, start: int) -> bool:
        old = old_by_number.get(entry["number"]) or {}
        if path.exists() and (old.get(key) or {}).get("start_frame") == start:
            entry[key] = old[key]
            return True
        path.unlink(missing_ok=True)
        return False

    windows = []
    for entry, s0, s1 in plans:
        path = out / f"throw_{entry['number']:02d}_side.mp4"
        if not reuse(entry, "side_clip", path, s0):
            windows.append((s0, s1, path))
    if windows:
        progress("cutting_clips", 0.68, "Writing the side clips")
        made = {Path(r["path"]).name: r for r in write_clips(side, windows, side_fps,
                progress=lambda s, f, m: progress(s, 0.68 + 0.14 * f, m))}
        for entry, s0, s1 in plans:
            entry["side_clip"] = entry["side_clip"] or made.get(f"throw_{entry['number']:02d}_side.mp4")
            if entry["side_clip"] is not None:
                entry["side_clip"]["frame_times_s"] = (times[s0:s1] - times[s0]).round(5).tolist()
    if front and front_sig and record["sync"].get("status") == "measured":
        offset = float(record["sync"]["offset_s"])
        f_fps = front_sig.fps
        front_times = np.asarray(clip_times(front), float)
        windows = []
        for entry, _, _ in plans:
            f_start = max(0, int(np.searchsorted(front_times, entry["side_clip_start_s"] + offset)) - 1)
            f_end = min(len(front_times), int(np.searchsorted(front_times, entry["side_clip_end_s"] + offset)) + 2)
            if f_end - f_start <= 10:
                entry["front_clip_reason"] = "The front recording does not cover this throw."
                continue
            entry["_front_window"] = (f_start, f_end)
            path = out / f"throw_{entry['number']:02d}_front.mp4"
            if not reuse(entry, "front_clip", path, f_start):
                windows.append((f_start, f_end, path))
        if windows:
            progress("cutting_clips", 0.84, "Writing the front clips")
            made = {Path(r["path"]).name: r for r in write_clips(front, windows, f_fps,
                    progress=lambda s, f, m: progress(s, 0.84 + 0.12 * f, m))}
            for entry, _, _ in plans:
                entry["front_clip"] = entry["front_clip"] or made.get(f"throw_{entry['number']:02d}_front.mp4")
        for entry, _, _ in plans:
            window = entry.pop("_front_window", None)
            if entry["front_clip"] and window:
                # Front-clip time (s) of side-clip frame 0: all the analysis needs to map one view onto the other.
                entry["front_clip"]["side_frame0_front_time_s"] = (entry["side_clip_start_s"] + offset) - float(front_times[window[0]])
                entry["front_clip"]["frame_times_s"] = (front_times[window[0]:window[1]] - front_times[window[0]]).round(5).tolist()
    elif front:
        for entry, _, _ in plans:
            entry["front_clip_reason"] = record["sync"].get("reason") or "The views could not be synchronised."
    # The front deck: found once on the take's opening seconds (an empty board), saved as the reference
    # frame every throw's clip is aligned to (the phone drifts slowly on its tripod).
    if front:
        record["front_board"] = find_take_board(front, out)
    # The side camera's board too: later throws have bags lying on the deck, which can hide the hole
    # the side-view detector checks, so the empty board at the start of the take is carried to every clip.
    progress("cutting_clips", 0.97, "Finding the board in the side camera")
    record["side_board"] = find_take_side_board(side, out, target_direction)
    if record["side_board"].get("status") == "found":
        for entry, _, _ in plans:
            if entry.get("side_clip"):
                entry["side_board_corners_frame0"] = carry_side_corners(out, record["side_board"],
                                                                        entry["side_clip"]["path"])
    throws = [entry for entry, _, _ in plans]
    throws = [entry for entry, _, _ in plans]
    record["throws"] = throws
    record_path.write_text(json.dumps(_json_ready(record), indent=2))
    progress("done", 1.0, f"{len(throws)} throws prepared")
    return record


FRONT_REFERENCE_NAME = "front_reference.png"


def find_take_board(front: str | Path, out: Path) -> dict[str, Any]:
    """Detect the deck in the front video's opening seconds (several windows, first success wins) and save
    the reference frame next to take.json."""
    import cv2
    from .front_view import deck_shape_hfov, detect_front_board, read_plate
    first_failure = None
    for start in (0.2, 2.0, 4.0, 8.0):
        try:
            plate = read_plate(str(front), start_s=start, span_s=1.6, count=9)
        except Exception as error:  # noqa: BLE001
            first_failure = first_failure or {"status": "not_found", "reason": f"Could not read the front video: {error}"}
            break
        board = detect_front_board(plate)
        if board["status"] == "found":
            cv2.imwrite(str(out / FRONT_REFERENCE_NAME), plate)
            board["reference_image"] = FRONT_REFERENCE_NAME
            board["reference_time_s"] = start
            board["hfov"] = deck_shape_hfov(np.asarray(board["corners_px"]), (plate.shape[1], plate.shape[0]))
            return board
        first_failure = first_failure or board
    if first_failure is not None:
        # Keep a reference frame anyway so the four corners can be clicked on it.
        try:
            cv2.imwrite(str(out / FRONT_REFERENCE_NAME), read_plate(str(front), start_s=0.2, span_s=1.6, count=9))
            first_failure["reference_image"] = FRONT_REFERENCE_NAME
            first_failure["reference_time_s"] = 0.2
        except Exception:  # noqa: BLE001
            pass
    return first_failure or {"status": "not_found", "reason": "No front video."}


SIDE_REFERENCE_NAME = "side_reference.png"


def find_take_side_board(side: str | Path, out: Path, target_direction: str) -> dict[str, Any]:
    """Side-view board on the take's opening seconds (board empty), saved as side_reference.png."""
    import cv2
    from .board import detect_board
    from .front_view import read_plate
    first = None
    for start in (0.2, 2.0, 4.0):
        try:
            plate = read_plate(str(side), start_s=start, span_s=1.6, count=9)
        except Exception as error:  # noqa: BLE001
            return {"status": "not_found", "reason": f"Could not read the side video: {error}"}
        found = detect_board(plate, target_direction)
        if found.get("status") == "found":
            cv2.imwrite(str(out / SIDE_REFERENCE_NAME), plate)
            return {"status": "found", "corners_px": np.asarray(found["corners_px"], float).tolist(),
                    "reference_image": SIDE_REFERENCE_NAME, "reference_time_s": start,
                    "hole_offset_in": found.get("hole_offset_in"), "confidence": found.get("confidence")}
        first = first or found
    return {"status": "not_found", "reason": "; ".join((first or {}).get("reasons") or ["board not found"])}


def carry_side_corners(out: Path, side_board: dict[str, Any], clip_path: str) -> dict[str, Any] | None:
    """The take's side-view deck corners in a throw clip's first frame (ECC alignment on the board area)."""
    import cv2
    from .front_view import align_to_reference, board_window, warp_points
    reference = cv2.imread(str(out / side_board["reference_image"]))
    capture = cv2.VideoCapture(str(clip_path))
    ok, frame = capture.read()
    capture.release()
    if reference is None or not ok:
        return None
    corners = np.asarray(side_board["corners_px"], float)
    window = board_window(corners, (reference.shape[1], reference.shape[0]))
    aligned = align_to_reference(cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY), cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), window)
    if not aligned["ok"]:
        return None
    return {"corners_px": warp_points(aligned["warp"], corners).round(2).tolist(), "reference_frame": 0,
            "correlation": aligned["correlation"]}


def clip_times(video: str | Path) -> list[float]:
    """Container timestamps (s) of every frame, read without decoding (grab only)."""
    import cv2
    capture = cv2.VideoCapture(str(video))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    times, index = [], 0
    try:
        while capture.grab():
            pos = capture.get(cv2.CAP_PROP_POS_MSEC)
            times.append(pos / 1000.0 if pos and pos > 0 else index / fps)
            index += 1
    finally:
        capture.release()
    return np.maximum.accumulate(np.asarray(times, float)).tolist() if times else []


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(v) for v in value]
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def side_to_front_frame(side_clip_frame: float, side_fps: float, front_clip: dict[str, Any], front_fps: float) -> float:
    """Front-clip frame (fractional) showing the same instant as a side-clip frame."""
    return (side_clip_frame / side_fps + float(front_clip["side_frame0_front_time_s"])) * front_fps


def front_setups(take_records: Sequence[Path]) -> dict[str, list[Path]]:
    """Take records grouped by front camera: device model, frame size and recording date."""
    groups: dict[str, list[Path]] = {}
    for path in take_records:
        try:
            front = json.loads(Path(path).read_text()).get("front") or {}
        except (OSError, ValueError):
            continue
        key = f"{front.get('model') or 'unknown camera'} {'x'.join(map(str, front.get('size') or []))} {front.get('recorded') or 'unknown date'}"
        groups.setdefault(key, []).append(Path(path))
    return groups


def pool_front_hfov(take_records: Sequence[Path]) -> dict[str, Any]:
    """Median front-camera field of view over takes from one set-up, written into each take.json.

    One take's deck-shape value is ±2–3° (half a pixel of corner error); the median of a session's takes is
    steadier. Takes more than 6° from the median are reported and still receive the median.
    """
    values = {}
    for path in take_records:
        record = json.loads(Path(path).read_text())
        hfov = ((record.get("front_board") or {}).get("hfov") or {})
        if hfov.get("status") == "measured" and hfov.get("hfov_deg"):
            values[str(path)] = float(hfov["hfov_deg"])
    if not values:
        return {"status": "unavailable", "reason": "No take had a measured front field of view.", "takes": 0}
    median = float(np.median(list(values.values())))
    outliers = [p for p, v in values.items() if abs(v - median) > 6.0]
    for path in take_records:
        record = json.loads(Path(path).read_text())
        record["front_hfov_pooled"] = median
        record["front_hfov_pool"] = {"median_deg": median, "takes": len(values),
                                     "spread_deg": float(np.ptp(list(values.values()))), "outliers": outliers}
        Path(path).write_text(json.dumps(_json_ready(record), indent=2))
    return {"status": "measured", "median_deg": median, "takes": len(values), "values": values, "outliers": outliers}


def share_front_lag(take_records: Sequence[Path]) -> dict[str, Any] | None:
    """Give takes of one front set-up the picture lag already measured on its other takes (``two_view.pool_front_lag``).

    Newly imported takes have no analysed throws yet; the lag belongs to the camera set-up, not the take."""
    measured = []
    for path in take_records:
        record = json.loads(Path(path).read_text())
        if record.get("front_lag_s") is not None and (record.get("front_lag_pool") or {}).get("status") == "measured":
            measured.append(record["front_lag_pool"])
    if not measured:
        return None
    pool = max(measured, key=lambda m: m.get("throws") or 0)
    for path in take_records:
        record = json.loads(Path(path).read_text())
        if record.get("front_lag_s") is None:
            record["front_lag_s"] = pool.get("applied_s", pool["lag_s"])
            record["front_lag_pool"] = pool
            Path(path).write_text(json.dumps(_json_ready(record), indent=2))
    return pool


def set_front_corners(take_record: Path, corners_px: np.ndarray) -> dict[str, Any]:
    """Replace the automatic deck corners of a take's front reference frame with clicked ones."""
    from .front_view import deck_homography, deck_shape_hfov, find_hole
    import cv2
    record = json.loads(take_record.read_text())
    board = record.get("front_board") or {}
    image_path = take_record.parent / (board.get("reference_image") or FRONT_REFERENCE_NAME)
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"No front reference frame at {image_path}")
    corners = np.asarray(corners_px, float).reshape(4, 2)
    hole = find_hole(image, deck_homography(corners))
    board.update(status="found", corners_px=corners.tolist(), source="clicked", reason=None,
                 checks={**(board.get("checks") or {}), "hole": hole},
                 hfov=deck_shape_hfov(corners, (image.shape[1], image.shape[0])))
    record["front_board"] = board
    take_record.write_text(json.dumps(_json_ready(record), indent=2))
    return {"status": "found", "hole_offset_in": None if hole is None else hole["offset_in"]}
