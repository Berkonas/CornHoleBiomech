# Second-pass audit — 7 September 2026

Baseline: ea7c88d. Native SwiftUI/AVKit application; existing scientific package retained.

## Verified working
- 25 Python tests pass with PYTHONPATH=python; five Swift tests pass.
- Project creation/opening and athlete creation exercised in the release application using an isolated /tmp QA project.
- Canonical pose import produces CSV, JSON, PNG, annotated video and comparison curves on synthetic fixtures.
- Code review verifies non-destructive corrections, event overrides, outcome geometry, reference means, and bootstrap Spearman estimates.

## Partial / missing
- Results primarily presents athlete statistics, not a coherent trial result.
- Sports2D is an optional dependency with no callable analysis adapter; installed 0.8.34 for investigation.
- Quality is a collection of fields without a transparent measurement-quality index; no waveform consistency score.
- No local HTML report, session model, trial-to-trial/own-mean modes, integrated board dispersion, or icon.
- Video and plot cursors are independent. Ghost graphic only shows arm and uses red as athlete color.

## UX / visualization
- Overview is a wall of research prose; normal controls and advanced settings need clearer hierarchy.
- Long athlete names expand the inner sidebar drastically. Inspector controls cannot fit narrow windows.
- Board editor does not preserve regulation 1:2 aspect ratio and symbols differ only in color.
- Results correlation action is enabled with zero analyzed trials.
- Computer-use connection intermittently lost the process while opening Trials; must repeat release QA before calling this a confirmed crash.

## Scientific weaknesses found in source
- Time resampling bridges long missing intervals even though earlier gap handling is conservative.
- Orientation arithmetic crosses the ±180° branch cut; derivatives can spike.
- Repeated-trial analysis can mix camera views, throwing hands, configurations, and spatial endpoint types.
- Quality omits the opposite shoulder needed for the trunk; interpolated manual anchors are not fully counted.
- Imported pose validates fps but not dimensions/frame indexing; events lack range validation.
- Cached comparisons can outlive their source analysis; pose cache key lacks backend version/model settings.
- Automatic release is wrist-velocity proxy, not observed bag separation; this needs stronger UI labeling.

## Documentation / organization
- README is ~26 KB and repeats technical material. No authoritative METRICS.md.
- Research notes inconsistently call included elbow angle flexion and contain stale backend claims.
- Source PDFs/books remain untracked and must remain local. Root scripts and native package can move with compatibility launchers.
- Plain pytest fails to import the source package; configuration should fix this.

## Plan
1. Checkpoint and inventory; organize app/scripts/reference materials without changing source contents.
2. Pin Sports2D public API, preserve raw confidence via a narrowly versioned bridge where upstream lacks export, parse TRC/MOT, record provenance, test real inference and failure behavior.
3. Fix missingness, angle wrapping, compatibility, quality, and stale-result handling.
4. Add trial insights/report, synchronized movement workspace, comparison modes, consistency, board dispersion and session workflow.
5. Integrate editable vector branding and release icon; rewrite documentation.
6. Run Python/Swift/release checks, exercise workflows with visibly labeled synthetic QA data, record limits and actual verification.

Synthetic QA data is software evidence only; real cornhole participant validation remains required.

## Second-pass disposition — 8 September 2026

The baseline gaps above have been addressed by the Sports2D adapter, canonical scientific fixes, native Results/movement workspace, four comparison modes, repeated-throw insights, sessions, board controls, original icon, report export and rewritten documentation. The original code/history and source materials were preserved. Release tests now pass 49 Python and 7 Swift cases. Native correction, cached analysis, comparison, outcome and export workflows were exercised; see ../QA.md for evidence and scope.

Remaining research work: real cornhole participant collection, manual release/outcome review, measurement agreement and repeatability validation. Pilot scores do not establish technique quality or physical measurement accuracy. Broader OS/device and exhaustive UI-state coverage remain beyond the recorded release checks.
