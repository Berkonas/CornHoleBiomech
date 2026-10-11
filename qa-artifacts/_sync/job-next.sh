export PYTHONPATH=python MPLCONFIGDIR="${TMPDIR:-/tmp}/cornhole-mpl"
PY=.venv/bin/python
LIB="$HOME/Documents/Cornhole Biomechanics Lab Data"
SRC="data/videos/Final Data Collection"
OUT=qa-artifacts/_sync/real
mkdir -p "$OUT"
for P in "Player 4" "Player 2" "Player 3"; do $PY scripts/remove_athlete.py --library "$LIB" --athlete "$P"; done
for P in "Player 4" "Player 2" "Player 3"; do
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
echo "=== tests and app build $(date)"
$PY -m pytest tests -q 2>&1 | tail -3
./build_app.sh 2>&1 | tail -3
echo "=== git $(date)"
git status --short | head -80
git diff --stat | tail -3
echo "=== finished $(date)"; tail -1 "$OUT/summary-all.txt"
