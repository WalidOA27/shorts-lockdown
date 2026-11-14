#!/usr/bin/python3 -I
"""shorts-guard: keeps YouTube Shorts unreachable on this machine.

Renders every enforcement file from this bundle + package defaults, writes only
when content differs, and marks outputs immutable. Idempotent; run as root.
  apply.py            render + enforce
  apply.py --check    exit 1 if anything is missing/different (no changes)
  apply.py --install  also (re)install systemd units + pacman hook and enable them
"""
import copy, glob, hashlib, json, os, pwd, re, sqlite3, subprocess, sys

HERE = "/usr/local/lib/shorts-guard"
STATE = "/var/lib/shorts-guard"
CONF = "/etc/shorts-guard/config.json"
try:
    _conf = json.load(open(CONF))
except Exception:
    _conf = {}
USER = _conf.get("user") or os.environ.get("SHORTS_GUARD_USER", "")
LIST_URL = "https://127.0.0.1:8737/shorts.txt"
CA_CERT = "/usr/local/lib/shorts-guard/tls/ca.crt"
UBO = "uBlock0@raymondhill.net"
UBO_XPI = "https://addons.mozilla.org/firefox/downloads/latest/uBlock0@raymondhill.net/latest.xpi"

BLOCK_MOZ = [
    "*://*.youtube.com/shorts*", "*://youtube.com/shorts*",
    "*://*.youtube.com/feed/shorts*", "*://youtube.com/feed/shorts*",
    "*://*.youtube-nocookie.com/shorts*",
]
BLOCK_CHROMIUM = [
    "youtube.com/shorts", "youtube.com/feed/shorts", "youtube-nocookie.com/shorts",
]
CHROMIUM_DIRS = [
    "/etc/chromium/policies/managed", "/etc/opt/chrome/policies/managed",
    "/etc/brave/policies/managed", "/etc/opt/brave.com/brave/policies/managed",
    "/etc/opt/vivaldi/policies/managed", "/etc/opt/edge/policies/managed",
    "/etc/opt/chromium/policies/managed",
]
MOZ = [  # (distribution dir owned by package, our /etc policies dir)
    ("/usr/lib/librewolf/distribution", "/etc/librewolf/policies"),
    ("/usr/lib/firefox/distribution", "/etc/firefox/policies"),
]
YTDLP_CONF = "/etc/yt-dlp.conf"
YTDLP_LINE = '--match-filters "media_type!=?short & original_url!*=?/shorts/ & webpage_url!*=?/shorts/"\n'
FREETUBE_KEYS = ["hideChannelShorts", "hideSubscriptionsShorts"]

# Used only when the live uBO profile can't be read and no snapshot exists yet:
# uBO's stock defaults (keeps blocking working, never empties the list set).
FALLBACK_LISTS = ["user-filters", "ublock-filters", "ublock-badware", "ublock-privacy",
    "ublock-quick-fixes", "ublock-unbreak", "easylist", "easyprivacy", "urlhaus-1", "plowe-0"]
FALLBACK_TRUSTED = ["chrome-extension-scheme", "moz-extension-scheme"]

# ---------------------------------------------------------------- uBO live state
def snappy_raw(b):
    n = shift = i = 0
    while True:
        c = b[i]; i += 1; n |= (c & 0x7F) << shift; shift += 7
        if c < 0x80: break
    out = bytearray()
    while i < len(b):
        tag = b[i]; i += 1; t = tag & 3
        if t == 0:
            ln = (tag >> 2) + 1
            if ln > 60:
                k = ln - 60; ln = int.from_bytes(b[i:i + k], "little") + 1; i += k
            out += b[i:i + ln]; i += ln; continue
        if t == 1:
            ln = ((tag >> 2) & 7) + 4; off = ((tag >> 5) << 8) | b[i]; i += 1
        elif t == 2:
            ln = (tag >> 2) + 1; off = int.from_bytes(b[i:i + 2], "little"); i += 2
        else:
            ln = (tag >> 2) + 1; off = int.from_bytes(b[i:i + 4], "little"); i += 4
        if off == 0 or off > len(out): raise ValueError("bad snappy")
        for _ in range(ln): out.append(out[-off])
    if len(out) != n: raise ValueError("bad length")
    return bytes(out)

