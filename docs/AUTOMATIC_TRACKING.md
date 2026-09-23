# Automatic bag tracking

Written 22 September 2026. Code: `python/cornhole_biomech/auto_bag.py`. Tests: `tests/test_auto_bag.py`.

## Why this design

- **Deep ball trackers need training data we don't have.** TrackNet-style heat-map networks need thousands of labelled frames of the same object ([Huang et al., 2019](https://arxiv.org/abs/1907.03698)), and none exist for cornhole bags.
- **General video segmenters are too heavy.** SAM 2 would add a multi-gigabyte model and slow CPU inference ([Meta](https://ai.meta.com/sam2/)).
- **The classical recipe fits.** Moving-candidate detection plus trajectory selection is what those networks were built on: TrackNetV3 adds background subtraction and trajectory rectification ([ScienceDirect 2025](https://www.sciencedirect.com/science/article/pii/S1877050925016709)).
- **Physics is the strongest prior.** A bag in free flight must follow a parabola whose downward acceleration is g. That rules out almost all clutter without any training.

## Steps

1. **Candidates.** Each frame is compared with its two neighbours after aligning them with an ORB-feature similarity transform (RANSAC), so hand-held drift is not "motion". Pixels that differ from both neighbours become blobs (three-frame differencing). Fragments of one blurred bag within 16 px are merged into one area-weighted blob.
2. **Seeds.** Blobs are linked frame to frame with a constant-velocity prediction (tracklets). Short windows of each tracklet are fitted with a quadratic, and RANSAC over triples is the fallback.
3. **Physics checks for a seed.**
   - It moves toward the target.
   - It curves downward, with image gravity inside the range implied by the athlete's arm length: the projected shoulder–wrist length is taken as 0.45–0.9 m, giving a pixels-per-metre range.
   - Horizontal curvature is small.
4. **Growth and trimming.** The best seed collects matching blobs, then extends frame by frame from both ends with a local fit.
   - Backward extension stops when the bag is still in the hand: within 0.45 arm lengths of the wrist, since a held bag sits about one hand length beyond the wrist landmark.
   - The end is trimmed where the bag breaks from a local parabola of the preceding 15 frames (slide or bounce after landing).
5. **Events.**
   - Release is the first free-flight frame.
   - First contact is the last on-parabola frame, but only if the bag is descending and inside the image. Otherwise contact is reported as unknown.
6. **Acceptance.** A flight is used without review only if all of these hold. Anything else is `needs_review` with the reason.
   - At least 12 detections covering at least 0.25 s and at least 60 % of flight frames.
   - RMS residual at most 0.08 arm lengths.
   - At least 4 arm lengths of travel toward the target.
   - The flight starts within 0.8 arm lengths of the wrist.
7. **Several throws per clip.** The detections of each found flight are removed and the search repeats. The trial uses the flight that starts at the throwing hand.
8. **Centroid.** Each detection is refined to the centre of the bag's silhouette (`bag_segment.py`): a local median background from camera-aligned neighbouring frames, a colour-difference mask, and image moments. Short gaps are re-acquired the same way. The detection centroid is kept next to it. The difference blob marks where the bag contrasts most with the background, so on the pilot clips it sat up to ~15 px from the centre.
9. **Coordinates.** Since revision 9, flight points are raw video pixels, the same system as the video, pose and manual clicks. `stabilized_points` and per-frame `camera_to_release` transforms hold the camera-motion-free version. Launch fits, the gravity scale and the model check use that version, so they behave as if the camera were fixed. Revision 8 stored only the stabilised points, which the overlay then drew on the moving video, 5–49 px off the bag.
10. **Filtered path.** `bag_filter.py` smooths the stabilised flight with a constant-acceleration Kalman filter and RTS smoother. Noise is estimated per clip, outliers are rejected by leave-one-out, and raw values are kept. The result goes to `bag_flight_filtered.json` and to the overlay's filtered centroid.

See `docs/SECOND_PASS_AUDIT.md` for the pilot evidence and `docs/BAG_TRACKING_VALIDATION.md` for measuring accuracy.

An accepted flight counts as reviewed with `confirmed_by = automatic_physics`. Any manual seed, correction, release or contact always overrides it.

## Pilot result (26 hand-held clips, 17 September 2026)

| Clip | Automatic result | Release frame | First contact | Angle (°) | Speed (m/s) | Height (m) | Arm angle at release (°) |
|---|---|---|---|---|---|---|---|
| 1 | accepted | 227 | 293 | 35.4 | 8.22 | 0.92 | 72 |
| 2 | accepted | 168 | 236 | 44.8 | 8.13 | 1.03 | 72 |
| 3 | accepted | 206 | 273 | 42.5 | 7.56 | 1.03 | 77 |
| 4 | accepted | 200 | 241 | 47.1 | — | — | 79 |
| 5 | review: The path moves only 0.1 arm lengths toward the target; a thr | — | — | — | — | — | — |
| 6 | accepted | 156 | 223 | 40.8 | 7.82 | 0.91 | 69 |
| 7 | accepted | 203 | unknown | 63.8 | — | — | 71 |
| 8 | review: The detected flight starts 2.5 arm lengths from the wrist; a | — | — | — | — | — | — |
| 9 | review: The detected flight starts 1.8 arm lengths from the wrist; a | — | — | — | — | — | — |
| 10 | accepted | 194 | 271 | 50.1 | 7.72 | 0.85 | 41 |
| 11 | accepted | 122 | 192 | 50.0 | 7.86 | 1.07 | 76 |
| 12 | accepted | 153 | 218 | 32.5 | 8.52 | 0.55 | 5 |
| 13 | review: The detected flight starts 1.6 arm lengths from the wrist; a | — | — | — | — | — | — |
| 14 | review: The path moves only 0.0 arm lengths toward the target; a thr | — | — | — | — | — | — |
| 15 | accepted | 628 | 702 | 68.4 | 5.94 | 0.94 | 40 |
| 16 | accepted | 134 | 186 | 37.0 | 7.78 | 1.20 | 74 |
| 17 | accepted | 180 | 226 | 37.2 | — | — | 73 |
| 18 | accepted | 190 | 254 | 37.5 | 7.57 | 0.77 | 44 |
| 19 | accepted | 50 | 107 | 30.6 | 7.93 | 0.82 | 73 |
| 20 | accepted | 245 | 298 | 27.7 | 7.36 | 0.70 | 41 |
| 21 | accepted | 39 | 98 | 29.1 | 8.11 | 1.08 | 70 |
| 22 | accepted | 91 | 130 | 45.6 | 6.71 | 0.48 | 26 |
| 23 | accepted | 40 | 76 | 12.5 | 10.89 | 0.67 | 54 |
| 24 | review: The bag left view or was lost before landing, so first conta | — | — | — | — | — | — |
| 25 | accepted | 81 | 137 | 59.5 | 6.42 | 1.07 | 68 |
| 26 | accepted | 103 | 170 | 48.0 | 5.41 | 1.43 | 92 |

- **20 of 26 clips** were accepted with no clicks. Clips 5 and 14 contain no complete throw. Clips 8, 9, 13 and 24 need review: the flight was split, or its start was not at the hand.
- **Agreement with manual review, clip 10 (the only clip with one):** first contact 271 vs 272 (−1 frame); release 194 vs 198 (−4 frames, 67 ms). A single clip does not establish accuracy. Measure release and contact agreement on the validation subset with `tools/annotator.html` and `validate-tracking` before quoting accuracy.
- **Where the pilot footage breaks tracking:** the hand-held camera, small blurred bags, a red bag over a red board, and bags leaving the frame. The recording protocol (tripods, athlete camera framed closer, contrasting bags) addresses each.
- Speed and height are missing on a few accepted clips because the flight's gravity scale did not have enough coverage. A meter stick in the throwing plane removes that dependency.
