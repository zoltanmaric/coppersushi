# Agent guidelines

- This repository is public. Keep credentials, private infrastructure inputs,
  content backups, and personal information outside Git. Follow
  [hosting/AGENTS.md](hosting/AGENTS.md) for deployment changes.
- Keep `AGENTS.md` as the source of agent instructions. Each directory with one
  must have a `CLAUDE.md` containing only `@AGENTS.md`.
- Stage named paths and inspect the staged diff before committing. Do not push
  directly to `master` without approval. Keep changes scoped to the PR's base;
  do not describe uncommitted experiments as prior repository behavior.
- Build and validate theme changes with `yarn test:ci`. Use the checks documented
  in `hosting/README.md` for hosting changes. Never put deployment credentials in CI.
- Production changes, including deployments, DNS changes and server deletion,
  require explicit approval. Code review or merging a PR does not grant it.
