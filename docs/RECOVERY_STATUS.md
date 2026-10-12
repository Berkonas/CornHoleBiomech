# Recovery status (2026-10-11)

Evidence-based status of the work reported by earlier sessions, checked against the repository on 2026-10-11.
Each status cites what was checked. "Reported" claims that could not be confirmed are marked as such.

## Repository and synchronisation

| Item | Status | Evidence |
|---|---|---|
| Local repo at `~/GitHub/CornHoleBiomech`, remote `Berkonas/CornHoleBiomech` | Completed and verified | `git remote -v`; `git fetch` succeeds |
| `main` | Up to date with `origin/main` at `7e61b4d9` | `git rev-list --left-right --count main...origin/main` = 0/0 |
| `berk/two-camera-takes` | Fully merged into `main` (via `berk/final-integration`, `8597128a`) | `git merge-base --is-ancestor` |
| `claude/board-phase-green-zone` | Fully merged into `main` | `git merge-base --is-ancestor` |
| `berk/coach-feedback` | 3 commits ahead of `main` (calculation audit, miss attribution, app screens), pushed as `719021d6` | `git rev-list` 0/3; matches `origin/berk/coach-feedback` |
| Swift build fix (`fix.diff`) | Recovered from `.local/fix.diff`, committed locally as `be0c3427`; **not pushed** | push fails: no GitHub credentials available to command-line git |
| Git LFS | Configured; 1,925 objects present locally; 213 not downloaded (pilot library backup, `data/videos/Player`, `Pro reference`, QA renders) | sample `git lfs pull` of `Pro reference` succeeded, so those objects are on GitHub |
| Final Data Collection videos | 46 `.mov` files (4 players), tracked in LFS and present locally | `git lfs ls-files` |
| Queue helper (`Claude Helper.command`, `.local/watcher.command`) | Not running; one stale job (`build2.sh`) left unrun. No longer needed: command-line git works directly | `ps`, `.local/queue/watcher.log` |
| Desktop launcher | Symlink to `dist/Cornhole Biomechanics Lab.app`, built 2026-10-10 23:44, i.e. **before** the coach-feedback work | `readlink`, `stat` |
| Old Desktop project folder | No longer exists | `ls` |

## Publishing and licensing (needs a decision)

- The GitHub repository is **public** (`api.github.com` reports `visibility: public`).
- The 46 participant recordings in `data/videos/Final Data Collection` are published through LFS. `CLAUDE.md` records the owner's approval to publish project videos; the four athletes' own consent to public sharing is not recorded in the repository.
- Commit `7e61b4d9` stopped tracking the copyrighted books and course handouts, but 576 of those files remain downloadable from the history of commit `01e3c8ed`. Removing them needs a history rewrite and force-push, which has not been done.

## Development work

| Task | Status | Evidence |
|---|---|---|
| Two-camera takes: sound sync, throw finding, front landing, combined result | Implemented, on `main` | commits `8f5df0fb`…`2544dce4`; tests pass |
| 3D flight from both cameras (`flight3d.py`) | Implemented, on `main`; real-video accuracy unverified | `tests/test_flight3d.py` passes |
| Reported "92-throw run" | Not re-verified (outside this phase's scope) | — |
| Shoulder-angle fold, motion-end trim, negative slide friction | Implemented and unit-tested on `berk/coach-feedback` | `tests/test_calculation_audit.py` |
| Miss attribution (left/right, short/long) | Implemented and unit-tested; needs critical scientific review | `attribution.py`, `tests/test_attribution.py` |
| Take screen, import queue, Needs-your-eye inbox, throw report, synced replay | Implemented; compiles after the fix; not yet exercised in the running app | `TakeView.swift`, `ReviewInboxView.swift`, etc. |
| Swift compilation | Completed and verified locally | `swift build`: 0 errors, 0 warnings |
| Python tests | Completed and verified: **630 passed** | `pytest` |
| Swift tests | Completed and verified: 86 executed, 3 skipped, 0 failures | `swift test` with the Xcode toolchain |
| Plane-fit release speed (`bag.plane_launch_fit`) | **Partially implemented**: function and test exist, not called by `pipeline.py` | `CALCULATION_AUDIT.md` D2; `grep` |
| Front-camera airborne tracking | Partially implemented: a physics-constrained 3D line fit exists; standalone front tracking is documented as fragile | `flight3d.py`, `front_track.py` |
| Landing tracking improvements | Partially implemented | to be reviewed in Phase 2 |
| Scientific validation plan | Not started | no plan document found |
| Merge of `berk/coach-feedback` into `main` | Not started | — |

## Progress on 2026-10-12

Each change below has targeted tests; the full suites pass (644 Python, 87 Swift). No video was processed.

| Change | Commit |
|---|---|
| Plane-fit release speed and angle wired into the pipeline when the board plane is the scale | `e7d8534f` |
| A person's result is never reverted by re-analysis (explicit `source`); Off clears a camera rest point; outcome.json uses the current outcome | `1170ea66` |
| Miss attribution: per-throw deck-contact carry sensitivity (≈ 1.33, not 1.8 m per m/s); no pooling across method versions | `1002c3f6` |
| Front camera: a deck track that turns onto a knocked bag, or two new bags on the deck, needs confirmation | `797e8ad0` |
| 3D flight: timing offset no longer added to the side contact time; fits pinned at a bound are `estimated` | `e57a93d2` |
| Sound sync scores every lag exactly; front clip rate from the frame spacing | `551bc442` |
| Shoulder angle: foreshortened frames missing, continuous across the cut; no velocity on unfiltered short runs | `477b4d99` |
| Statistics: coach message states the group size a difference really needs; outcome links respect noise floors | `ece4f1b0` |
| App: result edits and Add Athlete during the queue; stale analyses kept out of the inbox; atomic engine writes | `8049c46f` |

The Desktop launcher points to `dist/`, rebuilt from `8049c46f` on 2026-10-12 and signature-verified.

### Still open

- **GitHub push and PR: blocked.** Command-line git has no GitHub credentials, so the commits above are local only.
- **Copyrighted books in history** (commit `01e3c8ed`) and the athletes' consent for public videos: owner decision.
- Side camera board phase can re-acquire a knocked bag's vacated spot (`board_phase.py`, found by reading the code, not yet reproduced).
- App: outcome change history and undo, take ↔ report navigation (previous/next bag), dashed drawing of estimated launch lines in the top view, report files loaded off the main thread.
- Slide-friction SE gate is optimistic near its threshold; serial dependence within a session is not modelled.
- Validation plan for the real-video run: not written yet.
