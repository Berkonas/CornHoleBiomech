#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h}"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
SWIFT_PACKAGE="$PROJECT_DIR/app/CornholeBiomechanics"
XCODE_DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
SWIFT_MODULE_CACHE="${TMPDIR:-/tmp}/cornhole-swift-module-cache"
MATPLOTLIB_CACHE="${TMPDIR:-/tmp}/cornhole-matplotlib-cache"

if [[ ! -x "$PYTHON_BIN" ]]; then
  print -u2 "Missing project runtime: run ./setup.sh first."
  exit 2
fi

print "[1/4] Python and scientific tests"
MPLCONFIGDIR="$MATPLOTLIB_CACHE" PYTHONPATH="$PROJECT_DIR/python" "$PYTHON_BIN" -m pytest "$PROJECT_DIR/tests"

print "[2/4] Swift model, persistence, and migration tests"
CLANG_MODULE_CACHE_PATH="$SWIFT_MODULE_CACHE" SWIFTPM_MODULECACHE_OVERRIDE="$SWIFT_MODULE_CACHE" DEVELOPER_DIR="$XCODE_DEVELOPER_DIR" swift test --disable-sandbox --package-path "$SWIFT_PACKAGE"

print "[3/4] Data-schema fixtures"
PYTHONPATH="$PROJECT_DIR/python" "$PYTHON_BIN" "$PROJECT_DIR/scripts/validate_data_schema.py" --root "$PROJECT_DIR"

print "[4/4] Signed release build"
DEVELOPER_DIR="$XCODE_DEVELOPER_DIR" "$PROJECT_DIR/scripts/build_app.sh"

print "Verification complete. See docs/VERIFICATION.md for scope and limitations."
