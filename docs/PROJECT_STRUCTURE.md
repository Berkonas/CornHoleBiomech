# Project structure and data locations

**Audited 8 September 2026.** The software repository and the athlete data library are deliberately separate. A coach should normally interact with **Athletes, References, Throws, Sessions, and Results** in the app—not with source folders or `.cornholeproject` internals.

## 1. Source repository

The maintained top-level structure is:

```text
Project 1 - Cornhole/
├── README.md                  Start here
├── app/                       Native macOS Swift package/application
├── python/                    Python biomechanics and analysis engine
├── tests/                     Python software/scientific tests
├── scripts/                   Setup, build, QA, and validation utilities
├── docs/                      Current user, methods, validation, and verification docs
├── resources/branding/        Editable brand/icon sources
├── pyproject.toml             Python package and pinned dependencies
├── setup.sh                   Compatibility entry point -> scripts/setup.sh
├── build_app.sh               Compatibility entry point -> scripts/build_app.sh
├── run_app.sh                 Compatibility entry point -> scripts/run_app.sh
└── verify.sh                  Non-participant-data verification entry point
```

The root wrapper scripts are intentional: they keep the documented three-command setup stable while implementations live under `scripts/`. Moving the existing Swift or Python packages would create path risk without helping a coach, so their internal locations remain unchanged.

`docs/archive/` contains historical audit/plan records. They explain earlier decisions but are not the current methods, validation plan, or verification status.

## 2. Visible athlete library

On first launch, the app creates or opens a user-visible managed library. The default is:

```text
~/Documents/Cornhole Biomechanics Lab Data/
```

The user may choose another local folder. The current managed layout is:

```text
Cornhole Biomechanics Lab Data/
├── project.json                         Versioned library index
├── migration-log.json                   Present after legacy import
├── Athletes/
│   └── Athlete-Name-UUIDPREFIX/
│       ├── profile.json                 Human-readable athlete metadata
│       ├── throws/
│       │   └── UUIDPREFIX-original.mp4  Imported source-video copy
│       └── analyses/
│           └── Throw-UUIDPREFIX/        Derived data, figures, and reports
├── References/                          Managed external reference assets, when used
├── comparisons/                         Derived comparison packages
├── relationships/                       Derived repeated-throw analyses
└── exports/                             Exports explicitly created by the user
```

The UUID suffix prevents two athletes or throws with the same display name from colliding. Files inside the library are referenced by contained relative paths, not developer-machine absolute paths. Athlete edits update the readable folder/profile while preserving stable IDs.

The app imports a video by **copying** it into the athlete's `throws/` folder. The original selected file is not modified. Analysis output is derived and may be regenerated; it remains separate from the managed source-video copy.

## 3. Small Application Support index

The app stores only library/runtime state under:

```text
~/Library/Application Support/Cornhole Biomechanics Lab/
├── library-location.json
└── Runtime/                 Installed local Python runtime, when setup creates it
```

`library-location.json` stores schema version, library/project ID, visible data-root path, security-scoped bookmark when available, selected athlete/trial/session/reference IDs, and save time. It lets the same library and selection reopen after relaunch. Writes are atomic.

The scientific dataset is **not** hidden in Application Support. If the saved library cannot be resolved, the app retains the expected location, shows that the library is missing, and asks the user to locate/open it rather than creating an apparently empty replacement.

Development-only environment overrides are `CORNHOLE_APP_SUPPORT_ROOT` and `CORNHOLE_LIBRARY_ROOT`; they allow isolated persistence tests without touching a person's real library.

## 4. Missing files, relinking, and Finder

Each throw distinguishes available, missing, and unassigned source-video state. A moved file remains a throw record marked **Missing file**. **Locate / Relink** accepts a replacement path; an external replacement is copied into the managed athlete library, while an already-contained path stays relative.

Reveal actions open the selected library, athlete folder, or source video in Finder. Paths are validated to stay inside the managed root before derived data are opened, moved, or deleted.

## 5. Deletion semantics

Destructive UI actions require a confirmation that names affected records. Data rules are:

- deleting an analysis removes derived analysis/comparison files but preserves the source video;
- removing a reference assignment or deleting a reference set preserves source throws/videos;
- deleting a session removes the grouping record but preserves its throws/videos;
- deleting a throw removes that managed copy and its derived results;
- deleting an athlete reports affected sessions/throws/results and removes that athlete's managed files;
- filesystem removals are staged and moved to macOS Trash when possible; if Trash fails, the recoverable staging location is reported.

