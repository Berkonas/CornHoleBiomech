#!/bin/zsh
# Runs qa-artifacts/_sync/job.sh with the project runtime; output goes to qa-artifacts/_sync/job.log.
# caffeinate keeps the Mac from idle/system sleep while the job runs (a sleeping Mac pauses the analysis).
cd "${0:A:h}/../.."
LOG="qa-artifacts/_sync/job.log"
{ echo "=== job started $(date)"; caffeinate -is zsh qa-artifacts/_sync/job.sh; echo "=== job finished with status $? at $(date)"; } > "$LOG" 2>&1
echo "Done. You can close this window."
