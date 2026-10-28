# 1.21 Gigawatts

The custom Ghost theme and hosting code for [121gigawatts.org](https://121gigawatts.org/).
The theme is based on [Casper](https://github.com/TryGhost/Casper) and targets
Ghost 6, preserving the site's existing appearance.

## Repository guide

| Part | Responsibility |
| --- | --- |
| Root `.hbs` files and `partials/` | Page layouts and shared Handlebars templates |
| `assets/css/` and `assets/js/` | Theme styles and scripts; compiled output is in `assets/built/` |
| [hosting/](hosting/README.md) | Terraform infrastructure, Ansible setup and restore, and the deployment runbook |
| [.github/workflows/](.github/workflows/) | Theme and hosting configuration checks; no automatic deployment |

Posts, drafts, site settings, and uploaded media live in Ghost, not in this
repository. Restoring a site requires separate database and content backups.
Credentials, private keys, real inventories, backups, and Terraform state stay
outside this public repository.

## Work on the theme

Use Node.js 22.x and Yarn Classic (1.x). Run from the repository root:

```sh
yarn install --frozen-lockfile
yarn dev
```

`yarn dev` builds assets and watches for changes; it does not run Ghost. Preview
changes in a separate Ghost 6 installation with this theme active.

To build, validate, and package the theme:

```sh
yarn test
yarn zip
```

Upload `dist/121gigawatts.zip` through Ghost Admin's theme settings. Download the
active theme as a backup first. Uploading a theme changes its presentation;
it does not upgrade Ghost or restore content.

[Theme CI](.github/workflows/test.yml) runs `yarn test:ci`, which builds assets
and checks Ghost 6 compatibility. The two known, non-blocking warnings concern
optional custom fonts and the page title/feature-image toggle.

## Animated images

Precompress animations before uploading. Ghost can recompress uploads; verify
its saved original before using that URL to preserve the chosen quality.
Our [image-quality discussion](https://forum.ghost.org/t/image-compression-configuration/13545)
explains why controlling compression matters.

Warm the responsive image URLs rendered by the theme one at a time. Successful
resizes are saved and reused. Ghost 6.72 limits each resize operation to ten
seconds; a timeout redirects to the original and later requests retry the work.
For sizes that time out, generate animated variants offline and install them at
`content/images/size/w<width>/<year>/<month>/<filename>`, matching existing cache
ownership and permissions. Keep originals, avoid enlargement, and verify animation
timing. Check that the rendered URLs return WebP directly without a slow redirect.

## Run or migrate Ghost

Follow the [hosting runbook](hosting/README.md) for private inputs, server setup,
restoration, preview checks, cutover, and rollback. Deployment is manual and
separate from theme development. See the [rehearsal results](hosting/rehearsal.md)
for what has been tested and what remains before production cutover.

[Hosting CI](.github/workflows/hosting.yml) validates Terraform, Ansible, and
restore safeguards. It has no deployment credentials and does not change servers.

## License

Based on Casper. Copyright (c) 2013–2020 Ghost Foundation.
Released under the [MIT license](LICENSE).
