# Smoke test: normal videos play from channel/search, Shorts never play. Run via harness.py.
time.sleep(90)
def st(): return js("return [...document.querySelectorAll('video')].filter(v=>v.isConnected).map(v=>[v.readyState, Math.round(v.currentTime), v.paused, !!v.offsetParent])")
def clickwatch():
    return js("const a=[...document.querySelectorAll('a[href^=\"/watch\"]')].find(a=>a.offsetParent); if(!a) return 'none'; a.click(); return a.getAttribute('href').slice(0,30)")
go("https://www.youtube.com/@YouTube/videos"); time.sleep(10)
print("click normal", clickwatch()); time.sleep(12); print("normal:", url()[-25:], st())
go("https://www.youtube.com/@YouTube/shorts"); time.sleep(8)
js("document.querySelector('a[href^=\"/shorts/\"]').click()"); time.sleep(12); print("short:", url()[-25:], st())
js("history.back()"); time.sleep(6); go("https://www.youtube.com/@YouTube/videos"); time.sleep(8)
print("click normal after short", clickwatch()); time.sleep(12); print("normal2:", url()[-25:], st())
go("https://www.youtube.com/results?search_query=music"); time.sleep(8)
print("click from search", clickwatch()); time.sleep(12); print("search->watch:", url()[-25:], st())
print("sidebar related links:", js("return document.querySelectorAll('#related a[href^=\"/watch\"]').length"))
