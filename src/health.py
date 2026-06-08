from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return


def start_health_server(port=8765):
    def _run():
        server = HTTPServer(("127.0.0.1", port), Handler)
        server.serve_forever()

    t = Thread(target=_run, daemon=True)
    t.start()
