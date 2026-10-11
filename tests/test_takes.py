"""Two-camera takes: pairing, camera roles, sound sync, throw segmentation and clip cutting."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from cornhole_biomech import takes as T


def test_take_names_are_matched_in_any_capitalisation():
    assert T.parse_take_name("Take_2_Side.mov") == (2, "side")
    assert T.parse_take_name("take_5_Side.mov") == (5, "side")
    assert T.parse_take_name("Take_6_side.MOV") == (6, "side")
    assert T.parse_take_name("TAKE 3 FRONT.mp4") == (3, "front")
    assert T.parse_take_name("take-12-front.mov") == (12, "front")
    assert T.parse_take_name("throw1.mov") is None
    assert T.parse_take_name("Take_1_Sideways.mov") is None


def test_discover_takes_pairs_files_and_reports_gaps(tmp_path: Path):
    for name in ("Take_1_Front.mov", "Take_1_Side.mov", "take_2_Side.mov", "Take_2_front.MOV", "Take_3_Front.mov",
                 "notes.txt", ".hidden_Take_4_Side.mov"):
        (tmp_path / name).write_bytes(b"x")
    takes = T.discover_takes(tmp_path)
    assert [t.take for t in takes] == [1, 2, 3]
    assert Path(takes[1].side).name == "take_2_Side.mov" and Path(takes[1].front).name == "Take_2_front.MOV"
    assert takes[2].side is None and any("no side video" in n for n in takes[2].notes)


def _sig(model: str, w: int, h: int, fps: float) -> T.CameraSignature:
    return T.CameraSignature(model=model, width=w, height=h, fps=fps, duration_s=30.0, frame_count=900, created=None)


def test_swapped_front_and_side_labels_are_detected_from_the_cameras():
    side, front = _sig("iPhone 15 Pro Max", 1920, 1080, 59.94), _sig("iPhone 17 Pro", 1280, 720, 30.0)
    takes = [T.TakeFiles(1, front="f1", side="s1"), T.TakeFiles(2, front="f2", side="s2"),
             T.TakeFiles(3, front="f3", side="s3")]
    sigs = {"f1": front, "s1": side, "f2": front, "s2": side, "f3": side, "s3": front}   # take 3 mislabelled
    roles = T.assign_camera_roles(takes, sigs)
    assert roles["swapped_takes"] == [3]
    assert takes[2].front == "s3" and takes[2].side == "f3"
    assert any("other camera" in n for n in takes[2].notes)


def test_identical_cameras_keep_the_file_names():
    same = _sig("iPhone", 1920, 1080, 30.0)
    takes = [T.TakeFiles(1, front="f1", side="s1")]
    roles = T.assign_camera_roles(takes, {"f1": same, "s1": same})
    assert roles["status"] == "unavailable" and takes[0].front == "f1"


def test_nominal_frame_rate_snaps_only_close_values():
    assert T.nominal_fps(59.959) == 59.94
    assert T.nominal_fps(30.0) == 30.0          # must not become 29.97 (one frame off after 33 s)
    assert T.nominal_fps(29.97) == 29.97
    assert T.nominal_fps(29.69) == 29.69        # a clip with dropped frames keeps its measured rate


def _impulse_track(times: list[float], duration: float, rate: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    audio = 0.002 * rng.standard_normal(int(duration * rate))
    for t in times:
        i = int(t * rate)
        n = int(0.03 * rate)
        burst = rng.standard_normal(n) * np.exp(-np.arange(n) / (0.004 * rate))
        audio[i:i + n] += 0.5 * burst[: len(audio[i:i + n])]
    return audio


def test_sound_sync_recovers_a_known_offset():
    rate = T.AUDIO_RATE_HZ
    events_side = [1.9, 7.4, 10.4, 15.95, 21.66, 27.2]          # clap + impacts, side clock
    offset = 1.713
    side = _impulse_track(events_side, 30.0, rate, 1)
    front = _impulse_track([t + offset for t in events_side[:-1]] + [29.5], 31.5, rate, 2)
    result = T.sync_offset(T.loudness_envelope(front), T.loudness_envelope(side))
    assert result["status"] == "measured"
    assert abs(result["offset_s"] - offset) < 0.006
    assert result["convention"] == "front_time = side_time + offset_s"


def test_sound_sync_refuses_unrelated_soundtracks():
    rate = T.AUDIO_RATE_HZ
    rng = np.random.default_rng(5)
    a = 0.01 * rng.standard_normal(20 * rate)
    b = 0.01 * rng.standard_normal(20 * rate)
    result = T.sync_offset(T.loudness_envelope(a), T.loudness_envelope(b))
    assert result["status"] == "unavailable" and result["offset_s"] is None and result["reason"]


def _flight_blobs(start_frame: int, x0: float, frames: int, vx: float, vy0: float, g: float):
    out = []
    for k in range(frames):
        out.append((start_frame + k, x0 + vx * k, 110 + vy0 * k + 0.5 * g * k * k, 30.0))
    return out


def test_bag_flights_become_throws_and_people_walking_do_not():
    fps = 59.94
    blobs = []
    for start in (300, 900, 1500, 2100):                    # four throws, 10 s apart
        blobs += _flight_blobs(start, 100, 70, 4.6, -3.0, 0.08)
    blobs += [(f, 400 - 0.5 * (f - 600), 150, 40.0) for f in range(600, 800)]     # a bystander walking slowly
    blobs += [(f, 60 + 2.0 * math.sin(f / 5), 130, 60.0) for f in range(1000, 1060)]  # the athlete fidgeting
    scan = {"blobs": blobs, "fps": fps, "frame_count": 2400, "width_px": 480,
            "times_s": (np.arange(2400) / fps).tolist()}
    flights = T.find_flights(scan, "left_to_right")
    seg = T.segment_throws(flights, scan["times_s"], fps, None, expected=4)
    assert len(seg["throws"]) == 4 and not seg["notes"]
    assert [round(t["flight_start_s"], 1) for t in seg["throws"]] == [round(s / fps, 1) for s in (300, 900, 1500, 2100)]


def test_wrong_throw_count_is_reported():
    fps = 60.0
    blobs = _flight_blobs(300, 100, 70, 4.6, -3.0, 0.08)
    scan = {"blobs": blobs, "fps": fps, "frame_count": 600, "width_px": 480, "times_s": (np.arange(600) / fps).tolist()}
    seg = T.segment_throws(T.find_flights(scan, "left_to_right"), scan["times_s"], fps, None, expected=4)
    assert len(seg["throws"]) == 1 and "expected to have 4" in seg["notes"][0]


def test_impact_sound_confirms_each_flight():
    fps = 60.0
    blobs = _flight_blobs(300, 100, 70, 4.6, -3.0, 0.08) + _flight_blobs(900, 100, 70, 4.6, -3.0, 0.08)
    scan = {"blobs": blobs, "fps": fps, "frame_count": 1200, "width_px": 480, "times_s": (np.arange(1200) / fps).tolist()}
    impacts = [{"time_s": 370 / fps, "level_db": 40.0}]       # only the first throw was heard
    seg = T.segment_throws(T.find_flights(scan, "left_to_right"), scan["times_s"], fps, impacts, expected=2)
    assert [t["impact_heard"] for t in seg["throws"]] == [True, False]
    assert any("No impact sound" in n for n in seg["notes"])


def test_clips_are_frame_exact_copies(tmp_path: Path):
    cv2 = pytest.importorskip("cv2")
    source = tmp_path / "source.avi"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (160, 96))
    for i in range(60):
        frame = np.zeros((96, 160, 3), np.uint8)
        cv2.putText(frame, str(i), (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
        frame[:, : i + 1] = (0, 0, 200)
        writer.write(frame)
    writer.release()
    records = T.write_clips(source, [(10, 25, tmp_path / "a.mp4"), (40, 55, tmp_path / "b.mp4")], 30.0)
    assert [r["frame_count"] for r in records] == [15, 15]
    capture = cv2.VideoCapture(str(tmp_path / "b.mp4"))
    ok, first = capture.read()
    capture.release()
    # Frame 40 has the red band up to column 40; the clip's first frame must be that frame.
    red = (first[5, :, 2] > 120) & (first[5, :, 1] < 80)
    assert ok and abs(int(red.sum()) - 41) <= 2
    with pytest.raises(ValueError):
        T.write_clips(source, [(0, 5, tmp_path / "a.mp4")], 30.0)      # never overwrites


def test_quicktime_metadata_reader_handles_non_quicktime_files(tmp_path: Path):
    path = tmp_path / "x.mov"
    path.write_bytes(b"\x00\x00\x00\x08free")
    assert T.quicktime_metadata(path) == {}


def test_an_extra_silent_flight_is_left_out_when_the_take_has_enough_heard_throws():
    fps = 60.0
    times = [i / fps for i in range(60 * 40)]
    starts = [6, 12, 18, 24, 30]                       # five "flights"; the last is the phone being picked up
    flights = [{"start_frame": int(s * fps), "end_frame": int((s + 1.5) * fps), "launch_frame": int(s * fps),
                "tracklets": [], "points": [], "x_span_fraction": 0.8} for s in starts]
    impacts = [{"time_s": s + 1.2, "level_db": -20.0} for s in starts[:4]]
    seg = T.segment_throws(flights, times, fps, impacts, expected=4)
    assert [t["number"] for t in seg["throws"]] == [1, 2, 3, 4]
    assert all(t["impact_heard"] for t in seg["throws"])
    assert any("left out" in n for n in seg["notes"])
    # Without enough heard landings nothing is dropped (the extra flight could be a real, silent miss).
    kept = T.segment_throws(flights, times, fps, impacts[:3], expected=4)
    assert len(kept["throws"]) == 5


def test_front_field_of_view_is_pooled_per_front_camera_and_day(tmp_path):
    import json as _json
    paths = []
    for i, (model, day, hfov) in enumerate([("iPhone 17 Pro", "2026-10-01", 65.0), ("iPhone 17 Pro", "2026-10-01", 67.0),
                                            ("iPhone 17 Pro", "2026-10-01", 76.0), ("iPhone 13", "2026-10-01", 80.0)]):
        path = tmp_path / f"take{i}.json"
        path.write_text(_json.dumps({"front": {"model": model, "size": [1280, 720], "recorded": day},
                                     "front_board": {"hfov": {"status": "measured", "hfov_deg": hfov}}}))
        paths.append(path)
    groups = T.front_setups(paths)
    assert sorted(len(v) for v in groups.values()) == [1, 3]
    pooled = {k: T.pool_front_hfov(v) for k, v in groups.items()}
    assert pooled["iPhone 17 Pro 1280x720 2026-10-01"]["median_deg"] == 67.0
    assert _json.loads(paths[2].read_text())["front_hfov_pooled"] == 67.0      # the 76° take gets the median


def test_a_moving_camera_is_not_a_bag_flight():
    fps = 60.0
    rng = np.random.default_rng(2)
    blobs = _flight_blobs(300, 100, 70, 4.6, -3.0, 0.08)
    blobs += [(f, float(rng.uniform(0, 480)), float(rng.uniform(0, 270)), 20.0) for f in range(0, 1200, 1)
              for _ in range(2)]                                                       # a quiet scene
    blobs += _flight_blobs(800, 100, 40, 10.0, -1.0, 0.0)                              # "flight" during ...
    blobs += [(f, float(rng.uniform(0, 480)), float(rng.uniform(0, 270)), 20.0) for f in range(790, 850)
              for _ in range(25)]                                                      # ... a camera bump
    scan = {"blobs": blobs, "fps": fps, "frame_count": 1200, "width_px": 480, "times_s": (np.arange(1200) / fps).tolist()}
    flights = T.find_flights(scan, "left_to_right")
    assert [f["start_frame"] for f in flights] == [300]
