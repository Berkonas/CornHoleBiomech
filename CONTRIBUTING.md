# Contributing

Thanks for helping with the Cornhole Biomechanics Lab. This guide covers the team workflow.

## Set up

```bash
git clone https://github.com/Berkonas/CornHoleBiomech.git
cd CornHoleBiomech
./setup.sh          # once per Mac: Python runtime and pose models
./build_app.sh      # builds the app directly inside dist/
```

To work on the Python engine without the app, any machine with Python 3.11 or 3.12 works:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
python -m pytest tests
```

## Workflow

1. Branch from `main`: `git switch -c your-name/short-topic`.
2. Keep commits focused. Write the message as what the change does ("Bag tracker: reject fits with upward curvature").
3. Run the checks below, then open a pull request. CI runs the Python tests on 3.11 and 3.12.
4. A teammate reviews it before merge.

## Checks

| Change | Run |
|---|---|
| Python engine, scripts, tests | `python -m pytest tests` |
| Swift app, build scripts | `./verify.sh` (Mac only: Python + Swift tests, schema fixtures, signed build) |
| A method, metric, or threshold | Update the matching doc in `docs/` (usually `METHODS_AND_MATH.md` or `METRICS.md`) |

## Scientific ground rules

- Missing stays missing. Report `unavailable` with a reason; never substitute zero or a guess.
- Every new metric needs a reliability status and, where possible, an uncertainty.
- Thresholds (effect sizes, gates, filter cut-offs) must be justified in the docs with a reference or pilot evidence.
- Associations are not causes. Keep coaching wording consistent with the evidence gate.

## Data and privacy

This public repository includes the owner-approved project dataset and references. Only contribute recordings and materials you have permission to share publicly. Prefer participant codes such as `Player 1` in new examples. Never commit credentials or private account information. Large media is tracked by Git LFS; install LFS before adding files. Review data changes as carefully as source changes.

## Repository location

Keep your checkout in `~/GitHub/CornHoleBiomech` (or another local directory outside Desktop/iCloud). Setup creates `.venv` in that checkout. The app resolves its repository from its bundle location, uses the current Python source, and keeps preferences in `.local/app-support`. See [repository workflow](docs/REPOSITORY_WORKFLOW.md). Rebuild after Swift changes; commit and push changes to synchronize them with GitHub.
