#!/bin/bash
# Smoke test a coppersushi checkout: unit tests, then render every real network through the app.
set -u
WT="${1:?usage: smoke.sh <worktree path>}"
PY=/Users/ljube/git/coppersushi/.venv/bin/python
export MAPBOX_TOKEN="$(cat /Users/ljube/git/coppersushi/.secrets/.mapbox_token 2>/dev/null | tr -d '\n')"
cd "$WT" || exit 1
echo "### smoke: $WT ($(git rev-parse --abbrev-ref HEAD))"
$PY -m pytest tests/ -q 2>&1 | tail -3
$PY - <<'PY'
import sys, warnings
warnings.filterwarnings("ignore")
import app
ok = True
for key in list(app.NETWORK_LOADERS):
    try:
        fig, *_rest = app.render(f"/{key}", 0, slider_moved=False)
        n_traces = len(getattr(fig, "data", []) or [])
        status = "ok" if n_traces else "NO TRACES"
        ok &= bool(n_traces)
        print(f"  render /{key:24s} {status} ({n_traces} traces)")
    except Exception as e:
        ok = False
        print(f"  render /{key:24s} FAILED {type(e).__name__}: {str(e)[:90]}")
print("SMOKE OK" if ok else "SMOKE FAILED")
sys.exit(0 if ok else 1)
PY
