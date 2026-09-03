# Skill Authoring Guidelines

- **vendor-guidelines** — Skills are read by Claude Code and Codex, so follow both vendors' published guidance: Anthropic's [skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) and [Claude Code skills](https://code.claude.com/docs/en/skills), OpenAI's [skills](https://learn.chatgpt.com/docs/build-skills). In particular:
  - **Description triggers, body executes.** Only `name` and `description` are in context by default; the model loads the body when the task matches. Write the description in third person, key use case and trigger words first (hosts truncate long descriptions).
  - **Imperative body.** State what to do, not how or why, and nothing time-sensitive. Once loaded, every line is a recurring token cost. Rationale and evidence go to the wiki (`wiki/rule-provenance.md`), where the `ablation` rule can find them.
  - **Procedures here, facts and "always do X" in `AGENTS.md`.** A rule that must apply at every instant cannot wait for a body to load.

