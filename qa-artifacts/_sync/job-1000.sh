export PYTHONPATH=python MPLCONFIGDIR="${TMPDIR:-/tmp}/cornhole-mpl"
PY=.venv/bin/python
LIB="$HOME/Documents/Cornhole Biomechanics Lab Data"
OUT=qa-artifacts/_sync/real
mkdir -p "$OUT"
echo "=== python tests $(date)"
$PY -m pytest tests -q -x 2>&1 | tail -25
echo "=== swift build $(date)"
(cd app/CornholeBiomechanics && swift build 2>&1 | grep -E "error|warning: unre|Compiling|Build complete" | grep -v "^\[" | head -80) > qa-artifacts/_sync/swift-build.txt 2>&1
cat qa-artifacts/_sync/swift-build.txt | grep -E "error|Build complete" | head -60
echo "=== re-analyse all athletes, one throw at a time $(date)"
$PY scripts/analyze_library.py --library "$LIB" --athlete all 2>&1 | grep --line-buffered -aE "^[0-9]{2}:[0-9]{2}:[0-9]{2}|Traceback|Error"
for P in "Player 1" "Player 2" "Player 3" "Player 4"; do
  $PY scripts/summarize_two_view.py --library "$LIB" --athlete "$P" > "$OUT/summary-${P// /-}.txt" 2>&1
done
$PY scripts/summarize_two_view.py --library "$LIB" > "$OUT/summary-all.txt" 2>&1
echo "=== finished $(date)"; tail -1 "$OUT/summary-all.txt"
