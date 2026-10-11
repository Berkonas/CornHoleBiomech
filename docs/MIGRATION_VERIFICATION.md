# GitHub workspace migration verification

Verified on 10 October 2026 (America/Chicago):

- All five moved folder trees matched their pre-move SHA-256/symlink inventories.
- All 32,426 original dataset files match their committed Git/LFS content byte-for-byte.
  Only five macOS metadata/Python cache files were excluded from version control.
- 562 Python tests passed before and after relocation.
- 86 Swift tests ran: 83 passed, 3 opt-in visual/real-video tests skipped.
- The new repository-resolution test chooses the moved bundle ahead of an old source path.
- A native worker probe successfully used the relocated Python environment.
- Six library manifests validated with zero missing-file warnings.
- SceneVision and the release application built successfully; the bundle signature verified.
- Opening the Desktop shortcut launched the app from `~/GitHub/CornHoleBiomech/dist`.
- The main library loaded all four athletes and 92 throws; existing summary results displayed.
- A two-camera throw report opened and replay advanced through its video frames.

The original two-camera QA selection was empty and was preserved. The main library
is now selected for normal use. No recordings or analysis results were regenerated
as part of this move. This verifies relocation and app operation; it does not
establish new scientific accuracy or validate every existing measurement.

Machine-local details and the full verification log are retained in `.local/`.
