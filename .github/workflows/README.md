# Continuous integration

[`tests.yml`](tests.yml) runs on non-draft pull requests and manual requests.
A small selection job chooses the check groups; the container check starts independently.

| Group | Responsibility | Reason for the boundary |
|---|---|---|
| Python | Four-worker app tests, then forecast tests | Short forecast checks reuse the app environment. File-level pytest scheduling keeps module fixtures together. |
| Quality | Type checking and frontend contracts, types and tests | These checks share setup without occupying the app's test workers. |
| Ghost theme | Theme installation and validation | Independent of app checks; selected only for relevant changes. |
| Ghost hosting | Ansible setup and Terraform/Ansible checks | Network-dependent setup can overlap the other groups. |
| Container | Native publisher dependency and import check | Checks the publisher environment separately from development dependencies. |

Ghost groups are selected when `121gigawatts/`, `pyproject.toml`, `pixi.lock` or
workflow files change. Manual runs select every group. Selection compares the PR
merge with its first parent, so checkout includes two commits. Superseded runs are cancelled.

## Setup choices

Check jobs use native Ubuntu runners and locked Pixi environments. Only the Python
job writes the shared Pixi cache; all groups can restore it without competing to save it.
Short checks share a job because another environment download can cost more than the check.

The native publisher smoke stage verifies the deployed handler imports without web frameworks.
It has no remote layer cache: downloading and publishing layers can cost more than rebuilding.
Run it locally with `docker buildx build --target publisher-check .`.

The performance target is elapsed workflow time, including runner setup and cache
transfers. More jobs, cache hits or faster individual steps do not necessarily shorten
the longest chain of dependent work. Different runner CPUs also make a single
before/after workflow comparison inconclusive.
