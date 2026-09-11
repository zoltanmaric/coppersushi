#!/bin/bash
set -u
D=/private/tmp/claude-501/-Users-ljube-git-coppersushi/8219e1ac-a793-4c84-b3fb-ba3fccf008a8/scratchpad/gen
for c in RO SI HR HU SK DE FR; do
  for try in 1 2 3; do
    code=$(curl -sS -m 40 -o "$D/$c.json" -w "%{http_code}" "https://api.energy-charts.info/public_power?country=$(echo $c | tr A-Z a-z)&start=2024-08-29&end=2024-08-30")
    echo "$c try$try HTTP:$code"
    [ "$code" = "200" ] && break
    sleep 20
  done
  sleep 8
done
echo GEN_DONE
