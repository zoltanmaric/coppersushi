# Local Ghost project-page trial

From the monorepo root, after [setup](../../README.md#local-installation), with Docker running:

```sh
pixi run --locked ghost-trial
```

Open <http://localhost:2378/> or <http://localhost:2378/projects/power-flow/>.
`GHOST_TRIAL_PORT` selects another local port. The container name is scoped to the
checkout, so separate worktrees can use separate ports. Stop this checkout's trial:

```sh
pixi run --locked ghost-trial-stop
```

Ghost 6.72 renders the existing theme, navigation, project strip and portfolio.
The power-flow page frames the existing public `/embed/opf-2024` app. The grid
constraints card opens the existing tool in a new tab. The forecast card is marked
in development; it does not pretend the unmerged forecast viewer is available.

The launcher packages the theme, starts Ghost with SQLite, and seeds local sample
content. Repeat it after theme changes. Its database, generated local owner
credentials and copied theme live in ignored `data/ghost-trial/`. It has no live
Ghost credentials and makes no production content, hosting or DNS changes.
Email delivery is disabled by pointing the local container at an unused loopback
SMTP port; email device verification is disabled only in this loopback-only sample
site. Stopping retains the preview database.

## Theme controls

`Show projects` controls the homepage strip; it is off by default and enabled by
the local launcher. The original hero artwork and article-feed templates remain.
`App origin` sets the separately hosted application's origin. The trial's
[routes](routes.yaml) add `/projects/` and `/projects/power-flow/` without changing
article URLs. Navigation entries are ordinary Ghost settings.

For a deployment, merge these two routes into the site's existing routes file
and create pages with slugs `projects` and `power-flow`. Do not replace production
routes or settings with the sample site's configuration. Deployment remains a
separate action under the [hosting runbook](../hosting/README.md).

## Iframe boundaries

The parent page owns navigation and provides an always-visible direct-app link
if the frame fails or a larger viewport is useful. The app owns map interaction
and its internal loading/error display. Cross-origin iframe `load` events do not
prove the app is healthy, so the shell does not claim they do.

The project URL is shareable; selected hour and map camera are not synchronised
into the Ghost URL. Reloading or returning through history may reset that state.
Deep state links would require an explicit, origin-checked parent/app messaging
contract. The trial deliberately measures this boundary before adding one.
