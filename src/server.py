"""Bounded deterministic CPU operations for a private Hugging Face Space."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Any


CONTRACT = "hugging-face-cpu-compute/v1"
HOST = "0.0.0.0"
DEFAULT_PORT = 7860
MAX_BODY_BYTES = 6144
MAX_TEXT_BYTES = 4096
PBKDF2_ITERATIONS = 120_000
PBKDF2_OUTPUT_BYTES = 32
PBKDF2_SALT = b"harmonious-union/hugging-face-cpu-compute/v1"
MAX_CONCURRENT_REQUESTS = 8
SOCKET_TIMEOUT_SECONDS = 10


class RequestError(Exception):
    """A deterministic client refusal."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RequestError(400, "duplicate-field", "JSON object contains a duplicate field")
        result[key] = value
    return result


def parse_text_request(body: bytes) -> bytes:
    try:
        document = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object)
    except RequestError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RequestError(400, "invalid-json", "body must be one UTF-8 JSON object") from error

    if not isinstance(document, dict) or set(document) != {"text"}:
        raise RequestError(400, "invalid-fields", "body must contain exactly one text field")
    if not isinstance(document["text"], str):
        raise RequestError(400, "invalid-text", "text must be a JSON string")
    try:
        encoded = document["text"].encode("utf-8")
    except UnicodeEncodeError as error:
        raise RequestError(400, "invalid-text", "text must encode as UTF-8") from error
    if len(encoded) > MAX_TEXT_BYTES:
        raise RequestError(413, "text-too-large", f"text exceeds {MAX_TEXT_BYTES} UTF-8 bytes")
    return encoded


def compute(path: str, text: bytes) -> dict[str, Any]:
    if path == "/v1/sha256":
        return {
            "algorithm": "sha256",
            "contract": CONTRACT,
            "digestHex": hashlib.sha256(text).hexdigest(),
            "inputBytes": len(text),
        }
    if path == "/v1/pbkdf2":
        output = hashlib.pbkdf2_hmac(
            "sha256", text, PBKDF2_SALT, PBKDF2_ITERATIONS, PBKDF2_OUTPUT_BYTES
        )
        return {
            "algorithm": "pbkdf2-hmac-sha256",
            "contract": CONTRACT,
            "digestHex": output.hex(),
            "inputBytes": len(text),
            "iterations": PBKDF2_ITERATIONS,
            "outputBytes": PBKDF2_OUTPUT_BYTES,
            "saltDomain": PBKDF2_SALT.decode("ascii"),
        }
    raise RequestError(404, "not-found", "operation does not exist")


class BoundedThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], handler: type[BaseHTTPRequestHandler]):
        self._slots = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
        super().__init__(server_address, handler)

    def process_request(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        self._slots.acquire()
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class ComputeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "UnionBoundedCompute/1"
    sys_version = ""

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(SOCKET_TIMEOUT_SECONDS)

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, status: int, document: dict[str, Any]) -> None:
        body = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    def _refuse(self, error: RequestError) -> None:
        self._json(error.status, {
            "contract": CONTRACT,
            "error": error.code,
            "message": error.message,
        })

    def _method_not_allowed(self) -> None:
        self._json(405, {
            "contract": CONTRACT,
            "error": "method-not-allowed",
            "message": "use GET /health or POST to one v1 operation",
        })

    def do_GET(self) -> None:
        if self.path != "/health":
            self._refuse(RequestError(404, "not-found", "operation does not exist"))
            return
        self._json(200, {
            "contract": CONTRACT,
            "status": "ready",
            "state": "ephemeral",
        })

    def do_POST(self) -> None:
        try:
            if self.path not in {"/v1/sha256", "/v1/pbkdf2"}:
                raise RequestError(404, "not-found", "operation does not exist")
            if self.headers.get("Transfer-Encoding") is not None:
                raise RequestError(400, "unsupported-transfer", "transfer encoding is not accepted")
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                raise RequestError(415, "unsupported-media-type", "Content-Type must be application/json")
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise RequestError(411, "length-required", "Content-Length is required")
            try:
                length = int(raw_length, 10)
            except ValueError as error:
                raise RequestError(400, "invalid-length", "Content-Length must be an integer") from error
            if length < 0:
                raise RequestError(400, "invalid-length", "Content-Length must not be negative")
            if length > MAX_BODY_BYTES:
                raise RequestError(413, "body-too-large", f"body exceeds {MAX_BODY_BYTES} bytes")
            body = self.rfile.read(length)
            if len(body) != length:
                raise RequestError(400, "incomplete-body", "body ended before Content-Length")
            self._json(200, compute(self.path, parse_text_request(body)))
        except RequestError as error:
            self._refuse(error)

    do_HEAD = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_OPTIONS = _method_not_allowed


def make_server(host: str = HOST, port: int = DEFAULT_PORT) -> BoundedThreadingHTTPServer:
    return BoundedThreadingHTTPServer((host, port), ComputeHandler)


def main() -> None:
    raw_port = os.environ.get("PORT", str(DEFAULT_PORT))
    try:
        port = int(raw_port, 10)
    except ValueError as error:
        raise SystemExit("PORT must be an integer") from error
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be between 1 and 65535")
    make_server(port=port).serve_forever()


if __name__ == "__main__":
    main()
