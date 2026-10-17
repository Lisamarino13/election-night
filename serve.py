#!/usr/bin/env python3
"""Local preview server for the board. Serves this directory on :8777."""
import http.server, socketserver, os, functools
ROOT = os.path.dirname(os.path.abspath(__file__))
H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", 8777), H) as s:
    print(f"serving {ROOT} on http://127.0.0.1:8777", flush=True)
    s.serve_forever()
