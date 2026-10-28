# Deployment rehearsal

The server setup and Ghost 6 restore were exercised on a fresh CX23 running
Ubuntu 24.04.4. Existing infrastructure was imported into private Terraform
state; creation and Terraform apply were not tested.

- Installation, restore, repeat configuration with zero changes, and reboot passed.
- Restored owner credentials, database records, and content hashes were verified privately.
- The preview returned 16 pages and 122 same-origin assets without failures;
  authenticated Admin API requests returned 200.
- A repeat restore refused the nonempty database before stopping Ghost.
- SMTP TLS/authentication and HTTPS with an explicitly trusted test certificate passed.

The subsequent tooling simplification and MySQL override removal have local/CI
validation only, not another server rehearsal.

Before cutover: reconcile fresh live-site content, verify owner login and external
embeds, install production TLS, and decide on paid backups. The preview still
uses localhost and a short-lived test certificate. DNS has not changed.
Private inputs, backups, state, and logs remain outside this repository.
