#!/bin/zsh
# Read-only environment probe for the two-camera update (writes qa-artifacts/_sync/probe.log).
cd "${0:A:h}/../.."
LOG="qa-artifacts/_sync/probe.log"
{
echo "=== probe $(date)"; sw_vers; uname -m; sysctl -n hw.memsize hw.ncpu
echo "--- tools"; for t in ffmpeg ffprobe avconvert afconvert afinfo swift xcrun; do echo "$t: $(command -v $t)"; done
swift --version 2>&1 | head -2
echo "--- venv"; ls -la .venv; .venv/bin/python --version
.venv/bin/python -m pip list 2>/dev/null | grep -i -E "opencv|numpy|scipy|sports2d|pose2sim|rtmlib|onnx|imageio|av |soundfile|librosa|matplotlib|pandas|torch"
.venv/bin/python -c "import imageio_ffmpeg; print('imageio_ffmpeg', imageio_ffmpeg.get_ffmpeg_exe())" 2>&1 | tail -1
.venv/bin/python - <<'PY'
import cv2, numpy as np, tempfile, os
print('cv2', cv2.__version__)
for cc in ['avc1','hvc1','mp4v','H264']:
    p=tempfile.mktemp(suffix='.mp4'); w=cv2.VideoWriter(p, cv2.VideoWriter_fourcc(*cc), 30, (640,360))
    ok=w.isOpened()
    if ok:
        for i in range(10): w.write(np.full((360,640,3), i*20, np.uint8))
    w.release(); sz=os.path.getsize(p) if os.path.exists(p) else 0
    print('writer', cc, ok, sz)
bi=cv2.getBuildInformation(); i=bi.find('Video I/O'); print(bi[i:i+600])
PY
echo "--- rtmlib cache"; ls ~/.cache/rtmlib/hub/checkpoints 2>&1 | head
echo "--- libraries"; ls -la ~/Documents | grep -i corn; ls -la ~/Documents/"Cornhole Biomechanics Lab Data" 2>&1 | head; 
python3 - <<'PY'
import json, os
p=os.path.expanduser('~/Documents/Cornhole Biomechanics Lab Data/project.json')
if os.path.exists(p):
    d=json.load(open(p)); print('athletes', [(a['participantCode'], a['id'][:8]) for a in d['athletes']]); print('trials', len(d['trials']), 'sessions', len(d.get('sessions') or []))
    from collections import Counter; print(Counter(t['athleteID'][:8] for t in d['trials']))
PY
ls ~/Library/Application\ Support/Cornhole\ Biomechanics\ Lab/ 2>&1
cat ~/Library/Application\ Support/Cornhole\ Biomechanics\ Lab/*.json 2>/dev/null | head -20
echo "--- afconvert test"; afconvert -f WAVE -d LEI16@16000 -c 1 "data/videos/Final Data Collection/Player 1/Take_1_Side.mov" /tmp/probe_a.wav && afinfo /tmp/probe_a.wav | head -5
echo "=== done"
} > "$LOG" 2>&1
echo "Probe finished. You can close this window."
