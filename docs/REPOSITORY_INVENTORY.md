# Repository migration inventory

| Existing item | Purpose | Action / destination |
|---|---|---|
| CornholeBiomechanics/ | Swift package, app metadata, tests | git mv to app/CornholeBiomechanics/ |
| python/, tests/, pyproject.toml | Scientific engine and tests | Keep |
| build_app.sh, run_app.sh, setup.sh | Developer entry points | Move implementations to scripts/; retain thin compatibility launchers |
| README.md, RESEARCH_NOTES.md, REFERENCES.md | Public project explanation | Keep and revise |
| IMPLEMENTATION_PLAN.md | Initial historical plan | Archive under docs/archive/ |
| CURRENT_APP_AUDIT.md | Second-pass audit | Archive after verification |
| Course PDFs | Original course sources | Move unchanged to reference_materials/course/; ignore |
| Biomechanics of Movement.epub/ | Copyrighted local book | Move unchanged to reference_materials/books/; ignore |
| Design Books/ | Local design sources | Move unchanged to reference_materials/design/; ignore |
| .venv/, models/, dist/, .pytest_cache/, .build/ | Local runtime/generated content | Keep ignored; no model/participant data commits |
| .git/ | History | Preserve |

Original materials are moved locally, never added to Git. Content hashes are verified by the migration script. No nested external Git checkout is needed: official source inspection is temporary and runtime uses a pinned PyPI release.