def idb_strings(db, key):
    enc = b"0" + bytes(c + 1 for c in key.encode())
    con = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    try:
        row = con.execute("select data from object_data where key=?", (enc,)).fetchone()
    finally:
        con.close()
    if not row: return None
    raw = row[0]
    try: raw = snappy_raw(raw)
    except Exception: pass
    s = [x.decode("utf-16le") for x in re.findall(rb"(?:[\x20-\x7e]\x00){2,}", raw)]
    s += [x.decode() for x in re.findall(rb"[\x21-\x7e]{2,}", raw.replace(b"\x00", b"\x01"))]
    out = []
    for part in s:
        for p in part.split():
            if p not in out: out.append(p)
    return out

def default_profiles():
    if not USER: return
    home = pwd.getpwnam(USER).pw_dir
    for ini in [f"{home}/.config/librewolf/librewolf/profiles.ini", f"{home}/.librewolf/profiles.ini"]:
        if not os.path.exists(ini): continue
        base = os.path.dirname(ini); sec = None; secs = {}
        for line in open(ini, errors="ignore"):
            line = line.strip()
            if line.startswith("["): sec = secs.setdefault(line, {})
            elif "=" in line and sec is not None:
                k, v = line.split("=", 1); sec[k] = v
        paths = [s["Default"] for n, s in secs.items() if n.startswith("[Install") and "Default" in s]
        paths += [s["Path"] for s in secs.values() if s.get("Default") == "1" and "Path" in s]
        for p in dict.fromkeys(paths):
            yield p if p.startswith("/") else os.path.join(base, p)

def ubo_db(profile):
    try:
        prefs = open(os.path.join(profile, "prefs.js"), errors="ignore").read()
        uuid = re.search(r'uBlock0@raymondhill\.net\\":\\"([0-9a-f-]+)', prefs).group(1)
    except Exception:
        return None
    g = glob.glob(os.path.join(profile, "storage/default", f"moz-extension+++{uuid}^userContextId=4294967295", "idb", "*.sqlite"))
    return g[0] if g else None

KEY_RE = re.compile(r"^(?:[A-Za-z0-9_.-]{3,64}|https?://\S+)$")

def touches_youtube(entry):
    e = entry.lower()
    if "youtu" in e or e in ("*", "*.*") or e.startswith("*."):
        return True
    if e.startswith("/") and e.endswith("/") and len(e) > 2:
        try: return bool(re.search(e[1:-1], "https://www.youtube.com/shorts/x"))
        except re.error: return True
    return False

def live_ubo_state():
    if os.geteuid() == 0: os.makedirs(STATE, exist_ok=True)
    snap_path = os.path.join(STATE, "ubo-state.json")
    try: snap = json.load(open(snap_path))
    except Exception: snap = {"lists": FALLBACK_LISTS, "trusted": FALLBACK_TRUSTED}
    lists, trusted = None, None
    for prof in default_profiles():
        db = ubo_db(prof)
        if not db: continue
        try:
            l = idb_strings(db, "selectedFilterLists")
            t = idb_strings(db, "netWhitelist")
        except Exception:
            continue
        if l:
            l = [x for x in l if KEY_RE.match(x) and "127.0.0.1:8737" not in x]
            if len(l) >= 3 and "user-filters" in l: lists = l
        if t is not None:
            trusted = [x for x in t if re.match(r"^[\w.*:/\-]+$", x)]
        break
    if lists is None: lists = snap["lists"]
    if trusted is None: trusted = snap["trusted"]
    trusted = [x for x in trusted if not touches_youtube(x)]
    lists = [x for x in lists if "127.0.0.1:8737" not in x]
    if "user-filters" not in lists: lists.insert(0, "user-filters")
    new = {"lists": lists, "trusted": trusted}
    if new != snap and os.geteuid() == 0:
        with open(snap_path, "w") as f: json.dump(new, f)
    return lists + [LIST_URL], trusted

# ---------------------------------------------------------------- renderers
def merge_moz(base, lists, trusted):
    pol = copy.deepcopy(base)
    p = pol.setdefault("policies", {})
    wf = p.setdefault("WebsiteFilter", {})
    blk = wf.setdefault("Block", [])
    for u in BLOCK_MOZ:
        if u not in blk: blk.append(u)
    exc = wf.get("Exceptions", [])
    wf["Exceptions"] = [e for e in exc if "youtu" not in e.lower()]
    es = p.setdefault("ExtensionSettings", {})
    u = dict(es.get(UBO, {}))
    u.update({"install_url": UBO_XPI, "installation_mode": "force_installed",
              "private_browsing": True})
    es[UBO] = u
    p["DisableSafeMode"] = True
    certs = p.setdefault("Certificates", {}).setdefault("Install", [])
    if CA_CERT not in certs: certs.append(CA_CERT)
    tp = p.setdefault("3rdparty", {}).setdefault("Extensions", {})
    tp[UBO] = {"toOverwrite": {"filterLists": lists, "trustedSiteDirectives": trusted},
               "advancedSettings": [["trustedListPrefixes", "ublock- https://127.0.0.1:8737/"]]}
    return pol

