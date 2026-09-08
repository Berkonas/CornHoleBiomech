#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
SWIFT_PACKAGE="$PROJECT_DIR/app/CornholeBiomechanics"
APP_DIR="$PROJECT_DIR/dist/Cornhole Biomechanics Lab.app"
DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export DEVELOPER_DIR

swift build --package-path "$SWIFT_PACKAGE" -c release
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
cp "$SWIFT_PACKAGE/.build/release/CornholeBiomechanics" "$APP_DIR/Contents/MacOS/CornholeBiomechanics"
cp "$SWIFT_PACKAGE/AppInfo.plist" "$APP_DIR/Contents/Info.plist"
cp "$PROJECT_DIR/resources/branding/AppIcon.icns" "$APP_DIR/Contents/Resources/AppIcon.icns"
mkdir -p "$APP_DIR/Contents/Resources/python/cornhole_biomech"
cp "$PROJECT_DIR/python/cornhole_biomech/"*.py "$APP_DIR/Contents/Resources/python/cornhole_biomech/"
if [[ -f "$PROJECT_DIR/models/pose_landmarker_heavy.task" ]]; then
  mkdir -p "$APP_DIR/Contents/Resources/models"
  cp "$PROJECT_DIR/models/pose_landmarker_heavy.task" "$APP_DIR/Contents/Resources/models/"
fi
codesign --force --deep --sign - "$APP_DIR"

print "Built: $APP_DIR"
print "Launch: open \"$APP_DIR\""
