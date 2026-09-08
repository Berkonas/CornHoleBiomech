#!/bin/zsh
set -euo pipefail
exec "${0:A:h}/scripts/build_app.sh" "$@"
