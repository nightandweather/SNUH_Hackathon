#!/usr/bin/env python3
"""Run SICU LINK with Python's standard library."""
import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import webbrowser

WEB = Path(__file__).resolve().parent / 'web'


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def list_directory(self, path):
        self.send_error(403, 'Directory listing is disabled.')
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8003)
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('--port must be between 0 and 65535')
    if not (WEB / 'index.html').is_file():
        parser.exit(1, 'The web folder is missing. Extract the complete ZIP first.\n')
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port),
                    functools.partial(Handler, directory=str(WEB)))
    except OSError as error:
        parser.exit(1, 'Could not start SICU LINK: %s\nTry --port 8004.\n' % error)
    with server:
        url = 'http://127.0.0.1:%s/?lang=ko' % server.server_address[1]
        print('SICU LINK: ' + url, flush=True)
        print('Ctrl+C to stop', flush=True)
        if args.open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
