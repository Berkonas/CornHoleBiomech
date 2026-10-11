CORNHOLE BAG-TRACKING VALIDATION: rater instructions

Full guide: docs/BAG_TRACKING_VALIDATION.md in the project.

1. Open tools/annotator.html (in the project folder) in Chrome or Safari.
2. Enter your initials. Load ALL the PNGs of one folder below plus its annotation_manifest.json.
   Do NOT open bag_validation_plan.json: it shows the computer's guesses.
3. On each frame, click the CENTRE OF THE BAG'S VISIBLE OUTLINE. If the bag is hidden or out of frame, press N.
4. Step through the original video (data/videos in the project folder) and type:
   - Release: the first frame where the bag has clearly separated from the hand and is in independent flight.
     If you cannot tell exactly, also fill in the earliest and latest plausible frames.
   - First contact: the first frame the bag touches the board or ground.
5. Click 'Download annotation JSON' and move the file INTO that clip's folder.

Second rater: please do the 5 clips marked * independently (do not look at the first rater's file).

  Clip                  Player      Folder            Frames
* testsep17 - 1.mov     Player-1    Throw-19A9640F    20
  testsep17 - 2.mov     Player-1    Throw-44CA1279    20
  testsep17 - 3.mov     Player-1    Throw-80823323    20
  testsep17 - 4.mov     Player-1    Throw-3B3DC0EC    19
  testsep17 - 5.mov     Player-1    Throw-3D93058B    19
  testsep17 - 6.mov     Player-1    Throw-41A04DAC    20
  testsep17 - 7.mov     Player-1    Throw-1500778E    15
* testsep17 - 8.mov     Player-1    Throw-F0E77C58    20
  testsep17 - 9.mov     Player-1    Throw-D7FAAA60    20
* testsep17 - 10.mov    Player-2    Throw-D4FF5A49    20
  testsep17 - 11.mov    Player-2    Throw-126CCAD1    20
  testsep17 - 12.mov    Player-2    Throw-105B9972    20
  testsep17 - 13.mov    Player-2    Throw-DB5A8186    20
  testsep17 - 14.mov    Player-2    Throw-EFFA8D86    19
  testsep17 - 15.mov    Player-2    Throw-5B5C77D7    20
  testsep17 - 16.mov    Player-3    Throw-6BD2EE8F    20
  testsep17 - 17.mov    Player-3    Throw-14A6C444    20
* testsep17 - 18.mov    Player-3    Throw-3B1EF3CA    20
  testsep17 - 19.mov    Player-3    Throw-08541449    20
  testsep17 - 20.mov    Player-3    Throw-DE7F5B7D    20
  testsep17 - 21.mov    Player-3    Throw-AA7AC4A3    20
* testsep17 - 22.mov    Player-3    Throw-A21B263C    19
  testsep17 - 23.mov    Player-3    Throw-E0D8F3B9    20
  testsep17 - 24.mov    Player-3    Throw-BE2292C2    14
  testsep17 - 25.mov    Player-3    Throw-8D96BCAF    20
  testsep17 - 26.mov    Player-3    Throw-62AA318D    20

When done, the scoring command is in the guide (bag-benchmark).
