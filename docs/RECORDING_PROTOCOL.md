# Recording protocol (session-day checklist)

Written 22 September 2026 after reviewing the 17 September pilot clips. Those clips remain useful as pilot and validation data, but they show four problems this protocol fixes:

| Pilot problem (measured) | Consequence | Fix below |
|---|---|---|
| Handheld camera: background drifts up to ~100 px within one clip | Bag path, apex and launch angle include camera motion | Tripods, locked zoom |
| Athlete only ~300 px tall in a 1080p frame (upper arm ~60 px) | Simulated 2–4 px landmark noise gives ~5–10° elbow-angle SD, as large as real throw-to-throw differences | Camera A framed on the athlete |
| Board small and foreshortened; bag ~10–20 px | Landing position is a guess from a schematic click | Camera B on the board, four corners visible |
| No known length in the throwing plane | No m/s, only pixels or arm lengths | Meter stick at the start of each session |

Analysis methods and the validation plan are in [VALIDATION_PLAN.md](VALIDATION_PLAN.md). This page is only about getting usable recordings.

## Equipment

- 2 phones on tripods (a third is optional), each with at least 20 minutes of free storage.
- A 1 m stick or tape measure that can be held rigid.
- Tape for marking the tripod, foul-line and board positions.
- Bags in a color that differs from the board, floor, background and the athlete's clothing. **Avoid red bags on a red board.** The bag tracker follows color.
- An outcome sheet (template below) and a pen, or a second person entering results.

## Camera A: athlete (body and release)

1. Put the tripod on the **throwing-arm side** of the athlete, so the torso never hides the throwing arm.
2. Aim the optical axis perpendicular to the throwing direction, at roughly hip-to-shoulder height (about 1.0–1.2 m).
3. Frame so that the athlete's standing height fills about **60–70 % of the frame height**. The frame must also include about 1.5 m in front of the release point, so the first ~0.2 s of bag flight is visible.
4. Use landscape orientation, 1080p, and the **highest available frame rate** (120 fps preferred, 60 fps minimum). Lock focus and exposure (long-press on iPhone), and do not zoom after starting.
5. At the start of **every** session, have someone hold the 1 m stick level and then vertical, at the athlete's release position in the throwing plane, for 3 s each. This is the calibration for m/s.

## Camera B: board (landing)

1. Place it behind or beside the receiving board, raised as high as practical (a tripod at full height, a chair or a balcony) and looking down at the board.
2. **All four board corners must be visible**, plus about 1 m of floor around the board. The app will use the corners (24 × 48 in) to convert clicked landing points into board inches.
3. Use landscape orientation, 60 fps or higher, and locked exposure.

## Optional camera C: full flight

The pilot setup (wide side view of the whole pitch) is still useful for flight time and whole-trajectory visuals. Use it only on a tripod.

## Synchronizing cameras

Start all cameras, then clap once where every camera can see it. Leave the cameras recording and do not stop and restart between throws, unless you record one clip per throw on every camera.

## Per athlete

- Measure standing height, and upper-arm and forearm length (acromion→lateral epicondyle→ulnar styloid). Enter these in the athlete profile.
- 5 warm-up throws, not recorded as trials.
- **At least 20 recorded throws**, all at the same intended target. Novice athletes need enough misses *and* scored throws to compare. Twenty gives each group a realistic chance of reaching ~5.
- Pause about 3 s between throws, and call out the throw number before each one.
- **Never delete or skip a bad throw.** Record it and note why it might be excluded (for example a fumble or a foul).

## Outcome sheet (fill in immediately after each throw)

| Throw # | Points (0 / 1 / 3) | First contact: board / ground / hole | Bag stayed on board? | Notes |
|---|---|---|---|---|

"Success" in the app's main comparison is **scored (1 or 3) versus miss (0)**. Hole versus board is shown separately.

## Before leaving the session

- Play back one throw from each camera. Check that the throwing arm, the bag at release and all four board corners are visible and sharp.
- Check the actual frame rate of the exported files. Slow-motion exports can be retimed, so the app reports the file's real fps on import.
- Write down the camera positions (distance and height), phone models, frame rates and the tape-marked layout.

## Validation subset

For the tracking-accuracy study, pick 5 throws per athlete **before looking at any results** (for example throws 3, 7, 11, 15, 19). Two team members will mark landmarks, bag centers, release frames and landing points on those clips by hand.
