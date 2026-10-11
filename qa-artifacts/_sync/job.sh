export PYTHONPATH=python MPLCONFIGDIR="${TMPDIR:-/tmp}/cornhole-mpl"
PY=.venv/bin/python
LIB="$HOME/Documents/Cornhole Biomechanics Lab Data"
OUT=qa-artifacts/_sync/real
mkdir -p "$OUT"
echo "=== python tests $(date)"
$PY -m pytest tests -q 2>&1 | tail -5
echo "=== re-analyse all athletes, one throw at a time (side, pooled side, front, front lag) $(date)"
$PY scripts/analyze_library.py --library "$LIB" --athlete all 2>&1 | grep --line-buffered -aE "^[0-9]{2}:[0-9]{2}:[0-9]{2}|Traceback|Error"
for P in "Player 1" "Player 2" "Player 3" "Player 4"; do
  $PY scripts/summarize_two_view.py --library "$LIB" --athlete "$P" > "$OUT/summary-${P// /-}.txt" 2>&1
done
$PY scripts/summarize_two_view.py --library "$LIB" > "$OUT/summary-all.txt" 2>&1
echo "=== front lag check $(date)"
python3 qa-artifacts/_sync/lagstats.py "$LIB" | grep "median"
echo "=== app build $(date)"
./build_app.sh 2>&1 | tail -3
echo "=== finished $(date)"; tail -1 "$OUT/summary-all.txt"
