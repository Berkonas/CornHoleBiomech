#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
SWIFT_PACKAGE="$PROJECT_DIR/app/CornholeBiomechanics"
DESTINATION="$PROJECT_DIR/dist/Cornhole Biomechanics Lab.app"
INSTALL_ROOT="$HOME/Library/Application Support/Cornhole Biomechanics Lab/Builds"
INSTALLED_APP="$INSTALL_ROOT/Cornhole Biomechanics Lab.app"
DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export DEVELOPER_DIR
export CLANG_MODULE_CACHE_PATH="${CLANG_MODULE_CACHE_PATH:-${TMPDIR:-/tmp}/cornhole-swift-module-cache}"
export SWIFTPM_MODULECACHE_OVERRIDE="${SWIFTPM_MODULECACHE_OVERRIDE:-$CLANG_MODULE_CACHE_PATH}"

swift build --disable-sandbox --package-path "$SWIFT_PACKAGE" -c release
STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cornhole-app-build.XXXXXX")"
trap 'rm -rf "$STAGING_DIR"' EXIT
APP_DIR="$STAGING_DIR/Cornhole Biomechanics Lab.app"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
cp "$SWIFT_PACKAGE/.build/release/CornholeBiomechanics" "$APP_DIR/Contents/MacOS/CornholeBiomechanics"
cp "$SWIFT_PACKAGE/.build/release/SceneVision" "$APP_DIR/Contents/MacOS/scene-vision"
cp "$SWIFT_PACKAGE/AppInfo.plist" "$APP_DIR/Contents/Info.plist"
cp "$PROJECT_DIR/app/Resources/branding/AppIcon.icns" "$APP_DIR/Contents/Resources/AppIcon.icns"
mkdir -p "$APP_DIR/Contents/Resources/python/cornhole_biomech"
cp "$PROJECT_DIR/python/cornhole_biomech/"*.py "$APP_DIR/Contents/Resources/python/cornhole_biomech/"
if [[ -f "$PROJECT_DIR/app/Resources/models/pose_landmarker_heavy.task" ]]; then
  mkdir -p "$APP_DIR/Contents/Resources/models"
  cp "$PROJECT_DIR/app/Resources/models/pose_landmarker_heavy.task" "$APP_DIR/Contents/Resources/models/"
fi
# Finder/iCloud can attach layout metadata while a Desktop bundle is rebuilt.
# Clear only signing-incompatible metadata from this generated bundle, never
# quarantine/security attributes or any original source/participant files.
xattr -dr com.apple.FinderInfo "$APP_DIR" 2>/dev/null || true
xattr -dr com.apple.ResourceFork "$APP_DIR" 2>/dev/null || true
codesign --force --deep --sign - "$APP_DIR"
codesign --verify --deep --strict "$APP_DIR"
mkdir -p "$PROJECT_DIR/dist"
mkdir -p "$INSTALL_ROOT"
# Install only this generated application; Runtime and athlete data are separate.
rm -rf "$INSTALLED_APP"
mv "$APP_DIR" "$INSTALLED_APP"
codesign --verify --deep --strict "$INSTALLED_APP"
rm -rf "$DESTINATION"
ln -s "$INSTALLED_APP" "$DESTINATION"

print "Built and signature-verified: $DESTINATION"
print "Local executable: $INSTALLED_APP"
print "Launch: open \"$DESTINATION\""
