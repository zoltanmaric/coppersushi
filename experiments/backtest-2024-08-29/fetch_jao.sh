#!/bin/bash
set -u
OUT=/private/tmp/claude-501/-Users-ljube-git-coppersushi/8219e1ac-a793-4c84-b3fb-ba3fccf008a8/scratchpad/jao
for ep in shadowPrices maxNetPos netPosition; do
  curl -sS -m 300 -o "$OUT/$ep.json" -w "$ep HTTP:%{http_code} bytes:%{size_download}\n" \
    "https://publicationtool.jao.eu/core/api/data/$ep?FromUtc=2024-08-28T22:00:00Z&ToUtc=2024-08-29T22:00:00Z"
done
for h in $(seq 0 23); do
  F=$(printf "2024-08-%02dT%02d:00:00Z" $((28 + (22+h)/24)) $(( (22+h)%24 )) )
  T=$(printf "2024-08-%02dT%02d:00:00Z" $((28 + (23+h)/24)) $(( (23+h)%24 )) )
  curl -sS -m 600 -o "$OUT/fc_$h.json" -w "fc_$h $F HTTP:%{http_code} bytes:%{size_download}\n" \
    "https://publicationtool.jao.eu/core/api/data/finalComputation?FromUtc=$F&ToUtc=$T"
done
echo "JAO_FETCH_DONE"
