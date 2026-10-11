#!/bin/zsh
# Keep only a launcher on the Desktop; the application stays in this checkout.
set -euo pipefail
PROJECT_DIR="${0:A:h:h}"
APP="$PROJECT_DIR/dist/Cornhole Biomechanics Lab.app"
SHORTCUT="$HOME/Desktop/Cornhole Biomechanics Lab.app"
[[ -d "$APP" ]] || "$PROJECT_DIR/build_app.sh"
if [[ -e "$SHORTCUT" && ! -L "$SHORTCUT" ]]; then
  print -u2 "A regular file or app already occupies $SHORTCUT. Move it before installing the shortcut."
  exit 1
fi
ln -sfn "$APP" "$SHORTCUT"
print "Desktop shortcut now opens: $APP"
