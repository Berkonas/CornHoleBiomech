"""Per front set-up: first on-deck frame in the front camera minus the side contact mapped by sound."""
import json, statistics, sys, collections
from pathlib import Path
root = Path(sys.argv[1])
project = json.loads((root / "project.json").read_text())
codes = {a["id"]: a.get("participantCode") for a in project["athletes"]}
groups = collections.defaultdict(list)
for t in project["trials"]:
    if t.get("takeNumber") is None or not t.get("analysisRelativePath"):
        continue
    folder = root / t["analysisRelativePath"]
    try:
        tv = json.loads((folder / "two_view.json").read_text())
        link = json.loads((folder / "take_link.json").read_text()) if (folder / "take_link.json").exists() else {}
    except Exception:
        continue
    take = {}
    for name in folder.glob("*.json"):
        pass
    fr = tv.get("frames") or {}
    sc = tv.get("sync_check") or {}
    rec = (folder / link.get("take_record", "x")).resolve() if link else None
    front = {}
    if rec and rec.exists():
        front = json.loads(rec.read_text()).get("front") or {}
    key = f"{front.get('model')} {front.get('recorded')}"
    groups[key].append((codes.get(t["athleteID"]), t.get("takeNumber"), t.get("throwInTake"), sc.get("front_frames_difference"),
                        fr.get("contact_source"), (tv.get("result") or {}).get("category")))
for key, rows in groups.items():
    d = [r[3] for r in rows if r[3] is not None]
    print(key, "n", len(rows), "measured", len(d), "median", statistics.median(d) if d else None,
          "hist", dict(collections.Counter(d)))
    for r in rows:
        print("   ", r)
