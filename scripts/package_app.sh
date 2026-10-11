#!/bin/zsh
# Archive the built bundle for collaborators; the Python environment is recreated.
set -euo pipefail
PROJECT_DIR="${0:A:h:h}"
APP="$PROJECT_DIR/dist/Cornhole Biomechanics Lab.app"
[[ -d "$APP" ]] || "$PROJECT_DIR/build_app.sh"
codesign --verify --deep --strict "$APP"
mkdir -p "$PROJECT_DIR/releases"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$PROJECT_DIR/releases/Cornhole-Biomechanics-Lab-macOS.zip"
print "Packaged app; review and commit the archive with Git LFS."
