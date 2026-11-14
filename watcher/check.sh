#!/bin/bash
# Read-only remote watcher. Runs on ANOTHER machine; asks the guarded machine
# (via a forced-command SSH key) whether shorts-guard is intact and alerts on change.
# Config: ~/.config/shorts-watch/env  (chmod 600)
#   HOSTS="192.0.2.10 192.0.2.11"   # addresses of the guarded machine, tried in order
#   TARGET_USER=alice                # user on the guarded machine holding the forced key
#   KEY=~/.ssh/shorts_watch
#   NTFY_URL=https://ntfy.example/topic   NTFY_TOKEN=tk_...   (optional)
set -u
CONF=~/.config/shorts-watch/env; [ -f "$CONF" ] && source "$CONF"
KEY=${KEY:-~/.ssh/shorts_watch}; ST=~/.config/shorts-watch/state
prev=$(cat "$ST" 2>/dev/null || echo OK); fails=$(cat "$ST.n" 2>/dev/null || echo 0)
res=UNREACHABLE
for h in ${HOSTS:-}; do
  out=$(ssh -i "$KEY" -o BatchMode=yes -T -o ConnectTimeout=6 "$TARGET_USER@$h" </dev/null 2>&1); rc=$?
  if [ $rc -eq 0 ] && [ "$out" = OK ]; then res=OK; break; fi
  if echo "$out" | grep -q DRIFT; then res=DRIFT; break; fi
  if echo "$out" | grep -qi "permission denied"; then res=KEY_REMOVED; break; fi
done
[ $res = UNREACHABLE ] && exit 0          # machine off: nothing to report
if [ $res = OK ]; then fails=0; else fails=$((fails+1)); fi
echo $fails > "$ST.n"
cur=$res; [ $res != OK ] && [ $fails -lt 2 ] && cur=$prev   # need 2 bad checks in a row
if [ "$cur" != "$prev" ]; then
  if [ "$cur" = OK ]; then msg="shorts-guard: back to OK"; prio=3; else msg="shorts-guard tampered ($cur)"; prio=4; fi
  logger -t shorts-watch "$msg"
  [ -n "${NTFY_URL:-}" ] && curl -s -o /dev/null ${NTFY_TOKEN:+-H "Authorization: Bearer $NTFY_TOKEN"} \
    -H "Title: shorts-guard" -H "Priority: $prio" -d "$msg" "$NTFY_URL"
fi
echo "$cur" > "$ST"
