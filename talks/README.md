# Conference talks

## How GitHub Helps Us Reach 6,000 Learners

The presentation is published alongside the existing documentation at
[`talks/building-a-ladder/`](https://learntocloud.github.io/learn-to-cloud-app/talks/building-a-ladder/).
Its editable source is in `building-a-ladder/`.
The original URL is retained so existing links keep working.

The deck has 20 minimal, blue-accented slides. Each slide carries one main idea;
the full script and technical context live in speaker notes. The original
6,000-learner talk title is retained, with the current 9,000+ figure on the
Learn to Cloud slide.

Use Node.js 24 LTS:

```sh
cd talks
npm ci
npm run build
npm run serve
```

Open <http://localhost:4173/building-a-ladder/>. Use the arrow keys or on-screen
controls to navigate, `F` for fullscreen, `Esc` for an overview, and `S` for the
speaker view with notes and a timer. Allow the speaker popup when prompted.
Slide hashes can be bookmarked. Serve the files over HTTP rather than opening
`index.html` directly so the notes window can connect.

To reproduce the GitHub Pages project path or choose another port:

```sh
BASE_PATH=/learn-to-cloud-app/talks/ PORT=4174 npm run serve
```

Then open <http://localhost:4174/learn-to-cloud-app/talks/building-a-ladder/>.
The server listens only on the local machine and serves an in-memory snapshot of
`dist/`. It rejects symlink assets at startup and never reads filesystem paths
from requests. Rebuild and restart the server to preview edits.

## Browser checks

```sh
npx playwright install chromium
npm test
```

Linux CI uses `npx playwright install --with-deps chromium` to install the required
system libraries as well. Tests build the deck and start their own local server
on an available port, so they do not conflict with the preview server. They
check initialization, local asset loading, speaker notes, image loading, keyboard
and hash navigation, notes-window synchronization, the dark viewport background,
slide bounds and content clearance above footers, a narrow viewport, PDF output,
and the server's error handling. They also enforce the 20-slide structure,
original title, blue accent, and a 40-word on-slide text budget (excluding notes
and footers). The
browser checks use the full `/learn-to-cloud-app/talks/` project prefix.
Browser scratch files stay in the ignored `.browser-tmp/` directory.

For PDF export, open the presentation with `?print-pdf`, then print in Chromium
with background graphics enabled and margins disabled.

## Build and publication

Reveal.js and Playwright are pinned to exact versions in `package.json` and
`package-lock.json`. No CDN or application backend is needed. The build copies
only `index.html`, `styles.css`, `deck.js`, and `assets/` from the presentation,
plus Reveal's reset stylesheet, presentation stylesheet, JavaScript runtime,
notes plugin, and license, into `dist/building-a-ladder/`. Generated files and
`node_modules/` are not committed. Images should be local to `assets/`.

The Pages workflow installs dependencies, builds and tests the talk, and assembles
the documentation and `dist/` in `_site-source/` before running Jekyll. Jekyll
produces the complete `_site/`, including `talks/`, so later steps do not need to
write into its container-owned output directory.
The documentation remains at the site root. Pull requests build and test without
deploying. Only runs on `main` can deploy, including manually triggered runs.
Changes appear publicly after the pull request is merged and Pages deployment
completes; opening a pull request does not publish them.

## Image and claim provenance

The local screenshots show the public Learn to Cloud home page, a crop of its
public sign-in link button, and the assets panel of GitHub release `v0.1.8`.
They were captured for this presentation on September 21, 2026; each image
is kept below 500 KB. They do not depict a private learner account.
Synthetic diagrams are explicitly labeled in the slides rather than presented
as screenshots of real learner activity.

The claim of over 9,000 registered learners and the speaker's personal timeline
are speaker-supplied, not independently queried measurements.