The app never silently deletes a raw external original. Back up the visible library before large studies or migrations.

## 6. Legacy `.cornholeproject` migration

The app can open a current library or import an older `.cornholeproject` into the active athlete library. Import behavior is non-destructive:

- the original legacy folder is unchanged;
- athlete/session/trial UUIDs are preserved where possible;
- videos and analyses are copied without overwriting an existing destination;
- missing source/analysis files create warnings and retained records for relink/reanalysis;
- legacy reference flags become a provenance-labeled reference set;
- `migration-log.json` records source ID/path/schema/update time, imported IDs, warnings, and recheck time;
- repeating the same import is idempotent and does not duplicate known IDs.

At audit time, three legacy manifests named “Cornhole Study” existed in the repository area. They had distinct IDs/timestamps and contained no athletes, sessions, or trials. Five unique MP4 files existed in the literal path below; the space after `Reference` is part of the directory name:

```text
Participant/Reference /Cornhole Study.cornholeproject/videos/
```

These are user-owned inputs. They were not deleted, renamed, or treated as consented course data. The app's import/migration path—not a manual filesystem rewrite—should bring any wanted data into the managed library.

## 7. Local source material

`reference_materials/course/` contains the two legitimate local course PDFs. `reference_materials/` is excluded from Git so course and user-owned material is not redistributed.

Untracked books/partial downloads under `reference_materials/books/` and `reference_materials/design/` are opaque user-owned files: the application does not read, bundle, cite, or depend on them. `reference_materials/design/DESIGN_RESEARCH.md` was identified as unrelated research for a “Places” product. It is excluded from the maintained evidence base and should remain outside current documentation; no unofficial book was opened to make that determination.

## 8. Generated and cleanup candidates

| Path/type | Classification | Decision |
|---|---|---|
| `app/CornholeBiomechanics/.build/` | Swift build cache | Ignore; safe to regenerate; never source or participant data. |
| `dist/*.app` | Built release bundle | Ignore. Keep only the current named bundle during normal development; rebuild when needed. |
| `.venv` and runtime environments | Local dependencies/symlink | Ignore; recreate with `setup.sh`; never commit. Remove stale duplicate environments only after resolving the active runtime. |
| `.pytest_cache/`, `__pycache__/`, `*.pyc` | Test/interpreter cache | Ignore; disposable. |
| `python/*.egg-info/` | Generated package metadata | Ignore; regenerate during install. |
| `models/`, `*.task`, `*.onnx` | Downloaded/locally installed model weights | Ignore; preserve hashes in analysis manifests, not model binaries in Git. |
| `.DS_Store` | Finder metadata | Ignore; disposable. |
| `qa-artifacts/`, temporary `/tmp` projects | Generated QA evidence/fixtures | Ignore unless an intentionally redacted durable report is added; never confuse with participant data. |
| `Participant/` and `.cornholeproject` inputs | User-owned scientific/legacy data | Preserve; do not mass-delete or commit; migrate/import explicitly. |
| `docs/archive/` | Historical documentation | Retain for provenance, clearly non-current. |
| root setup/build/run scripts | Compatibility interface | Retain. |

Generated size is not repository architecture. Build caches and releases can dominate disk usage without belonging in the maintained project tree.

## 9. Canonical documentation map

- [USER_GUIDE.md](USER_GUIDE.md): coach/researcher workflow.
- [BIOMECHANICS_METHODS.md](BIOMECHANICS_METHODS.md): equations, units, coordinate systems, and limits.
- [RESEARCH_BACKGROUND.md](RESEARCH_BACKGROUND.md): why, questions, and evidence matrix.
- [VALIDATION_PLAN.md](VALIDATION_PLAN.md): evidence still required and how to collect it.
- [VERIFICATION.md](VERIFICATION.md): checks actually run, at a named commit/date.
- [REFERENCES.md](REFERENCES.md): maintained bibliography.
- [SPORTS2D.md](SPORTS2D.md): version-locked upstream integration contract.

Legacy filenames `METRICS.md`, `VALIDATION_PROTOCOL.md`, `QA.md`, and `REPOSITORY_INVENTORY.md` remain as short compatibility pointers or historical run records so existing links do not break.
