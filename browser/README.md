# xiaobei-browser runtime

The 5.8 browser runtime uses the main-repository TypeScript SDK `camoufox 0.5.9`, `fpgen-js 1.3.0`, `playwright-core 1.62.1` and its paired browser `158.0.1-beta.41`. Node >=22.15 is required; the full product follows OpenClaw's higher Node requirement. The runtime owns its dependency tree. Do not hoist it into OpenClaw's Playwright 1.63.

The architecture, remaining validation, profile reset policy and snapshot/OSBI roadmap are maintained in [the browser development guide](../docs/browser-architecture.md). This package does not switch installed commands or production services merely by being built.

Use the shared installer/update script for SDK, build and asset cutover. Source updates keep an installed 0.5.8 SDK on its paired asset lock; packaging uses the target lock. Installation verifies the built driver and pinned dependencies/assets without starting a browser or resetting profiles. Compatible v2 identities created by 0.5.8 keep their original creator tag and fingerprint under 0.5.9; v1, unknown SDKs and invalid identities still require recovery.

Official browser bundles include UBO. Installation validates its pinned version before moving files and retains the standalone XPI fallback. macOS uses `Camoufox.app/Contents/Resources/addons/UBO`. Runtime startup selects the installed fpgen model through the public `setModelDir` API.

## Build and isolated validation

```bash
npm ci --ignore-scripts --prefix browser
npm run build --prefix browser

# All state and downloaded assets in ignored test/, away from existing profiles/cache.
export XIAOBEI_BROWSER_HOME="$PWD/test/browser/manual-state"
export XIAOBEI_BROWSER_ASSETS="$PWD/test/browser/manual-assets"
node browser/dist/cli.js doctor --json
node browser/scripts/install-assets.mjs
node browser/dist/cli.js --session demo --no-geoip start --json
node browser/dist/cli.js --session demo open about:blank --json
node browser/dist/cli.js --session demo snapshot --json
node browser/dist/cli.js --session demo stop --json

XIAOBEI_BROWSER_E2E=1 node --test test/browser/*.test.mjs
```

Asset installation is explicit and checksum verified, including the fpgen model, GeoIP AIO and uBlock Origin. Runtime startup fails if required assets are missing. Default assets live in `~/.camoufox-cli/assets/<version>-<release>/`; `CAMOUFOX_INSTALL_DIR` overrides the parent, `XIAOBEI_BROWSER_ASSETS` overrides the complete directory. Pre-downloaded browser/addon/GeoIP files are read from `~/.xiaobei/cache/` by their original URL filenames and still verified. `XIAOBEI_CACHE_DIR` overrides the shared cache; `XIAOBEI_BROWSER_DOWNLOADS` takes precedence for browser resources. The new asset directory does not replace the old SDK cache. PowerShell uses the same Node/JS entries and `$env:XIAOBEI_BROWSER_HOME` / `$env:XIAOBEI_BROWSER_ASSETS` for isolation.

Release tarballs carry the pinned GeoIP database in `data/geoip-aio-all-<version>.mmdb` and the original signed uBlock XPI in `data/ublock_origin-<version>.xpi`, prepared by `scripts/prepare-browser-data.mjs`. Installation verifies and uses those copies before consulting the download cache or upstream, then validates the uBlock manifest version. Customer installation needs neither the Mozilla download nor the historical GeoIP release. GeoIP upstream retains only two weekly releases; installed databases also use a versioned filename so a pin update preserves the earlier database rather than comparing its contents against the new hash.

Identity schema v2 records the SDK and fpgen identity. Old v1, corrupt or populated profiles without a compatible identity return `PROFILE_RESET_REQUIRED`; archive the whole old profile after stopping its session and use a fresh profile with a new login. Do not inject old cookies into a new identity. This release does not implement an automatic profile purge or lossless old-identity conversion.

## Interfaces

- `@wiseflow/browser/client`: shared `BrowserClient` and `resolveLaunchOptions`; start/status/sessions/request/stop. Status is read-only; stop waits for registration release.
- `@wiseflow/browser/protocol`: versioned requests, responses and errors.
- `@wiseflow/browser/driver`: controlled SDK launcher for isolated rendering/recording, sharing the same SDK/assets. Normal session callers use the client.
- `dist/cli.js`: `xiaobei-browser`, default persistent `default` profile.
- `dist/compat/cli.js`: `camoufox-cli` grammar/envelope; implicit ephemeral behavior retained, use `--persistent` when needed.
- `bridge/xiaobei_browser.py`: explicit Node + JS with JSON stdin and no shell, not a Python Camoufox SDK. Supply `node=` / `XIAOBEI_BROWSER_NODE`, and `home=` for isolated tests.

