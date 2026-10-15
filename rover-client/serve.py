#!/usr/bin/env python3
"""SMARS Rover Client — serves src/ on http://localhost:1430 and opens the browser."""
import http.server, socketserver, webbrowser, threading, os

PORT = 1430
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
threading.Timer(0.3, webbrowser.open, args=[f"http://localhost:{PORT}"]).start()
with socketserver.TCPServer(("", PORT), http.server.SimpleHTTPRequestHandler) as httpd:
    print(f"Rover client → http://localhost:{PORT}  (Ctrl+C to stop)")
    httpd.serve_forever()
