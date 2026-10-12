# What each camera measures, and how the two are combined

A one-page map for the presentation and the Q&A. Every number in the app comes from one of three routes: the **side
camera alone**, the **front camera alone**, or **both cameras combined** after synchronising them. The two cameras are
never merged into a 3D skeleton: each body measure is a 2D measure in one camera's view, and the only 3D quantity is the
bag's flight, fitted with physics (see "Both cameras").

## The set-up

| | Side camera | Front camera |
|---|---|---|
| Position | Tripod beside the throwing lane, optical axis across the throw | Tripod behind the board, looking back at the thrower |
| Recording | iPhone, 1920 × 1080, 59.94 fps | iPhone, 1280 × 720, 30 fps |
| Plane it sees well | The **throw plane** (sagittal): forward–back and up–down | The **frontal plane**: left–right and up–down |
| Plane it cannot see | Left–right (depth to the camera) | Distance along the throw (the bag flies straight at it) |
| Scale | The board's 48 in deck (perspective-n-point), checked against gravity on the bag's arc | The board's deck corners (homography; camera pose from the deck shape) |

## Side camera only (sagittal plane, metres and seconds)

| Group | Measures | How |
|---|---|---|
| Body (Sports2D pose, 6 Hz zero-phase filter) | Arm angle at release, backswing angle, forward-swing time, tempo, peak wrist speed and its timing, trunk lean at release, elbow angle at release (advanced) | Throwing-side shoulder–elbow–wrist and hips in the side image; angles are 2D projections in the throw plane |
| Release event | Release frame | Bag leaving the hand, confirmed against the wrist path |
| Release conditions | **Release speed, release angle, release height, release point** | Gravity-constrained fit of the first ~0.12 s of bag flight, in the board's throw plane (or the flight's own gravity scale when the board plane is not usable) |
| Flight | Arc, apex, time of flight, drag-free model | Bag track from release to first contact |
| Landing along the board | **First contact along the deck**, slide length, slide friction, rest along the deck, fell-in-hole | Board phase: the bag on the tilted deck after touchdown |

## Front camera only (frontal plane)

| Group | Measures | How |
|---|---|---|
| Result | **Hole / board / off** | New bag on the deck, under the board (through the hole) or on the floor, against the frame before the throw |
| Landing across the board | **Left/right of first contact and of rest** | Deck homography (about ±0.3 in) |
| Body (same Sports2D model) | Hand across the body at release and 0.15 s later, trunk side lean, shoulder tilt, **hand-path sideways range** in the forward swing, **trunk lean change** set-up → release, stance width and offset | Front image, roll-corrected; reported as *front view 2D*. No elbow or shoulder joint angles: the arm swings toward this camera |
| Identity checks | Knocked bags, a slide that turns onto another bag | Changes on the deck and the deck track |

## Both cameras combined

| What | Side gives | Front gives | Combined into |
|---|---|---|---|
| Synchronisation | Soundtrack, side contact frame | Soundtrack, front contact frame | Clap and impact cross-correlation (±17.5 ms), then the set-up's measured picture lag (18 ms, 79 throws) |
| 3D bag flight | The arc along the throw and up (metric) | Where the bag is sideways in each frame | **Sideways release position, sideways launch direction, launch line** (physics-constrained fit; `measured` or `estimated`) |
| Landing point | Distance up the deck | Distance across the deck | **First contact and rest on the board, the miss from the hole** (short/long, left/right) |
| Release position sideways | Release distance to the board | Release hand in the image + camera pose | **Release point from the board's centre line** |
| Result checks | How the bag ended (rest / hole / floor) | Hole / board / off | Agreement check; a knocked-bag ambiguity on the front is settled by the side ending |
| Miss explanation | Release speed and angle (carry), slide | Aim, release position, sideways slide, body at release | The four-part explanation: observed, measured evidence, possible reason, what to review |

## Which parameters we look at, and why

The coach report leads with the parameters that can resolve a single throw's difference (METRICS.md "Metric review"):

1. **Release speed and release angle** (side). They set the carry through the drag-free flight; ≈ 1.3 m of first
   contact per m/s at our athletes' release distance.
2. **Launch direction and release position sideways** (both cameras). They set left/right through the geometry of
   the launch line.
3. **First contact and slide** (side along, front across). They separate a miss made in the flight from one made
   after landing.
4. **Body profile** (each camera): forward-swing time and tempo (side, per throw); backswing, trunk lean, peak wrist
   speed (side), hand-path range and trunk lean change (front) describe *how* an athlete throws. They are compared
   with the athlete's own usual, never with other athletes, and are reported as associations, not causes.

## Limits to state in the presentation

- No 3D joint angles: the cameras are not calibrated to each other for the body; each body angle is a 2D projection.
- The 3D flight is a fit to physics and one camera's sideways view, not stereo triangulation.
- On 45 of 92 throws the side camera's field of view varied too much to use the board-plane fit, so release speed
  comes from the flight's own gravity scale.
- Four athletes, 20–28 throws each: findings describe these athletes; validation against hand-marked frames is
  planned (VALIDATION_PLAN.md).
