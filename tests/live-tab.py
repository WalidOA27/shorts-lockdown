# Opens a temporary background tab in the running browser via Marionette (port 2828,
# browser must be started with --marionette), runs a JS file, closes the tab.
# Read-only by intent; one Marionette client at a time (check nothing else is connected).
import socket, json, sys, time
s = socket.create_connection(("127.0.0.1", 2828), timeout=60)
buf = b""
def recv():
    global buf
    while b":" not in buf: buf += s.recv(65536)
    n, rest = buf.split(b":", 1); n = int(n)
    while len(rest) < n: rest += s.recv(65536)
    buf = rest[n:]; return json.loads(rest[:n])
mid = 0
def cmd(name, params={}):
    global mid; mid += 1
    d = json.dumps([0, mid, name, params]).encode()
    s.sendall(str(len(d)).encode() + b":" + d)
    r = recv(); return r[3] if r[2] is None else {"ERR": r[2]}
recv()
cmd("WebDriver:NewSession", {"capabilities": {}})
orig = cmd("WebDriver:GetWindowHandle")["value"]
w = cmd("WebDriver:NewWindow", {"type": "tab", "focus": False})["handle"]
cmd("WebDriver:SwitchToWindow", {"handle": w, "focus": False})
try:
    cmd("WebDriver:Navigate", {"url": "https://www.youtube.com/"}); time.sleep(10)
    r = cmd("WebDriver:ExecuteAsyncScript" if "done" in open(sys.argv[1]).read() else "WebDriver:ExecuteScript", {"script": open(sys.argv[1]).read(), "args": []})
    print(json.dumps(r, ensure_ascii=False)[:6000])
finally:
    cmd("WebDriver:CloseWindow"); cmd("WebDriver:SwitchToWindow", {"handle": orig, "focus": False})
    cmd("WebDriver:DeleteSession"); s.close()
