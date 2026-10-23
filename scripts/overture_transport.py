"""Loopback-only relay to one fixed public file, with serial bounded HTTP reads."""

import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

from app.download_budget import DownloadBudget


@contextmanager
def paced_file(url):
    budget = DownloadBudget()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_HEAD(self):
            self.transfer("HEAD")

        def do_GET(self):
            self.transfer("GET")

        def transfer(self, method):
            if self.path != "/places.parquet":
                self.send_error(404)
                return
            started = False
            try:
                budget.request()
                headers = {"Accept-Encoding": "identity"}
                if self.headers.get("Range"):
                    headers["Range"] = self.headers["Range"]
                with httpx.stream(
                    method, url, headers=headers, timeout=30, follow_redirects=False
                ) as response:
                    if response.status_code not in {200, 206}:
                        self.send_error(503)
                        return
                    size = int(response.headers.get("content-length", "0"))
                    if method == "GET" and (
                        size <= 0 or size > budget.max_bytes - budget.bytes
                    ):
                        self.send_error(413)
                        return
                    self.send_response(response.status_code)
                    for key in (
                        "content-length",
                        "content-range",
                        "accept-ranges",
                        "content-type",
                        "etag",
                        "last-modified",
                    ):
                        if key in response.headers:
                            self.send_header(key, response.headers[key])
                    self.end_headers()
                    started = True
                    if method == "GET":
                        for block in response.iter_raw(65536):
                            budget.received(len(block))
                            time.sleep(len(block) / (512 * 1024))
                            self.wfile.write(block)
            except (ValueError, httpx.HTTPError, OSError):
                if not started:
                    self.send_error(503)
                self.close_connection = True

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/places.parquet", budget
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=35)
