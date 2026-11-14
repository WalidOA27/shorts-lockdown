# WebDriver harness: throwaway headless LibreWolf/Firefox profile (policies apply to it).
# ALWAYS muted (media.volume_scale=0): headless browsers still play sound.
# Usage: python3 -I harness.py smoke.py   (needs geckodriver; ports 4455/2829 free)
import json, sys, time, urllib.request, subprocess, tempfile, os
WD = "http://127.0.0.1:4455"
def req(m, p, body=None):
    r = urllib.request.Request(WD + p, method=m, data=json.dumps(body).encode() if body is not None else None,
                               headers={"Content-Type": "application/json"})
    try: return json.load(urllib.request.urlopen(r, timeout=120))["value"]
    except urllib.error.HTTPError as e: return json.load(e)["value"]
prof = tempfile.mkdtemp(prefix="sg-prof-")
gd = subprocess.Popen(["geckodriver", "--port", "4455", "--marionette-port", "2829"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
sess = req("POST", "/session", {"capabilities": {"alwaysMatch": {"moz:firefoxOptions": {
    "binary": os.environ.get("BROWSER_BIN", "/usr/lib/librewolf/librewolf"), "args": ["-headless", "-profile", prof],
    "prefs": {"privacy.resistFingerprinting": False, "media.volume_scale": "0.0", "media.autoplay.default": 0, "media.autoplay.blocking_policy": 0}}}}})
sid = sess["sessionId"]
def go(u):
    req("POST", f"/session/{sid}/url", {"url": u})
def js(s, *a):
    return req("POST", f"/session/{sid}/execute/sync", {"script": s, "args": list(a)})
def url(): return req("GET", f"/session/{sid}/url")
try:
    exec(open(sys.argv[1]).read())
finally:
    req("DELETE", f"/session/{sid}"); gd.terminate()
