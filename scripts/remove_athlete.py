#!/usr/bin/env python3
"""Remove one athlete and everything recorded for them from a library (throws, sessions, takes, analyses).

Used to rebuild an athlete from scratch after the take preparation changed:

  PYTHONPATH=python .venv/bin/python scripts/remove_athlete.py --library <library> --athlete "Player 4"

The original videos are never touched (the library only holds copies and clips).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--athlete", required=True)
    args = parser.parse_args()
    root = args.library.expanduser().resolve()
    path = root / "project.json"
    project = json.loads(path.read_text())
    athlete = next((a for a in project.get("athletes", []) if a.get("participantCode") == args.athlete), None)
    if athlete is None:
        print(f"No athlete {args.athlete!r}; nothing to remove.")
        return
    aid = athlete["id"]
    project["athletes"] = [a for a in project["athletes"] if a["id"] != aid]
    project["trials"] = [t for t in project.get("trials", []) if t.get("athleteID") != aid]
    project["sessions"] = [s for s in project.get("sessions") or [] if s.get("athleteID") != aid]
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(project, indent=2))
    temporary.replace(path)
    slug = "-".join(p for p in re.split(r"[^A-Za-z0-9]+", args.athlete) if p)
    for folder in (root / "Athletes").glob(f"{slug}-{aid[:8]}"):
        shutil.rmtree(folder)
    dashboard = root / "dashboards" / f"{aid}.json"
    if dashboard.exists():
        dashboard.unlink()
    print(f"Removed {args.athlete} ({aid[:8]}).")


if __name__ == "__main__":
    main()
