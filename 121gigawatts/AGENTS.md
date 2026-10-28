# Ghost theme and hosting

- Build and validate theme changes with `pixi run --locked theme-test` from the repository root. Hosting changes use `pixi run --locked hosting-test` and [hosting/AGENTS.md](hosting/AGENTS.md).
- The deployment target is the permanent CX23. DNS cutover and deletion of the old live server need explicit approval; code review is not that approval.
