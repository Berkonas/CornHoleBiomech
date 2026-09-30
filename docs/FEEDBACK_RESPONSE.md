# Response to the 24 September report feedback

How the app changed in response to Dr. Zelik's comments, the peer review, and the team's notes after the tripod sessions (29 September 2026). Equations and validation are in [METHODS_AND_MATH.md](METHODS_AND_MATH.md) (§1.9 board phase, §1.13 personal green zone, §2.3 verdict).

| Feedback | What the app does now |
|---|---|
| "How does the system address heading (left–right) errors?" (Zelik); "nothing measures left/right" (peer) | Stated in the app and methods: the side camera does not measure left/right; the pilot throws were made straight at the board. The board phase decides outcomes from the along-board position only. The board camera is the route to lateral error. |
| "There is not just one right speed or angle, it's the combination" (Zelik); motor abundance / Bernstein | The personal green zone is the set of speed × angle combinations that reach the hole for this athlete. The best aim is where that set is widest relative to the athlete's own spread, and the model's chance of the hole window is shown for their usual release and for the best aim. |
| "If the ball stopped past the target the player can see it … what if the app says too fast but it landed next to the target?" (peer) | Outcome first: a made throw gets no corrections. Advice for a board bag or miss comes from where the bag actually stopped, signed short/long, not from the model alone. |
| Error column unsigned; over- vs under-throws (peer) | The summary table's *Ended* column is signed (− short, + past, "In hole"). The verdict states short/long. |
| "Can recording the result be automated? The coach is busy" (Zelik) | The board phase suggests Hole / Board / Miss from the video. One click accepts it. It matched the recorded result on 10/10 tripod clips with a located board. |
| "How will you know the system is accurate enough?" (Zelik) | Board-phase end classification checked frame by frame on 10 clips; along-board position uncertainty about ±3 in stated. The per-athlete model check is reported: 40 % model chance of the hole window vs 42 % observed for Player 1. |
| "Be quantitative where possible" (Zelik) | Slide distance, time, entry speed, deceleration and effective friction μ are measured for each throw. |
| Simplify for coaches (peer) | Each throw gets one plain sentence ("Landed 15 in short of the hole, slid 18 in, hung on the lip for 0.6 s and dropped in.") and a top-view board drawing. |
| Recommended range needs grounding (peer) | The green window comes from the drag-free model with the athlete's measured distance, height and slide. The best aim comes from their measured variability. |
| Distance assumption | The measured release-to-board distance is used everywhere (tripod sessions ≈ 5.1–5.8 m, not the 27 ft regulation pitch). Implausible measured distances (> 15 m from a failed board scale) are ignored. |
| Team: average and pattern came from only the first five throws | The summary's consistency now pools every comparable throw and names any left out. The dashboard is built from the largest comparable group, not the newest throw. |
| Team: the computer crashes when analyzing all videos at once | One analysis at a time: an app queue plus a Mac-wide lock in the engine. |
