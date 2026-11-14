# Lessons learned (verified 2026-11, LibreWolf/Firefox 159, uBO 1.74, yt-dlp 2026.08)

Each item cost real debugging time. Verify again if versions move far.

## Browser policies
- Linux Firefox-family builds read `/etc/<appname>/policies/policies.json` (dirsvc `SysConfD`,
  needs `MOZ_SYSTEM_POLICIES`). **If it exists it replaces** `<install>/distribution/policies.json`
  entirely — merge, don't overwrite, or you silently drop the distro's own policies.
- `browser.policies.alternatePath` is honored only in automation/Nightly → users can't redirect policies via about:config.
- `WebsiteFilter` only checks top-level/sub-document/object loads and redirects. It **does not**
  see SPA navigations (`history.pushState`) — YouTube opens Shorts in-app without a page load.
- Policies load at browser start. A browser open since before install is unprotected until restarted.
  Check `ps -o lstart -C librewolf,firefox`. Every browser and every profile counts.
- `DisableSafeMode` matters: troubleshoot mode starts without extensions.
- `Certificates.Install` accepts absolute paths; combine with a **name-constrained** CA
  (`permitted;IP:127.0.0.1/255.255.255.255`, `DNS:localhost`) so the added root can't vouch for any
  real site. OpenSSL rejects a leaf whose subject CN looks like a hostname outside the
  constraint — use `/O=…` without CN, SAN `IP:127.0.0.1`.

## uBlock Origin (managed storage via policy `3rdparty.Extensions["uBlock0@raymondhill.net"]`)
- Keys (1.74): `toOverwrite.{filters,filterLists,trustedSiteDirectives}`, `toAdd.trustedSiteDirectives`,
  `advancedSettings`, `userSettings`, `disableDashboard`, `disabledPopupPanelParts`. No `toAdd.filters`.
- `toOverwrite.filters` would wipe the user's "My filters" — don't. Use `filterLists` with an
  extra list URL instead, and feed back the user's current lists so nothing changes for them.
- uBO **caches managed storage** (`cachedManagedStorage`) and applies it on the *next* start →
  every policy change needs **two** browser restarts. This explained "nothing is fixed" twice.
- Scriptlets named `trusted-*` only run from trusted lists. `trustedListPrefixes`
  (`advancedSettings`) ignores `http://` prefixes; `https://` (with hostname) or `file:///` only.
  → serve the list over local HTTPS.
- Non-trusted `json-edit-*` scriptlets can only *remove* properties. uBO JSONPath syntax:
  filters are `[?.key==value]` (**no parentheses**); `A;$B` = "if A matches anything, apply B from root".
  Working query: `..playerMicroformatRenderer[?.isShortsEligible==true];$..streamingData`.
  Test offline: `import { JSONPath } from './js/jsonpath.js'` from the unpacked xpi under node.
- `:remove()` procedural filters are throttled (~2–3 s) → a Short still played audio for seconds.
  Cosmetic hiding never stops audio. The real fix: `trusted-override-element-method,
  HTMLMediaElement.prototype.play, <shorts video selector>, throw`.
- Reading uBO state from disk: profile `storage/default/moz-extension+++<uuid>^userContextId=4294967295/idb/*.sqlite`;
  uuid from `extensions.webextensions.uuids` in `prefs.js`; keys are `"0" + chr(c+1)` per char;
  values are raw-snappy structured clones (pure-Python decoder in apply.py). Open with `?immutable=1`.

## YouTube
- Anonymous headless YouTube ≠ logged-in YouTube. Logged-in in-app Shorts got media with **no**
  `/youtubei/v1/player` fetch (delivered via googlevideo/onesie path), so response editing never
  saw it. Always validate against the real session (`tests/live-tab.py`).
- `isShortsEligible` in `microformat.playerMicroformatRenderer` marks Shorts even at `/watch?v=`.
- `reel/` endpoints (`reel_item_watch`, `reel_watch_sequence`) are Shorts-only; safe to block.
- Shorts player DOM: `ytd-shorts … ytd-reel-video-renderer … div#shorts-player video`.

## yt-dlp
- System config `/etc/yt-dlp.conf` is read by user installs too.
- `media_type == 'short'` (from `isShortsEligible`) catches Shorts by any URL form.
- Use **none-inclusive** operators (`!=?`, `!*=?`): a missing field otherwise *rejects* the video,
  which would break every non-YouTube extractor.
- Limits: `--ignore-config`, `--no-match-filters` bypass it (friction only).

## Operations
- Headless browsers output audio; the user heard test videos. Mute always.
- `pkill -f 'librewolf.*-headless'` killed the agent's own shell (pattern in its argv).
- systemd `DynamicUser` services can't read root-600 keys → `LoadCredential=`.
- Watcher over SSH: forced-command key with `restrict,from=…`; use `ssh -T … </dev/null`
  or the "Pseudo-terminal will not be allocated" line breaks output parsing.
- Root-repair from another machine = that machine gets root here. Offer read-only + alert instead.
