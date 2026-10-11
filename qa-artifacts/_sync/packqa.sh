# Pack the QA sample: analysis outputs (json/csv/jpg) + side/front clips + take record + front reference.
cd "$HOME/mnt/Cornhole Biomechanics Lab Data"
LIST="Athletes/Player-1-93B49584/analyses/Throw-D2305B00 Athletes/Player-1-93B49584/analyses/Throw-A3029AB3 Athletes/Player-2-72B0049F/analyses/Throw-C031BF67 Athletes/Player-2-72B0049F/analyses/Throw-188B1BD3 Athletes/Player-3-A0E58E0B/analyses/Throw-1C97BD64 Athletes/Player-3-A0E58E0B/analyses/Throw-3242FE1B Athletes/Player-4-5616D09A/analyses/Throw-7796ECB2 Athletes/Player-4-5616D09A/analyses/Throw-89A82950"
FILES=""
for d in $LIST; do
  for f in results.json two_view.json auto_flight.json events.json replay.json take_link.json manifest.json keypoints.csv kinematics.csv plate.jpg front_pose_raw.json; do
    [ -f "$d/$f" ] && FILES="$FILES $d/$f"
  done
  rec=$(python3 -c "import json,sys,os;l=json.load(open('$d/take_link.json'));print(os.path.normpath(os.path.join('$d',l['take_record'])))")
  n=$(python3 -c "import json;print('%02d'%json.load(open('$d/take_link.json'))['throw_number'])")
  tdir=$(dirname "$rec")
  FILES="$FILES $rec $tdir/throw_${n}_side.mp4 $tdir/throw_${n}_front.mp4"
  for r in $tdir/front_reference.png; do FILES="$FILES $r"; done
done
tar czf "$HOME/mnt/Project 1 - Cornhole/qa-artifacts/_sync/qa8.tgz" $(echo $FILES | tr ' ' '\n' | sort -u) && ls -la "$HOME/mnt/Project 1 - Cornhole/qa-artifacts/_sync/qa8.tgz"
