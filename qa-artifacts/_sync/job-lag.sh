export PYTHONPATH=python MPLCONFIGDIR="${TMPDIR:-/tmp}/cornhole-mpl"
PY=.venv/bin/python
LIB="$HOME/Documents/Cornhole Biomechanics Lab Data"
OUT=qa-artifacts/_sync/real
echo "=== tests $(date)"
$PY -m pytest tests -q 2>&1 | tail -3
echo "=== lag before (from the last front pass) $(date)"
python3 qa-artifacts/_sync/lagstats.py "$LIB" | grep "median"
$PY -c "
import json,sys
from pathlib import Path
from cornhole_biomech.two_view import pool_front_lag, TAKE_LINK_FILENAME
root=Path(sys.argv[1]); p=json.loads((root/'project.json').read_text())
dirs=[root/t['analysisRelativePath'] for t in p['trials'] if t.get('analysisRelativePath') and (root/t['analysisRelativePath']/TAKE_LINK_FILENAME).exists()]
print(pool_front_lag(dirs))" "$LIB"
echo "=== front camera again with the lag, one throw at a time $(date)"
$PY scripts/analyze_library.py --library "$LIB" --athlete all --front-only 2>&1 | grep --line-buffered -aE "^[0-9]{2}:[0-9]{2}:[0-9]{2}|Traceback|Error"
for P in "Player 1" "Player 2" "Player 3" "Player 4"; do
  $PY scripts/summarize_two_view.py --library "$LIB" --athlete "$P" > "$OUT/summary-${P// /-}.txt" 2>&1
done
$PY scripts/summarize_two_view.py --library "$LIB" > "$OUT/summary-all.txt" 2>&1
echo "=== lag after $(date)"
python3 qa-artifacts/_sync/lagstats.py "$LIB" | grep "median"
echo "=== app build $(date)"
./build_app.sh 2>&1 | tail -3
echo "=== finished $(date)"; tail -1 "$OUT/summary-all.txt"
