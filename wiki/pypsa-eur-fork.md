# The PyPSA-Eur fork — layout and hygiene

[zoltanmaric/pypsa-eur](https://github.com/zoltanmaric/pypsa-eur), local checkout `../pypsa-eur`, remotes `origin` (fork) and `upstream` (PyPSA/pypsa-eur). Since the [2026-09-02 pivot](specs/sushi-2.md) it hosts the Sushi 2 pipeline.

## Branches and tags

| Ref | Meaning |
|---|---|
| `master` | Pristine mirror of `upstream/master`. **Never commit here** — that is what keeps every sync a fast-forward. |
| `coppersushi-opf` | The working branch: `master` + the committed config + enhancement rules/scripts. Rebased onto `master` after each sync. |
| `legacy-2022` | The old master (48 commits on PyPSA-Eur 0.5, 2022). Archive; receives nothing. |
| `coppersushi-v1` (tag) | The commit whose `config.yaml` produced v1's bundled network `elec_s_all_ec_lv1.01_2H.nc`. |

## Rules

- **Config under its own name.** Upstream gitignores `config/config.yaml` (a local overlay). Ours is `config/coppersushi.yaml`, committed, passed with `--configfile`, written against `config/schema.default.json` — not copied from `config/examples/config.validation.yaml`, which carries keys today's code ignores.
- **Upstream-shaped changes only.** New behaviour is a rule plus a script under `rules/` and `scripts/`, config keys in the schema, hooks via `solving.options.custom_extra_functionality`; no edits to core scripts. Keeps the [upstream PR](upstream-contributions.md) path open.
- **Sync** = `git fetch upstream && git checkout master && git merge --ff-only upstream/master && git push origin master`, then rebase `coppersushi-opf`.
- **Environment**: pixi (`pixi install`, `pixi shell`), upstream's preferred method; solver HiGHS (`highs-default` profile, raise `threads`).

## Refresh procedure (step 1 of the spec, one-off)

1. `git branch -m master legacy-2022 && git push origin legacy-2022`.
2. `git checkout -b master upstream/master && git push --force origin master` (fork default branch stays `master`).
3. Delete the ~30 remote branches that are stale copies of upstream's own branches; only `master`, `legacy-2022` and the merged `patch-1` are ours.
4. `git checkout -b coppersushi-opf master`; add `config/coppersushi.yaml`.

Why not rebase or merge the 2022 work: 41 of 46 commits conflict on files upstream deleted or restructured; the five that apply are trivia; the code changes are obsolete or already in this repo. Details in [codebase-v1](codebase-v1.md) lineage and the `coppersushi-v1` tag.