`--request-file FILE` / `--request-stdin` accept `{ "action": "eval", "params": { "expression": "document.title" } }` and optional requestId. Task ownership uses lease acquire/renew/wait/release and `--lease-token`. UTF-8 output is a single JSON result. A timeout after dispatch means `OUTCOME_UNKNOWN`; do not retry side effects automatically. `close --all` remains unsupported.

## OpenClaw plugin and lifecycle service

`browser/openclaw.plugin.json` and `plugin/index.ts` register the independent `xiaobei-browser` plugin through the public OpenClaw 2026.10.10 SDK. Its `xiaobei_browser` tool replaces the native browser tool. The public `skills/browser-guide/` skill remains in the normal shared skill layout; there is no second plugin-specific copy. Tool/file/evaluate/network restrictions remain enforced, including the native upload/inbound-media path rules. Unsupported SSRF/sandbox/run-bound policies fail closed.

The plugin service publishes an authenticated local broker in this installation's private runtime registry. `BrowserClient.start()` and both CLIs delegate startup to that service; subsequent actions reuse the per-session IPC endpoint. A browser launched for an agent exec is a child of the service owner, so command-tree cleanup cannot close the login window. A missing service returns `BROKER_REQUIRED` inside OpenClaw instead of launching a disposable daemon. Standalone CLI use without a Gateway retains local startup. A live but unreachable broker never falls back to local startup, and a start dispatched before a timeout is not replayed.

The service tracks its own daemon generations. Stopping it drains admitted starts and retires only its browsers, including human-wait leases, without deleting profiles or stopping foreign sessions. Manual-login wait stays protected during normal operation. Session actions and lease ownership remain unchanged; the broker is not a second browser driver.

Install/update runs `scripts/configure-browser-plugin.mjs` after the package is built. It registers the product's absolute plugin path, disables the native browser plugin, preserves explicit browser/plugin disables and existing browser options, and migrates exact browser tool policies to `xiaobei_browser`. The script validates staged configuration with the built host, backs up the original and refuses a concurrent config change. Browser source/summary patches are no longer shipped. Current snapshots remain public default ARIA snapshots plus DOM-bound action refs; extraction projections remain planned.

Runtime tests and fixtures live in ignored repository-root `test/browser/`; shared renderer/installer regressions live in `test/shared-playwright/`; they must be transferred separately to other machines. Real E2E uses fresh profiles and local HTTP pages. Recording additionally needs the Playwright-version-specific FFmpeg executable; native Windows/macOS, actual platform logins, deployment, cancellation and special DOM coverage remain separate acceptance items. See the guide for evidence and limitations, including the observed varying `deBG` PNG ancillary chunk on FF156.

## Shared Playwright and Chromium

`browser/package.json` owns the Playwright version for all xiaobei skills. The
single driver is `browser/node_modules/playwright-core`; the single Chromium
headless shell cache is `browser/.browsers`, independent of cwd or an inherited
`PLAYWRIGHT_BROWSERS_PATH`. Normal source, tarball and Docker installation
preinstalls it through `scripts/install-browser.mjs`. To repair only this runtime:

```bash
node scripts/install-playwright.mjs
```

Node callers use `browser/scripts/shared-playwright.mjs` (`launchChromium`,
`sharedPlaywrightInfo`, `requirePlaywright`); Python callers use
`browser/bridge/shared_playwright.py`. Skills must not declare their own
Playwright package or use Python Playwright/system Chrome as another driver.
Missing assets fail with a repair instruction; skill execution never downloads.
Camoufox remains the shared browser for platform sessions and browsing.

The installer removes the retired deck-render browser cache and private
Playwright copies in deck-render/ui-demo after the shared shell is ready. It does
not remove system Chrome or the user's global Playwright cache, which may serve
other applications. Chromium revisions follow the owner package and are managed
in the same cache by Playwright ([browser installation](https://playwright.dev/docs/browsers)).
