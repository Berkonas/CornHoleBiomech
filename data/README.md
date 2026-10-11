# Shared project data

These recordings, imported libraries and outputs were published at the project owner’s request. Large media files use Git LFS; run `git lfs pull` after cloning.

## Libraries

| Library | Athletes | Throws | Schema |
| --- | ---: | ---: | ---: |
| `Cornhole Biomechanics Lab Data` | 4 | 92 | 4 |
| `Cornhole Pilot Library` | 3 | 36 | 4 |
| `Cornhole Pilot Library backup 2026-09-27` | 3 | 26 | 4 |

The default is `libraries/Cornhole Biomechanics Lab Data`. Open the folder through File → Choose Athlete Library in the app. `project.json` is the library manifest; file references within it are relative to its library folder. Do not move individual files out of a library.

## Other collections

- `videos/`: source footage grouped by participant and reference recordings.
- `bag-validation/`: material for manual bag-tracking validation.
- `spot-check/`: existing visual spot checks.
- `../qa-artifacts/`: historical test libraries, analysis outputs and development archives.
- `../research/`: project references; original third-party rights remain applicable.

Existing outputs are snapshots from different development stages and should not be interpreted as one uniform validation study. Some historic JSON/logs retain old absolute input paths as provenance. Reanalyzing a throw produces current outputs in its managed library folder.

Do not use the same library concurrently from multiple app instances. Commit data changes after analysis finishes; Git does not safely merge independently edited library manifests.
