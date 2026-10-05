# Cornhole Biomechanics Lab — project context

## What this is
A native macOS app (SwiftUI) with a Python science engine. It turns one side-camera phone video of a cornhole throw into release physics, body mechanics, an outcome, and coaching feedback. Everything runs locally on the Mac.

Built for **Biomechanics of Human Movement (Vanderbilt, Fall 2026), Project 1**, taught by Prof. Zelik.
Team: Berk Kasimcan, John Wilson, Eliam Chang, Emily Park. Repo: github.com/Berkonas/CornHoleBiomech

## What we are trying to achieve
The brief (realistic fiction): Vanderbilt Athletics is starting a cornhole team, and the coach wants an evidence-based training-analytics system. The course requires that the system:
- **links how the movement is done to the outcome it produces.** Tracking or scoring alone is not enough.
- **turns that link into feedback** that actually helps a coach or athlete train in a more targeted way (and, as a bonus, helps evaluate recruits).
- runs on **real data from real participants** with equipment we can realistically get. No sensors on or in the bag.
- states its **limitations, uncertainty and risks**, and compares against other approaches with credible references.

Final deliverables: a client report plus a live or recorded demo of the prototype measuring a real person. In the Q&A the team must be able to explain and defend every decision. So the code must stay explainable, and every number must be traceable to a method in `docs/`.

The core chain the app shows: **body → release → flight → outcome → advice.**

## Architecture
- `app/CornholeBiomechanics/` holds the Swift package (Swift 6.2, macOS 15+).
  - `Sources/CornholeBiomechanics/` is the coach app: athlete library (`ProjectStore.swift`), throw report, athlete summary, Launch Lab, board outcome, charts.
  - `Sources/SceneVision/` is a small Apple Vision helper that makes person masks so bystanders are boxed out of the bag search.
  - `AnalysisService.swift` runs the Python engine as a worker process. The engine streams JSON-line progress and writes CSV/JSON/plots for each throw.
- `python/cornhole_biomech/` is the engine. Key modules:
  - pose: `sports2d_adapter.py`, `pose.py`, `filtering.py` (Sports2D/RTMPose, 6 Hz Butterworth)
  - bag: `auto_bag.py`, `bag*.py`, `flight.py` (gravity-gated parabola fit, Kalman/RTS smoother)
  - board and scale: `board.py`, `board_phase.py`, `scene.py`, `geometry.py` (PnP homography, gravity-calibrated px/m)
  - events and chain: `events.py`, `chain.py`, `chain_analysis.py`, `swing.py`, `arm_motion.py`
  - model and advice: `trajectory_model.py` (drag-free flight), `zones.py` (personal green zone), `verdict.py`, `corrections.py`, `coaching.py`, `insights.py`
  - stats: `statistics.py`, `performance.py`, `reliability.py`
  - orchestration: `pipeline.py`, `cli.py`
- `tests/` has about 440 pytest tests. `scripts/` has setup, build, library, regression and QA tools. `tools/annotator.html` does blinded manual annotation.
- `docs/` is the source of truth for methods. Start with `METHODS_AND_MATH.md`, `METRICS.md`, `FEEDBACK_RESPONSE.md` and `APP_GUIDE.md`. Design specs and plans are in `docs/superpowers/`.

## Commands (macOS, zsh)
```bash
./setup.sh                 # once per Mac: Python runtime + pose models (.venv is a symlink into ~/Library/Application Support)
PYTHONPATH=python .venv/bin/python -m pytest tests     # Python tests (fast; run after any engine change)
./verify.sh                # full check: pytest + swift test + SceneVision build + schema fixtures + signed build
./build_app.sh             # build and install the app; dist/ links to it
PYTHONPATH=python .venv/bin/python -m cornhole_biomech analyze clip.mov --output out/ --trial-id t1 --athlete-id p1 --view side --throwing-side right --target-direction left_to_right
```
Only one analysis may run at a time. Full-library runs have crashed the Mac before, and the app queue plus the engine lock exist for that reason. Don't parallelize video analysis.

## Ground rules (scientific and code)
- **Missing stays missing.** Report `unavailable` with a reason. Never fill a gap with zero or a guess.
- Every metric carries a status (`measured` / `estimated` / `unavailable`), a GOOD/WARNING/POOR grade, and an uncertainty where possible.
- Any new threshold, gate or filter cut-off needs justification in `docs/` (a reference or pilot evidence).
- Associations are not causes. Coaching wording must match the evidence gate (≥ 5 throws per group, Cliff's δ ≥ 0.474, difference > measurement noise).
- Outcome first: a made throw gets no corrections. Advice for misses comes from where the bag actually stopped (signed short/long).
- When a method, metric or threshold changes, update the matching doc (usually `METHODS_AND_MATH.md` or `METRICS.md`) in the same change.
- Python and Swift must agree. Swift reads engine outputs, so check `tests/swift_contract.py` and the replay/schema tests when changing output fields.
- Coach-facing text stays plain and short: one sentence per throw, no jargon.

## Known limits and open work (good places to improve)
- Side-only throws are projected 2D with no left/right. **Two-camera takes** (side + front, `takes.py`, `front_view.py`, `two_view.py`, METHODS_AND_MATH §5) add left/right, heading, hole/board/off and frontal-plane body. Sync is from sound (±17.5 ms).
- The flight model is drag-free. One camera can't separate drag from motion toward or away from the lens.
- Release-frame timing can be off by a few frames on some throws (see `docs/superpowers/2026-09-23-measurement-engine-rulings.md`).
- Parked items in that rulings file (`recording_date` now exists for two-camera takes): no registration-quality flag on accepted flights, flight-review save drops the automatic contact, Vision person-mask recall around 55%.
- More real throws per athlete are needed. The target is 20–40.

## Data and privacy
Never commit participant video, real names, course PDFs or model weights. `data/`, `research/`, `qa-artifacts/` and model files are git-ignored. Use codes like `Player 1` in examples and fixtures. The athlete library lives outside the repo (normally `~/Documents/Cornhole Biomechanics Lab Data`). Don't hand-edit it.

## Git
Branch from `main` (`name/short-topic`), keep commits focused, and write messages as what the change does. A teammate reviews each PR. CI runs pytest on Python 3.11 and 3.12. Current version: 0.6.2.
