# 1.21 Gigawatts

Custom Ghost theme for [121gigawatts.org](https://121gigawatts.org/), based on
[Casper](https://github.com/TryGhost/Casper). It controls the site’s layouts,
styles, scripts, and theme images. Posts, site settings, and uploaded media live
in Ghost. This repository cannot upgrade Ghost or restore the full site.

## Development

Use the latest Node.js 22.x and Yarn Classic (1.x). Run from the theme directory:

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

## Ghost 6 compatibility

Theme version 3.0.14 targets Ghost 6. It replaces removed theme helpers and keeps
the existing bookmark and gallery styles. The migration was rehearsed locally
through Ghost 4.48.9 and 5.130.6 to 6.72.0; the live Ghost installation has not
been upgraded.

[CI](.github/workflows/test.yml) runs `yarn test:ci` to build the theme and check
Ghost 6 compatibility. The two known, non-blocking warnings concern optional
custom font controls and the page title/feature-image toggle.

## License

Based on Casper. Copyright (c) 2013–2020 Ghost Foundation.
Released under the [MIT license](LICENSE).
