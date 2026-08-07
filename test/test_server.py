import hashlib
import http.client
import json
import pathlib
import socket
import sys
import threading
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import server  # noqa: E402


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server("127.0.0.1", 0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        deadline = time.monotonic() + 2
        while True:
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.1):
                    break
            except ConnectionRefusedError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        return response.status, response.headers, json.loads(raw)

    def post(self, path, document):
        body = json.dumps(document, separators=(",", ":")).encode()
        return self.request(
            "POST", path, body, {"Content-Type": "application/json", "Content-Length": str(len(body))}
        )

    def test_health_is_deterministic(self):
        first = self.request("GET", "/health")
        second = self.request("GET", "/health")
        self.assertEqual(first[0], 200)
        self.assertEqual(first[2], second[2])
        self.assertEqual(first[2]["state"], "ephemeral")

    def test_sha256(self):
        status, _headers, result = self.post("/v1/sha256", {"text": "cedar fog"})
        self.assertEqual(status, 200)
        self.assertEqual(result["digestHex"], hashlib.sha256(b"cedar fog").hexdigest())
        self.assertEqual(result["inputBytes"], 9)

    def test_pbkdf2_has_provider_fixed_work(self):
        status, _headers, result = self.post("/v1/pbkdf2", {"text": "cedar fog"})
        expected = hashlib.pbkdf2_hmac(
            "sha256", b"cedar fog", server.PBKDF2_SALT,
            server.PBKDF2_ITERATIONS, server.PBKDF2_OUTPUT_BYTES,
        ).hex()
        self.assertEqual(status, 200)
        self.assertEqual(result["digestHex"], expected)
        self.assertEqual(result["iterations"], 120_000)
        self.assertEqual(result["outputBytes"], 32)

    def test_rejects_extra_fields(self):
        status, _headers, result = self.post("/v1/sha256", {"text": "x", "url": "https://example.test"})
        self.assertEqual(status, 400)
        self.assertEqual(result["error"], "invalid-fields")

    def test_rejects_duplicate_fields(self):
        body = b'{"text":"first","text":"second"}'
        status, _headers, result = self.request(
            "POST", "/v1/sha256", body,
            {"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        self.assertEqual(status, 400)
        self.assertEqual(result["error"], "duplicate-field")

    def test_rejects_oversized_text(self):
        status, _headers, result = self.post("/v1/sha256", {"text": "x" * 4097})
        self.assertEqual(status, 413)
        self.assertEqual(result["error"], "text-too-large")

    def test_rejects_oversized_body_before_reading_it(self):
        body = b"x" * (server.MAX_BODY_BYTES + 1)
        status, _headers, result = self.request(
            "POST", "/v1/sha256", body,
            {"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        self.assertEqual(status, 413)
        self.assertEqual(result["error"], "body-too-large")

    def test_rejects_wrong_media_type(self):
        status, _headers, result = self.request(
            "POST", "/v1/sha256", b'{"text":"x"}', {"Content-Type": "text/plain"}
        )
        self.assertEqual(status, 415)
        self.assertEqual(result["error"], "unsupported-media-type")

    def test_rejects_unknown_operation(self):
        status, _headers, result = self.post("/v1/fetch", {"text": "https://example.test"})
        self.assertEqual(status, 404)
        self.assertEqual(result["error"], "not-found")

    def test_rejects_other_methods(self):
        status, _headers, result = self.request("PUT", "/v1/sha256")
        self.assertEqual(status, 405)
        self.assertEqual(result["error"], "method-not-allowed")


if __name__ == "__main__":
    unittest.main()
