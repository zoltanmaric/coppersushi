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

## Restore

Prepare the restore pair from the **same validated Ghost 6 installation**:

- SQL: a full `mysqldump` of the Ghost database, gzip compressed. Use a private
  MySQL option file, not a password in command arguments. Do not import Ghost 4
  SQL directly into Ghost 6. Rehearse supported upgrades/imports first.
- Content: a gzip tar archive of directories *inside* `content/`, including
  uploads, settings, and the active migrated theme. Not the installation root,
  config, or `node_modules`. The restore helper rejects links and escaping paths.
- Verify the snapshot has the real owner's credentials, expected post/draft
  counts, active theme, and uploads. A dummy test owner is not a deployable backup.

On an empty target database only:

```sh
make -C hosting restore CONFIRM="RESTORE blog.example.org"
```

Replace the confirmation domain with `domain` in the private variables. The
restore validates the backups once and checks the database is empty before stopping Ghost.
It then imports SQL, replaces content while retaining the old directory, clears
browser sessions, and starts Ghost. A preflight refusal leaves the service alone;
a failure after import starts leaves Ghost stopped. It never clears a nonempty
database for you.
Back up the target and explicitly prepare an empty database before retrying a
partial import. Keep previous content and SQL backups until validation passes.

## Preview and checks

```sh
ssh -N -L 127.0.0.1:2371:127.0.0.1:2368 root@"$SERVER_IPV4"
# In another terminal:
python3 hosting/verify.py http://localhost:2371
```

Open `http://localhost:2371/` and `/ghost/`. Verify owner login, email delivery,
post/draft counts, theme, navigation, GIFs, Google Slides, and the Copper Sushi
map. The script checks sitemap pages and same-origin HTML assets; browser
review is still needed for external embeds, CSS images, and interactions.
Keep preview analytics injection disabled and save its original values privately.

Check HTTPS without DNS changes using the Cloudflare Origin CA trust bundle
obtained from Cloudflare's official documentation:

```sh
curl --fail --cacert "$DEPLOY_PRIVATE/origin-ca.pem" \
  --resolve "$DOMAIN:443:$SERVER_IPV4" "https://$DOMAIN/"
```

Do not disable certificate verification. While Ghost retains its localhost
preview URL, canonical links and some redirects intentionally use localhost;
check them again after setting the production URL, before the DNS switch.

## Cutover and rollback

1. **Before approval:** finish preview checks, verify SMTP and TLS, record DNS
   values, and take fresh content/database backups. Freeze publishing and other
   writes while taking the final snapshot. Reconcile anything changed on the
   live site since the rehearsal and verify that snapshot again.
2. **After cutover approval:** set Ghost's URL to the production HTTPS origin,
   restore the saved production analytics injection, restart, and verify through
   direct-IP HTTPS. Keep the working SMTP relay. Change only the intended
   Cloudflare origin A record, preserving proxying, TLS mode, and mail records.
   Validate the public site and admin. Keep the old server intact for rollback.
3. **Rollback:** restore the recorded origin DNS value. If the new server has
   received writes, back them up and reconcile them first; a DNS rollback alone
   does not move content or memberships back. Continue the publishing freeze
   until the cutover is accepted.

After the cutover is accepted, retire the old server only with explicit approval.
Keep the CX23 and its Terraform state as the permanent deployment.

The [rehearsal record](rehearsal.md) summarizes deployment checks and remaining cutover work.
