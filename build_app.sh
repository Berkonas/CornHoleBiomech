#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h}"
SWIFT_PACKAGE="$PROJECT_DIR/CornholeBiomechanics"
APP_DIR="$PROJECT_DIR/dist/Cornhole Biomechanics Lab.app"
DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export DEVELOPER_DIR

swift build --package-path "$SWIFT_PACKAGE" -c release
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
cp "$SWIFT_PACKAGE/.build/release/CornholeBiomechanics" "$APP_DIR/Contents/MacOS/CornholeBiomechanics"
cp "$SWIFT_PACKAGE/AppInfo.plist" "$APP_DIR/Contents/Info.plist"
codesign --force --deep --sign - "$APP_DIR"

print "Built: $APP_DIR"
print "Launch: open \"$APP_DIR\""
