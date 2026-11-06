#!/bin/bash
set -u
D=/private/tmp/claude-501/-Users-ljube-git-coppersushi/8219e1ac-a793-4c84-b3fb-ba3fccf008a8/scratchpad/prices
for bzn in AT BE CZ DE-LU FR HR HU NL PL RO SI SK; do
  for try in 1 2 3 4; do
    code=$(curl -sS -m 40 -o "$D/$bzn.json" -w "%{http_code}" "https://api.energy-charts.info/price?bzn=$bzn&start=2024-08-29&end=2024-08-30")
    echo "$bzn try$try HTTP:$code"
    [ "$code" = "200" ] && break
    sleep 20
  done
  sleep 8
done
echo "PRICES_DONE"
