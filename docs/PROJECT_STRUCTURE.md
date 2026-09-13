# Finding your way around

Start with the README in the main folder. Open the app from `dist`. Everything else is grouped by purpose, not by an old project session.

The `dist` app is a link to the generated runnable build in `~/Library/Application Support/Cornhole Biomechanics Lab/Builds`. The Python runtime is a separate sibling folder there. This avoids iCloud Desktop adding metadata that invalidates app signing. Athlete data remains separate in Documents or the library location you select.

```
Project 1 - Cornhole/
  README.md
  setup.sh, build_app.sh, run_app.sh, verify.sh
  app/
    CornholeBiomechanics/       Swift app and native tests
    Resources/
      branding/                App icon source and compiled icon
      models/                  Local model weights; ignored by Git
  python/cornhole_biomech/      Scientific engine
  tests/                       Python tests
  scripts/                     Implementation of setup/build and QA tools
  docs/                        Current methods, guides, and verification
    archive/                   Previous README, research notes, and audits
  research/                    Local user material; ignored by Git
    course/                    Course PDFs
    books/                     User-owned material, untouched
    design/                    Earlier design material, not scientific evidence
  dist/                        Link to the locally installed app; ignored by Git
```

The app’s athlete library is separate, normally in `~/Documents/Cornhole Biomechanics Lab Data`. Each athlete has a readable folder name with a stable identifier, a profile, throws, and analyses. The library index is `project.json`; “project” here is an internal compatibility name, not a setup task you must repeat.

Prepared video copies are stored in a throw-specific `…-video-revisions` folder alongside its managed original. Each revision contains `prepared.mp4` and a `.preparation.json` sidecar with the original hash, dimensions, source-frame mapping, crop, rotation, and output hash. If an analysis existed when the clip changed, it is moved into that revision’s `previous-analysis` folder. Returning to the original also invalidates analysis. Revisions are retained until you delete the throw or athlete.

## Cleanup performed in version 0.4

Moved the former root `models` and `resources/branding` into `app/Resources`; updated setup, build, and model lookup paths. Removed the now-empty `resources` directory. Renamed `reference_materials` to `research` without opening or changing books. Moved duplicate root research/reference notes and previous long-form documentation into `docs/archive`. No participant recording was deleted. The earlier `Participant` and `Cornhole Study.cornholeproject` folders were absent at the start of this pass; their relocation was not performed by this pass.

Build output and caches are generated and Git-ignored. They remain available for quick rebuilds. Avoid manually deleting anything inside an athlete library unless you have a backup; use the app’s confirmed management actions instead.
