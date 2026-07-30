#!/bin/bash
# Regenerate schedule_VI.json from scratch through a given batch boundary page.
# Usage: run_all_batches.sh <end_page>
set -e
cd "$(dirname "$0")"
rm -f schedule_VI.json
BATCHES=(59:73 74:88 89:103 104:118 119:133 134:148 149:163 164:178 179:193 194:208 209:223 224:238 239:253 254:268 269:283 284:298 299:313 314:320)
END_PAGE=$1
for b in "${BATCHES[@]}"; do
  START=${b%%:*}
  END=${b##*:}
  if [ "$START" -gt "$END_PAGE" ]; then
    break
  fi
  echo "=== batch $START-$END ==="
  python run_VI_batch.py "$START" "$END" 2>&1 | grep -E "Carried forward|Rows added|Total rows|Gaps|needs_review rows"
done
