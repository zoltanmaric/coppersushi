# Hosting review

Before committing or publishing a hosting PR:

- Inspect `git diff --cached --name-only` and the full staged diff. Check new
  files, examples, scripts, documentation, generated artifacts, and PR text.
- Keep real inventories, server/account identifiers, credentials, SSH/TLS private
  keys, Ghost configuration, content exports, SQL dumps, logs, Terraform state,
  saved plans, and private variable files outside the repository. Use placeholders
  in examples. `.gitignore` is only a fallback; never force-add private files.
- Check command construction, logging, and CI for accidental secret exposure.
  Do not print private values to prove that they are absent from the diff.
- Commit dependency lock files: provider/package versions and checksums are
  public reproducibility data. Terraform state and saved plans are not lock files.
- If sensitive data is found, remove it before publishing. If already published,
  tell the user and arrange credential rotation; deleting the latest line does
  not remove it from Git history.
