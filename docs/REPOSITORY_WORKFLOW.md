# Repository workflow and storage

The working copy is `~/GitHub/CornHoleBiomech`. GitHub stores committed versions;
the macOS application and analysis workers execute on your Mac. A push does not
build or launch the app, and opening the app does not automatically commit changes.

## Where files live

| Path inside the checkout | Purpose |
| --- | --- |
| `app/`, `python/`, `scripts/`, `tests/`, `docs/` | App source, science engine, tooling, tests and documentation |
| `dist/Cornhole Biomechanics Lab.app` | Generated signed app; rebuilt from source |
| `.venv/` | Local Python environment; recreated by setup on each Mac |
| `data/libraries/Cornhole Biomechanics Lab Data/` | Main imported athlete library |
| `data/libraries/Cornhole Pilot Library*/` | Preserved pilot library and backup |
| `data/videos/`, `research/`, `qa-artifacts/` | Original recordings, project references and analysis/QA outputs |
| `.local/app-support/` | This Mac's selected-library index and preferences |
| `.local/legacy-support/`, `.local/previous-swift-build/` | Preserved pre-migration generated app/state/build cache |
| `.local/migration-manifest.json` | SHA-256 inventory checked before and after each folder move |

The Desktop contains only `Cornhole Biomechanics Lab.app`, a shortcut to `dist/`.
Double-click it or run `./run_app.sh`. To create/repair the shortcut, run
`./scripts/install_desktop_shortcut.sh`. That command refuses to overwrite a real
Desktop app or regular file.

## Daily changes

1. Open this checkout in GitHub Desktop. Fetch/pull before starting new work.
2. Edit source or use the app to import/analyze throws.
3. Run `./verify.sh` after code changes. Rebuild Swift changes with `./build_app.sh`.
   The app uses Python source from the checkout, so restart an analysis to use edits.
4. Review the changed files, commit with a meaningful message, and Push origin.
5. Before switching branches or pulling, finish running analyses and close the app.
   Never have two apps/branches write to the same athlete library simultaneously.

Generated runtime files and build caches are deliberately not versioned: they are
machine-specific and reproducible from setup/build scripts. Keep separate backups
of local-only files; GitHub protects only data successfully committed and pushed.

## New Mac or collaborator

Install Xcode (Swift 6.2) and Python 3.11/3.12, clone the repository, then run
`./setup.sh`, `./build_app.sh`, and optionally `./scripts/install_desktop_shortcut.sh`.
The app defaults to the main library under `data/libraries`. A local selection is
remembered under `.local/app-support`. Choose another library in the app if needed.
No developer-specific absolute source path is required by the launcher.

## Moving the checkout again

Quit the app, move the complete checkout, recreate the Python environment with
`./setup.sh` (virtual environments are not portable), rebuild the app and reinstall
the Desktop shortcut. If a saved library location still points to the old folder,
use the app's Open Library action to select its new location. Preserve `.local/`
until you have confirmed all libraries and results open correctly.

## Migration verification

The migration used same-volume renames and compared SHA-256 inventories for every
ordinary file, plus symlink targets, before and after each move. Recordings and
analysis files were not edited. The machine-specific library index was remapped
and its old bookmark removed, allowing the app to create a fresh bookmark.
The previously selected two-camera QA library was empty. It and the separate
92-throw main library were both retained; the app now opens the main library. Historical logs may mention old paths; their original contents
remain intact as research provenance.

The existing feature branches remain available. The migration publishes the
current local implementation to main; it does not silently replace it with the
experimental 3D-flight work on `berk/two-camera-takes`.

## Public data and Git LFS

At the project owner's explicit request, the existing videos, analysis libraries,
QA artifacts, project references and model files are included in the public repo.
The MIT license covers this project's original code; third-party references,
recordings and model assets retain their original rights and terms. Publication
here does not grant a new license to third-party materials.

Git LFS stores large binary content separately while Git commits record exact
content hashes. Small per-frame scene masks and reference-book images use ordinary
Git to avoid thousands of individual LFS requests. Clone through GitHub Desktop, or install Git LFS and run
`git lfs install` before cloning, followed by `git lfs pull`. A normal GitHub
source ZIP may contain LFS pointer files rather than the actual dataset. Check
`git lfs status` before pushing; check `git lfs fsck` if media appears incomplete.
GitHub LFS storage/download quotas apply to this shared dataset.

The app does not auto-commit or auto-push. After importing or analyzing data,
review and commit the changes in GitHub Desktop, then Push origin. Historical
outputs are retained unchanged even where they mention pre-migration paths.

`releases/Cornhole-Biomechanics-Lab-macOS.zip` contains the signed app bundle.
After cloning and running setup, unzip it into `dist/`, or build from source.
The bundle uses the checkout's Python runtime and source; it is not a standalone
installer. Regenerate the archive with `./scripts/package_app.sh` after building.
