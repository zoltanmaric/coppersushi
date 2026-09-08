---
name: job-supervision
description: Launches and supervises long-running commands — solves, workflows, downloads, builds — detached with a log, PID and exit sentinel, then tells stuck from slow and kills verifiably. Use before running anything that may exceed a minute, for nohup or background launches, and when a run hangs, shows no output, or timed out.
---

# Job supervision

## The gate — answer before launching

1. **Success artifact**: which file or remote state proves success? Poll that, not the client process.
2. **Birth signal**: what shows the run alive by ~30 s — CPU accruing, a log or lock file created, a socket open? Not stdout: healthy jobs are often pipe-buffered silent.
3. **Progress**: what emits progress, at what cadence, against known phase durations? If unknown, measuring them is this run's job.
4. **Silence budget**: after how long without progress is it failed? An armed timer, not a vibe. On any exit, verify the artifact — silence is not success.

**Preflight** every fallible precondition before the expensive phase: credentials that expire, connectivity, config validation (`snakemake -n`), disk space.

## Launch recipe

- **Detach from the tool's timeout in its own process group, keep the PID and the exit status**: a background tool call is capped, and a plain `nohup … &` shares the tool shell's group. Launch as `nohup perl -MPOSIX -e 'POSIX::setsid(); exec @ARGV' bash -c '<cmd>; echo "EXIT $?"' </dev/null >> <logdir>/<name>.log 2>&1 & echo $! > <logdir>/<name>.pid`, then, after a second, confirm `ps -o pgid= -p $(cat <name>.pid)` prints the PID.
- **Never pipe a long-runner through `tail`/`head`**. Log to a file, read the tail on demand.
- **Arm the watcher at once** on the log, filtering for progress **and every terminal state**: `Traceback|Error|Exiting|EXIT|Killed`.
- **Verify downloads by size or checksum** before relying on them.

## Stuck vs. slow

Check: process alive (`pgrep -f`); CPU *time* accruing (`ps -o time -p <pid>`, two samples 20 s apart — not %CPU); the tool's own artifacts growing (fresh mtimes); `lsof -p <pid>` — a lone TCP connection in `CLOSE_WAIT` with flat CPU is a dead client. Flat on all → stuck. Then kill.

## Verified kill

Kill the launched process *group*, not a command-line pattern: `kill -- -$(cat <name>.pid)`, wait, `pgrep -g $(cat <name>.pid)` shows nothing; then remove stale locks (Snakemake: `.snakemake/locks/`) and relaunch. A kill is done when the process tree is confirmed gone.
