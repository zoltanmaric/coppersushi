#!/bin/bash
# Wait for the running solve; if it failed, wait for Zenodo to answer and resume. Bounded.
set -u
S=/private/tmp/claude-501/-Users-ljube-git-coppersushi/8219e1ac-a793-4c84-b3fb-ba3fccf008a8/scratchpad
PE=/Users/ljube/git/pypsa-eur
WT=/Users/ljube/git/coppersushi/worktrees/solve-2024
export PATH=/opt/homebrew/bin:$PATH

while kill -0 "$(cat $S/logs/solve4.pid)" 2>/dev/null; do sleep 20; done

for attempt in 1 2 3 4 5; do
  if grep -q "^EXIT 0" $S/logs/solve4.log; then echo "SOLVE OK (no resume needed)"; exit 0; fi
  echo "RESUME $attempt: previous run ended without EXIT 0; waiting for zenodo"
  until [ "$(curl -sS -m 25 -o /dev/null -w '%{http_code}' https://zenodo.org/api/records/10820928 2>/dev/null)" = "200" ]; do sleep 60; done
  echo "RESUME $attempt: zenodo up, unlocking and resuming"
  (cd $PE && pixi run snakemake --unlock --configfile $WT/config/coppersushi.yaml >/dev/null 2>&1)
  : > $S/logs/solve4.log
  (cd $WT && /Users/ljube/git/coppersushi/.venv/bin/python -m coppersushi.pypsa_eur solve; echo "EXIT $?") >> $S/logs/solve4.log 2>&1
  if grep -q "^EXIT 0" $S/logs/solve4.log; then echo "SOLVE OK after resume $attempt"; exit 0; fi
done
echo "SOLVE GAVE UP after 5 resumes"
