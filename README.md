# shorts-lockdown

Make **YouTube Shorts unreachable on a Linux desktop** while the rest of YouTube
(and every other site/app) keeps working. Built as a *self-commitment* tool: the
"adversary" is the machine's own user in a weak moment, who also has `sudo`.

Goal is not "impossible for root" (nothing is) but "far more effort than an impulse
lasts": root-owned, immutable, self-healing, verified, with no unlock path.

> Agents: read **[AGENTS.md](AGENTS.md)** before touching anything. Machines differ;
> it has the discovery checklist, exact install/verify steps and the hard rules.

## What it blocks

| Door | How | Result |
|---|---|---|
| `youtube.com/shorts/…`, `m.`, no-www, http, `/feed/shorts` (typed, links, redirects) | Firefox/LibreWolf enterprise policy `WebsiteFilter` | "Blocked Page" |
| Clicking a Short **inside** YouTube (SPA navigation, no page load) | uBlock Origin, force-installed by policy, with an admin-managed filter list | player never starts (`play()` throws), no audio |
| A Short opened as a normal video (`/watch?v=ID`, embeds) | uBO scriptlets strip `streamingData` when `isShortsEligible:true` | "An error occurred" |
| Shorts button, shelves, tabs, chips, links | uBO cosmetic filters | not shown |
| Disabling uBO on YouTube / Safe Mode | policy `force_installed`, `DisableSafeMode`, managed `trustedSiteDirectives` with YouTube stripped | not possible from the UI |
| yt-dlp / mpv | `/etc/yt-dlp.conf` `--match-filters` on `media_type` (`short` even for `/watch?v=`) | Shorts skipped |
| FreeTube | settings `hideChannelShorts`, `hideSubscriptionsShorts` re-forced | hidden |
| Chromium / Chrome / Brave / Vivaldi / Edge (even before being installed) | managed `URLBlocklist` | direct URLs blocked |

## What it does NOT cover (honest limits)

- A user with sudo and time can undo it. Mitigations: immutability, self-repair,
  remote read-only watcher + alert, and agents instructed never to help.
- Pasting a Short link directly into FreeTube.
- A portable browser that ignores system policies (e.g. a tarball in `$HOME`).
- Chromium-family browsers only get the direct-URL block (no uBO hardening).
- YouTube UI changes may resurface entry points; the *player* blocks are the backstop.
  Maintenance may only harden, never weaken (see AGENTS.md).

## Architecture

```
/usr/local/lib/shorts-guard/        (all files chattr +i)
  apply.py        renders + enforces everything, idempotent; --check / --install
  shorts.txt      uBO filter list (network + cosmetic + scriptlets)
  serve.py        HTTPS server for that list on 127.0.0.1:8737 (systemd DynamicUser)
  tls/            name-constrained local CA (only valid for 127.0.0.1/localhost) + server cert
  systemd/        unit sources (installed to /etc/systemd/system)
  zz-shorts-guard.hook   pacman hook: re-apply after browser/yt-dlp upgrades
/etc/shorts-guard/config.json       {"user": "<desktop user>"}
/var/lib/shorts-guard/ubo-state.json  last-seen uBO lists/allowlist (fallback)
/root/shorts-guard/ca.key           CA key (root only, for re-issuing)
```

Rendered outputs (immutable, rewritten only if content differs):
`/etc/librewolf/policies/policies.json`, `/etc/firefox/policies/policies.json`,
Chromium-family `…/policies/managed/zz-shorts-guard.json`, `/etc/yt-dlp.conf`,
`/srv/shorts-guard/shorts.txt`, systemd units, pacman hook; FreeTube settings (user-owned, re-forced).

Self-healing: `shorts-guard.path` (instant, on change), `shorts-guard.timer` (every 2 min),
`shorts-guard-boot.service` (before the display manager), pacman hook. A tampered output is
restored in ~2 s.

Key design points (details in [docs/LESSONS.md](docs/LESSONS.md)):
- `/etc/<app>/policies/policies.json` **replaces** the package's distribution policies, so
  `apply.py` merges the distribution file + our overlay on every run.
- uBO's admin list must be **trusted** to use `trusted-override-element-method`; uBO only
  trusts `https://` (or `file:///`) prefixes → local HTTPS with a name-constrained CA
  installed through the `Certificates` policy.
- The user's own uBO choices are preserved: `apply.py` reads their current selected lists
  and allowlist from the browser profile (pure-Python snappy + IndexedDB reader) and feeds
  them back through policy, adding our list and removing any YouTube allowlist entry.

## Install (summary)

```bash
sudo ./install.sh --user <desktop-user>
# then fully quit and reopen EACH browser twice (uBO applies admin settings one start late)
```

Optional remote watcher (another machine, read-only): see AGENTS.md § Watcher.

## Tests

- `tests/harness.py` + `tests/smoke.py`: throwaway headless profile, **muted**.
- `tests/live-tab.py` + `tests/live-probe.js`: probe the real logged-in session in a
  temporary background tab (logged-in YouTube behaves differently from anonymous!).
- `python3 -I /usr/local/lib/shorts-guard/apply.py --check` → `OK` / `DRIFT` (works unprivileged).
