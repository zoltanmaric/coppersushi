# Continuous integration

[`tests.yml`](tests.yml) runs on non-draft pull requests and manual requests.
A small selection job chooses the check groups; the container check starts independently.

| Group | Responsibility | Reason for the boundary |
|---|---|---|
| Python | Four-worker app tests, then forecast tests | Short forecast checks reuse the app environment. File-level pytest scheduling keeps module fixtures together. |
| Quality | Type checking and frontend contracts, types and tests | These checks share setup without occupying the app's test workers. |
| Ghost theme | Theme installation and validation | Independent of app checks; selected only for relevant changes. |
| Ghost hosting | Ansible setup and Terraform/Ansible checks | Network-dependent setup can overlap the other groups. |
| Container | Runtime activation and native-library smoke test | Checks the serving environment separately from development dependencies. |

Ghost groups are selected when `121gigawatts/`, `pyproject.toml`, `pixi.lock` or
workflow files change. Manual runs select every group. Selection compares the PR
merge with its first parent, so checkout includes two commits. Superseded runs are cancelled.

## Setup choices

Check jobs use native Ubuntu runners and locked Pixi environments. Only the Python
job writes the shared Pixi cache; all groups can restore it without competing to save it.
Short checks share a job because another environment download can cost more than the check.

The container smoke stage inherits the production environment and mounts fixtures
read-only. Running the check inside the build avoids exporting and loading an image
just to test it. It has no remote layer cache: downloading, extracting and publishing
those layers can cost more than rebuilding. Dependency and source layers remain
separate for local build reuse; production bytecode compilation serves Lambda startup.

To run the container check locally:

```sh
docker buildx build --target runtime-check --build-context fixtures=tests/fixtures .
```

The performance target is elapsed workflow time, including runner setup and cache
transfers. More jobs, cache hits or faster individual steps do not necessarily shorten
the longest chain of dependent work. Different runner CPUs also make a single
before/after workflow comparison inconclusive.
