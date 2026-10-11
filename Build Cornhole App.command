#!/bin/zsh
# Double-click to rebuild the Cornhole Biomechanics Lab app from this folder, then open it.
cd "${0:A:h}"
LOG="qa-artifacts/build.log"
mkdir -p qa-artifacts
{ echo "=== build started $(date) ==="; ./build_app.sh; STATUS=$?; echo "=== build finished with status $STATUS ==="; } 2>&1 | tee "$LOG"
if grep -q "status 0" "$LOG"; then open "dist/Cornhole Biomechanics Lab.app"; fi
