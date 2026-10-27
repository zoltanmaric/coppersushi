# 1.21 Gigawatts

Custom Ghost theme for [121gigawatts.org](https://121gigawatts.org/), based on
[Casper](https://github.com/TryGhost/Casper). It controls the site’s layouts,
styles, scripts, and theme images. Posts, site settings, and uploaded media live
in Ghost. This repository cannot upgrade Ghost or restore the full site.

## Development

With Node.js and Yarn installed, run from the theme directory:

```sh
yarn install
yarn dev
```

`yarn dev` builds assets and watches CSS and template changes; it does not run
Ghost. Preview the theme in a separate Ghost installation. CSS sources are in
`assets/css/`, scripts in `assets/js/`, and compiled assets in `assets/built/`.

Templates use Handlebars: `default.hbs` is the shared shell; `index.hbs`,
`post.hbs`, and `page.hbs` render the home page, posts, and pages. Shared pieces
live in `partials/`.

## Build and upload

```sh
yarn test
yarn zip
```

These commands build and validate the theme, then create
`dist/121gigawatts.zip`. Upload the ZIP through Ghost Admin’s theme settings.
Download the active theme as a backup before replacing it. See
[Ghost’s theme installation guide](https://ghost.org/help/installing-a-theme/).

## Automatic deployment

[The deployment workflow](.github/workflows/deploy-theme.yml) is configured to
upload the theme as `121gigawatts-master` on pushes to `master`. It requires the
GitHub Actions secrets `GHOST_ADMIN_API_URL` and `GHOST_ADMIN_API_KEY`.

**The workflow needs repair before use:** it targets the retired
`ubuntu-18.04` runner. Credential validity has not been verified. The deployment
job also has no build step, so compiled assets must be updated before upload.

## License

Based on Casper. Copyright (c) 2013–2020 Ghost Foundation.
Released under the [MIT license](LICENSE).
