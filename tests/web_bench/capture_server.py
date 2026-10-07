"""Local-only sink for bench captures and results (see tests/web_bench/prepare.py).

python tests/web_bench/capture_server.py --out build-web/bench/captures

Accepts POST /<name> from the bench page and writes the body to --out/<name>.
Binds 127.0.0.1 only, answers only pages served from a loopback origin, and
restricts names to [A-Za-z0-9_.-] (no leading dot).
"""
import argparse
import http.server
import os
import re
from urllib.parse import urlsplit

NAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]*')


def loopback(origin):
    try:
        return urlsplit(origin).hostname in ('localhost', '127.0.0.1', '::1')
    except ValueError:
        return False


def handler(out):
    class Handler(http.server.BaseHTTPRequestHandler):
        def _headers(self, code):
            self.send_response(code)
            # The bench page is served cross-origin (port 8090, COEP). Other
            # sites open in the same browser must not be able to write here.
            origin = self.headers.get('Origin', '')
            if loopback(origin):
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Cross-Origin-Resource-Policy', 'cross-origin')
            self.end_headers()

        def do_OPTIONS(self):
            self._headers(204)

        def do_POST(self):
            name = self.path.lstrip('/')
            origin = self.headers.get('Origin')
            if not NAME.fullmatch(name) or (origin is not None and not loopback(origin)):
                self._headers(403 if NAME.fullmatch(name) else 400)
                return
            data = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            with open(os.path.join(out, name), 'wb') as f:
                f.write(data)
            self._headers(200)

        def log_message(self, *args):
            pass
    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default='build-web/bench/captures')
    ap.add_argument('--port', type=int, default=8091)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    print(f'Writing bench captures to {args.out} (http://127.0.0.1:{args.port}/)')
    http.server.ThreadingHTTPServer(('127.0.0.1', args.port), handler(args.out)).serve_forever()


if __name__ == '__main__':
    main()
