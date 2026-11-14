#!/bin/bash
# shorts-lockdown installer. Idempotent: safe to re-run (keeps existing TLS CA).
# Usage: sudo ./install.sh --user <desktop-user>
set -euo pipefail

usage() { echo "usage: sudo $0 --user <desktop-user>" >&2; exit 2; }
USER_NAME=""
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_NAME="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$USER_NAME" ] || usage
[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
id "$USER_NAME" >/dev/null 2>&1 || { echo "no such user: $USER_NAME" >&2; exit 1; }
for b in python3 openssl chattr lsattr systemctl; do
  command -v "$b" >/dev/null || { echo "missing dependency: $b" >&2; exit 1; }
done

HERE="$(cd "$(dirname "$0")" && pwd)"
L=/usr/local/lib/shorts-guard
KEEP=/root/shorts-guard

unlock() { [ -e "$1" ] && chattr -i "$1" 2>/dev/null || true; }

echo "==> bundle -> $L"
install -d -m755 "$L" "$L/systemd" "$L/tls"
install -d -m700 "$KEEP"
for f in "$L"/* "$L"/systemd/* "$L"/tls/*; do unlock "$f"; done
install -m755 "$HERE/src/apply.py" "$HERE/src/serve.py" "$L/"
install -m644 "$HERE/src/shorts.txt" "$HERE/src/zz-shorts-guard.hook" "$L/"
install -m644 "$HERE"/src/systemd/* "$L/systemd/"

if [ ! -s "$L/tls/ca.crt" ] || [ ! -s "$L/tls/srv.key" ]; then
  echo "==> generating name-constrained local CA (valid only for 127.0.0.1/localhost)"
  T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
    -keyout "$T/ca.key" -out "$T/ca.crt" -days 7300 -config "$HERE/src/ca.cnf" 2>/dev/null
  openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
    -keyout "$T/srv.key" -out "$T/srv.csr" -subj "/O=shorts-guard list server" 2>/dev/null
  openssl x509 -req -in "$T/srv.csr" -CA "$T/ca.crt" -CAkey "$T/ca.key" -CAcreateserial \
    -out "$T/srv.crt" -days 3650 -extfile "$HERE/src/srv.cnf" 2>/dev/null
  openssl verify -CAfile "$T/ca.crt" "$T/srv.crt" >/dev/null
  install -m644 "$T/ca.crt" "$T/srv.crt" "$L/tls/"
  install -m600 "$T/srv.key" "$L/tls/srv.key"
  install -m600 "$T/ca.key" "$KEEP/ca.key"
fi

echo "==> config"
install -d -m755 /etc/shorts-guard
unlock /etc/shorts-guard/config.json
printf '{"user": "%s"}\n' "$USER_NAME" > /etc/shorts-guard/config.json
chmod 644 /etc/shorts-guard/config.json

echo "==> lock bundle (chattr +i)"
chattr +i "$L"/apply.py "$L"/serve.py "$L"/shorts.txt "$L"/zz-shorts-guard.hook \
  "$L"/systemd/* "$L"/tls/* /etc/shorts-guard/config.json

echo "==> apply + enable units"
python3 -I "$L/apply.py" --install >/dev/null
systemctl restart shorts-guard-list.service
sleep 1
python3 -I "$L/apply.py" --check

cat <<EOF

Installed. Remaining manual step:
  Fully quit the browser and reopen it TWICE (wait ~1 min after the first start).
  uBlock Origin caches policy-provided settings and only applies them on the
  start after it first sees them.
Verify with the steps in AGENTS.md ("Verification").
EOF
