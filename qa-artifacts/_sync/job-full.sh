export PYTHONPATH=python MPLCONFIGDIR="${TMPDIR:-/tmp}/cornhole-mpl"
PY=.venv/bin/python
LIB="$HOME/Documents/Cornhole Biomechanics Lab Data"
SRC="data/videos/Final Data Collection"
OUT=qa-artifacts/_sync/real
mkdir -p "$OUT"
echo "--- clearing the half-built library from the stopped run"
rm -rf "$LIB/Athletes/"Player-* "$LIB/project.json" "$LIB/project.json.tmp"
echo "--- library before"; ls -la "$LIB" 2>&1 | head
cat "$LIB/project.json" 2>/dev/null; echo
if [ -f "$LIB/project.json" ] && ! $PY -c "import json,sys; p=json.load(open(sys.argv[1])); sys.exit(1 if (p.get('athletes') or p.get('trials')) else 0)" "$LIB/project.json"; then echo "Library already has athletes; stopping so nothing is overwritten."; exit 1; fi
echo "--- app build"; ./build_app.sh 2>&1 | tail -2
for P in "Player 1" "Player 4" "Player 2" "Player 3"; do
  echo "=== $P: prepare $(date)"
  $PY scripts/add_takes_to_library.py --library "$LIB" --athlete "$P" --folder "$SRC/$P" 2>&1 | grep --line-buffered -av "it/s"
  echo "=== $P: analyse $(date)"
  $PY scripts/analyze_library.py --library "$LIB" --athlete "$P" 2>&1 | grep --line-buffered -aE "^[0-9]{2}:[0-9]{2}:[0-9]{2}|Traceback|Error" 
  $PY scripts/summarize_two_view.py --library "$LIB" --athlete "$P" > "$OUT/summary-${P// /-}.txt" 2>&1
  echo "=== $P: done $(date)"; tail -1 "$OUT/summary-${P// /-}.txt"
done
echo "=== all athletes: pool the camera set-ups and refresh $(date)"
$PY scripts/analyze_library.py --library "$LIB" --athlete all 2>&1 | grep --line-buffered -aE "^[0-9]{2}:[0-9]{2}:[0-9]{2}|Traceback|Error"
$PY scripts/summarize_two_view.py --library "$LIB" > "$OUT/summary-all.txt" 2>&1
echo "=== finished $(date)"; tail -1 "$OUT/summary-all.txt"
