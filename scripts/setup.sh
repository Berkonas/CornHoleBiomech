#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
PYTHON_CANDIDATES=(
  "${CORNHOLE_PYTHON:-}"
  "/opt/homebrew/bin/python3.12"
  "/usr/local/bin/python3.12"
  "/Users/${USER}/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
  "python3.12"
  "python3.11"
  "python3"
)

PYTHON_BIN=""
for candidate in "${PYTHON_CANDIDATES[@]}"; do
  [[ -z "$candidate" ]] && continue
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(not ((3,11) <= sys.version_info[:2] < (3,13)))'; then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  print -u2 "Python 3.11 or 3.12 is required. Install Python 3.12 or run CORNHOLE_PYTHON=/path/to/python3.12 ./setup.sh"
  exit 2
fi

RUNTIME_DIR="$PROJECT_DIR/.venv"
# Older releases linked to Application Support. Unlink only the pointer; never
# remove the old environment or silently install into another checkout's runtime.
if [[ -L "$RUNTIME_DIR" ]]; then
  rm "$RUNTIME_DIR"
fi
"$PYTHON_BIN" -m venv "$RUNTIME_DIR"
"$RUNTIME_DIR/bin/python" -m pip install --upgrade pip
"$RUNTIME_DIR/bin/python" -m pip install -e "${PROJECT_DIR}[test,pose,sports2d]"

MODEL_DIR="$PROJECT_DIR/app/Resources/models"
MEDIAPIPE_MODEL="$MODEL_DIR/pose_landmarker_heavy.task"
if [[ ! -f "$MEDIAPIPE_MODEL" ]]; then
  mkdir -p "$MODEL_DIR"
  print "Downloading the official MediaPipe pose model for optional offline fallback..."
  curl --fail --location --output "$MEDIAPIPE_MODEL" \
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task"
  (cd "$MODEL_DIR" && shasum -a 256 "${MEDIAPIPE_MODEL:t}" > "${MEDIAPIPE_MODEL:t}.sha256")
fi
print "Installed Cornhole Biomechanics Lab scientific engine."
print "Verify: PYTHONPATH=\"$PROJECT_DIR/python\" \"$PROJECT_DIR/.venv/bin/python\" -m cornhole_biomech probe"
