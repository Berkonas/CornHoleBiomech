#!/bin/zsh
# Runs every queue/*.sh one at a time (output in queue/done/<name>.out), checking every 10 s.
# caffeinate keeps the Mac awake while this window is open. Close the window to stop it.
cd "${0:A:h}/../.."
Q=qa-artifacts/_sync/queue
mkdir -p $Q/done
echo "watcher started $(date)" >> $Q/watcher.log
caffeinate -is -w $$ &
while true; do
  for f in $Q/*.sh(N); do
    name=${f:t:r}
    echo "=== $name started $(date)" >> $Q/watcher.log
    zsh "$f" > "$Q/done/$name.out" 2>&1
    echo "=== exit $? at $(date)" >> "$Q/done/$name.out"
    mv "$f" "$Q/done/$name.sh"
    echo "=== $name finished $(date)" >> $Q/watcher.log
  done
  sleep 10
done
