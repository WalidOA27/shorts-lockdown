#!/usr/bin/python3 -I
"""HTTPS static server for the shorts-guard uBO list (127.0.0.1 only)."""
import http.server, os, ssl, functools
d = os.environ.get("CREDENTIALS_DIRECTORY", "/usr/local/lib/shorts-guard/tls")
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain("/usr/local/lib/shorts-guard/tls/srv.crt", os.path.join(d, "srv.key"))
H = functools.partial(http.server.SimpleHTTPRequestHandler, directory="/srv/shorts-guard")
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8737), H)
srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
srv.serve_forever()