def desired_files():
    lists, trusted = live_ubo_state()
    files = {}
    for dist, etc in MOZ:
        src = os.path.join(dist, "policies.json")
        app = dist.split("/")[3]
        if not os.path.isdir(f"/usr/lib/{app}"): continue
        try: base = json.load(open(src))
        except FileNotFoundError: base = {"policies": {}}
        files[os.path.join(etc, "policies.json")] = json.dumps(merge_moz(base, lists, trusted), indent=2) + "\n"
    chrom = json.dumps({"URLBlocklist": BLOCK_CHROMIUM}, indent=2) + "\n"
    for d in CHROMIUM_DIRS:
        files[os.path.join(d, "zz-shorts-guard.json")] = chrom
    files[YTDLP_CONF] = YTDLP_LINE
    files["/srv/shorts-guard/shorts.txt"] = open(os.path.join(HERE, "shorts.txt")).read()
    return files

# ---------------------------------------------------------------- enforcement
def chattr(flag, path):
    subprocess.run(["chattr", flag, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def is_immutable(path):
    r = subprocess.run(["lsattr", "-d", path], capture_output=True, text=True)
    return r.returncode == 0 and "i" in r.stdout.split()[0]

def ensure_file(path, content, check, mode=0o644):
    try: cur = open(path).read()
    except Exception: cur = None
    ok = cur == content and is_immutable(path)
    if ok or check: return ok
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path): chattr("-i", path)
    tmp = path + ".shorts-guard.tmp"
    with open(tmp, "w") as f: f.write(content)
    os.chmod(tmp, mode); os.rename(tmp, path)
    chattr("+i", path)
    return False

def freetube(check):
    try: pw = pwd.getpwnam(USER)
    except (KeyError, TypeError): return True
    db = os.path.join(pw.pw_dir, ".config/FreeTube/settings.db")
    if not os.path.exists(db): return True
    vals = {}
    for line in open(db, errors="ignore"):
        try: d = json.loads(line)
        except Exception: continue
        if "_id" in d: vals[d["_id"]] = d.get("value")
    missing = [k for k in FREETUBE_KEYS if vals.get(k) is not True]
    if not missing or check: return not missing
    with open(db, "a") as f:
        for k in missing: f.write(json.dumps({"_id": k, "value": True}, separators=(",", ":")) + "\n")
    os.chown(db, pw.pw_uid, pw.pw_gid)
    return False

def systemd_files():
    d = {}
    for name in sorted(os.listdir(os.path.join(HERE, "systemd"))):
        d[f"/etc/systemd/system/{name}"] = open(os.path.join(HERE, "systemd", name)).read()
    d["/etc/pacman.d/hooks/zz-shorts-guard.hook"] = open(os.path.join(HERE, "zz-shorts-guard.hook")).read()
    return d

UNITS_ENABLED = ["shorts-guard.timer", "shorts-guard.path", "shorts-guard-list.service", "shorts-guard-boot.service"]

def units_ok():
    for u in UNITS_ENABLED:
        r = subprocess.run(["systemctl", "is-enabled", u], capture_output=True, text=True)
        if r.stdout.strip() != "enabled": return False
    for u in ["shorts-guard.timer", "shorts-guard.path", "shorts-guard-list.service"]:
        if subprocess.run(["systemctl", "is-active", "-q", u]).returncode: return False
    return True

def main():
    check = "--check" in sys.argv
    install = "--install" in sys.argv
    if os.geteuid() != 0 and not check: sys.exit("run as root")
    ok = True
    sysd = systemd_files()
    changed_units = False
    for p, c in sysd.items():
        good = ensure_file(p, c, check)
        if not good: changed_units = True
        ok &= good
    for p, c in desired_files().items():
        ok &= ensure_file(p, c, check)
    ok &= freetube(check)
    if not check:
        if changed_units or install: subprocess.run(["systemctl", "daemon-reload"])
        if install or not units_ok():
            subprocess.run(["systemctl", "unmask", *UNITS_ENABLED], stderr=subprocess.DEVNULL)
            subprocess.run(["systemctl", "enable", "--now", "shorts-guard.timer", "shorts-guard.path", "shorts-guard-list.service"])
            subprocess.run(["systemctl", "enable", "shorts-guard-boot.service"])
    else:
        ok &= units_ok()
    if check:
        print("OK" if ok else "DRIFT"); sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
