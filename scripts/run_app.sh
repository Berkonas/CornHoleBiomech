#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
APP_DIR="$PROJECT_DIR/dist/Cornhole Biomechanics Lab.app"
if [[ ! -d "$APP_DIR" ]]; then
  "$PROJECT_DIR/build_app.sh"
fi
open "$APP_DIR"
