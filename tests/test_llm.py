"""Tests for the optional LLM summary against a fake OpenAI endpoint.

No network access: the "endpoint" is a local HTTP server on port 0.
No secrets and no real model are involved.
"""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from stale_listing_reviewer.llm import SummaryError, summarize


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.url_path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        if body.get("model") == "boom-model":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"model exploded")
            return
        if body.get("model") == "bad-shape":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"oops": True}).encode("utf-8"))
            return
        reply = {
            "choices": [
                {"message": {"content": "Start with the VHS tape; cut 5 percent today."}}
            ]
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(reply).encode("utf-8"))

    def log_message(self, *args):
        pass

    @property
    def url_path(self):
        return getattr(self, "path", "")


class SummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeOpenAIHandler)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/v1"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_success_returns_blurb(self):
        blurb = summarize("worksheet text", api_base=self.url, model="llama3.1")
        self.assertIn("VHS tape", blurb)

    def test_trailing_slash_base_is_tolerated(self):
        blurb = summarize("x", api_base=self.url + "/", model="llama3.1")
        self.assertTrue(blurb)

    def test_full_endpoint_path_is_tolerated(self):
        blurb = summarize("x", api_base=self.url + "/chat/completions", model="ok")
        self.assertTrue(blurb)

    def test_http_error_raises(self):
        with self.assertRaises(SummaryError):
            summarize("x", api_base=self.url, model="boom-model")

    def test_bad_response_shape_raises(self):
        with self.assertRaises(SummaryError):
            summarize("x", api_base=self.url, model="bad-shape")

    def test_empty_base_raises(self):
        with self.assertRaises(SummaryError):
            summarize("x", api_base="", model="llama3.1")

    def test_unreachable_server_raises(self):
        with self.assertRaises(SummaryError):
            summarize("x", api_base="http://127.0.0.1:1/v1", model="m", timeout=2)


if __name__ == "__main__":
    unittest.main()
