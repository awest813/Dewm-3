#!/usr/bin/env python3
"""serve.py — local HTTP server for the dhewm3 web build.

Serves a directory (default: build-web) with:
  - correct MIME types (.wasm -> application/wasm, .js -> text/javascript,
    .data -> application/octet-stream)
  - no-cache headers for engine files (iterate fast, avoid stale .wasm)
  - COOP/COEP headers (required for SharedArrayBuffer / -pthread builds;
    harmless for single-threaded builds; disable with --no-coop)

Usage:
  python3 web/serve.py [--dir build-web] [--port 8080] [--no-coop]
  then open http://localhost:8080/dhewm3.html
"""
import argparse
import functools
import http.server
import os

MIME_OVERRIDES = {
    ".wasm": "application/wasm",
    ".js": "text/javascript",
    ".data": "application/octet-stream",
    ".pk4": "application/octet-stream",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    use_coop = True

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        if self.use_coop:
            # Needed for crossOriginIsolated (threads); harmless otherwise.
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()

    def guess_type(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext in MIME_OVERRIDES:
            return MIME_OVERRIDES[ext]
        return super().guess_type(path)

    def log_message(self, fmt, *args):  # quieter logs
        pass


def main():
    ap = argparse.ArgumentParser(description="Serve the dhewm3 web build")
    ap.add_argument("--dir", default="build-web", help="directory to serve")
    ap.add_argument("--port", type=int, default=8080, help="port to listen on")
    ap.add_argument("--no-coop", action="store_true", help="skip COOP/COEP headers")
    args = ap.parse_args()

    if not os.path.isdir(args.dir):
        print("error: directory '%s' does not exist." % args.dir)
        print("build it first: emcmake cmake -S neo --preset web-wasm -B build-web")
        raise SystemExit(1)

    Handler.use_coop = not args.no_coop
    handler = functools.partial(Handler, directory=args.dir)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print("Serving %s at http://localhost:%d/dhewm3.html" % (args.dir, args.port))
    print("Press Ctrl-C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
