# Ghost hosting

[Repository overview and theme workflow](../README.md)

This configuration runs Ghost on a permanent Hetzner CX23: Ubuntu 24.04,
Node 22, MySQL 8, Ghost 6.72.0, Nginx, UFW, and 2 GiB swap. Ghost runs as an
unprivileged account on loopback. Installation paths are fixed for this site.

Terraform owns the server and primary IPs, with deletion guards. It reuses an
existing SSH public key. Paid daily backups are controlled by `backups`;
preserve the observed setting when adopting a server. Cloudflare DNS and origin
certificate issuance/renewal remain manual. Git pushes and CI never deploy.

## Quick start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), Terraform
1.5+, and Make. From the repository root:

```sh
make -C hosting setup
make -C hosting test
```

`setup` installs the locked Python/Ansible environment and pinned Ansible
collections. `test` validates configuration without connecting to a server.
The Makefile contains direct tool commands, which you can also run individually.
Commit `uv.lock` and `.terraform.lock.hcl`; these contain public dependency
versions and checksums, not deployment state.

## Private inputs

Choose an absolute directory **outside Git**, with mode `0700` and private files
mode `0600`. Copy the three examples there once and fill them in:

```sh
export DEPLOY_PRIVATE=/absolute/private/ghost
umask 077
mkdir -p "$DEPLOY_PRIVATE"
cp hosting/terraform/site.tfvars.example "$DEPLOY_PRIVATE/site.tfvars"
cp hosting/ansible/inventory.example.yml "$DEPLOY_PRIVATE/inventory.yml"
cp hosting/ansible/site.example.yml "$DEPLOY_PRIVATE/site.yml"
```

Do not overwrite existing inputs when returning to this workflow. Keep real
inventories, credentials, private keys, backups, state, saved plans, and logs
outside the repository. See [hosting review guidelines](AGENTS.md).

Supply a project-scoped `HCLOUD_TOKEN` through the environment. Verify the SSH
host fingerprint before recording it in `known_hosts`. Supply a separate private
Ghost `config.production.json` with MySQL database `ghost_prod`, user `ghostapp`,
and a strong password. Keep that password stable between runs; rotation is
separate. Ghost binds `127.0.0.1:2368`, MySQL uses `127.0.0.1`, and content lives
at `/var/www/121gigawatts/content`. Set the same URL in Ghost config and `site.yml`.
Use `http://localhost:2371` for preview and working SMTP for login emails.

Supply `origin_certificate_file` and `origin_key_file`, or install both directly
under `/etc/ssl/121gigawatts` and omit those inputs. Cloudflare Origin CA requires
proxied traffic with Full (strict) TLS. Browsers do not trust it directly.
Renew certificates before expiry.

## Infrastructure

Initialize Terraform, keeping its working data outside Git:

```sh
export TF_DATA_DIR="$DEPLOY_PRIVATE/terraform-data"
terraform -chdir=hosting/terraform init -lockfile=readonly
```

For an existing server, import its three resources once. Obtain their IDs from
Hetzner; verify they belong to the intended CX23. Skip these commands only when
intentionally creating a new paid server.

```sh
terraform -chdir=hosting/terraform import -state="$DEPLOY_PRIVATE/terraform.tfstate" -var-file="$DEPLOY_PRIVATE/site.tfvars" 'hcloud_primary_ip.site["ipv4"]' "$IPV4_ID"
terraform -chdir=hosting/terraform import -state="$DEPLOY_PRIVATE/terraform.tfstate" -var-file="$DEPLOY_PRIVATE/site.tfvars" 'hcloud_primary_ip.site["ipv6"]' "$IPV6_ID"
terraform -chdir=hosting/terraform import -state="$DEPLOY_PRIVATE/terraform.tfstate" -var-file="$DEPLOY_PRIVATE/site.tfvars" hcloud_server.site "$SERVER_ID"
```

Plan, inspect the proposed changes, then explicitly apply the saved plan:

```sh
terraform -chdir=hosting/terraform plan -state="$DEPLOY_PRIVATE/terraform.tfstate" -var-file="$DEPLOY_PRIVATE/site.tfvars" -out="$DEPLOY_PRIVATE/review.tfplan"
terraform -chdir=hosting/terraform apply -state="$DEPLOY_PRIVATE/terraform.tfstate" "$DEPLOY_PRIVATE/review.tfplan"
```

Review creation, resize, backup charges, and deletion proposals. Adoption can
record provider defaults and public-network IDs as an in-place change; verify
them against Hetzner. Creation-time SSH keys cannot be reconciled after import;
manage subsequent key changes on the server. Back up the private state.

## Configure

For a fresh restore target, install with Ghost held stopped so its database stays
empty:

```sh
make -C hosting configure HOLD=1
```

Omit `HOLD=1` only to start a new empty site. On an already configured server,
predict changes before applying them:

```sh
make -C hosting check
make -C hosting configure
```

`configure` can restart services. Ansible check mode needs existing packages and
files; it is not a first-installation test.

The playbook installs or reconciles the pinned Ghost version; it refuses an
implicit version upgrade. Node 22 patch updates follow the package repository.
OS upgrades and Ghost upgrades are separate maintenance operations. MySQL uses
Ubuntu defaults. Removing an existing `99-ghost-small.cnf` override restarts
MySQL; inspect that change before applying to a running site.

## Preview

```sh
ssh -N -L 127.0.0.1:2371:127.0.0.1:2368 root@"$SERVER_IPV4"
```

Open `http://localhost:2371/` and `/ghost/`. Validate content, owner access, SMTP,
and production TLS before a separately approved DNS cutover. The CX23 is the
permanent target; the old server is retained only for rollback until approved
retirement. Syntax checks do not replace a fresh-server rehearsal.
