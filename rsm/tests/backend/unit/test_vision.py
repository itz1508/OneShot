"""Unit tests for `rsm.vision` — the small Vision capability.

These tests exercise request construction, validation, failure handling,
output bounding, and the no-exec guarantee against a local HTTP stub.
They do NOT make any live NVIDIA call; live Vision inference is covered
separately when a real NVIDIA credential is available.
"""

from __future__ import annotations

import base64
import http.server
import json
import socketserver
import threading
import time
import unittest
from typing import Any, Dict

from rsm.vision import (
    ALLOWED_MIMES,
    HttpChatVisionProvider,
    NullVisionProvider,
    VisionError,
    VisionProvider,
    VisionResult,
    VisionUnavailable,
    observe_image,
)


# Deterministic 70-byte PNG (header + minimal IDAT + IEND).
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c62000100000005000120b60000000049454e44ae426082"
)
# Minimal JPEG magic.
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 20 + b"\xff\xd9"


class _Stub(http.server.BaseHTTPRequestHandler):
    captured: Dict[str, Any] = {}
    reply_body: bytes = b""
    reply_status: int = 200
    sleep_s: float = 0.0

    def log_message(self, *a, **k):  # pragma: no cover - silence stub
        pass

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n)
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"__raw__": raw[:200].decode("latin1", "replace")}
        _Stub.captured = {
            "path": self.path,
            "headers": {k: v for k, v in self.headers.items()},
            "body": parsed,
        }
        if _Stub.sleep_s:
            time.sleep(_Stub.sleep_s)
        self.send_response(_Stub.reply_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(_Stub.reply_body)))
        self.end_headers()
        try:
            self.wfile.write(_Stub.reply_body)
        except BrokenPipeError:  # pragma: no cover - timeout path
            pass


class _Server:
    def __init__(self):
        self.httpd = socketserver.TCPServer(("127.0.0.1", 0), _Stub)
        self.port = self.httpd.server_address[1]
        self.t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.t.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def set_reply(self, obj, status=200, sleep_s=0.0):
        _Stub.reply_body = json.dumps(obj).encode()
        _Stub.reply_status = status
        _Stub.sleep_s = sleep_s

    def set_raw(self, raw: bytes, status=200):
        _Stub.reply_body = raw
        _Stub.reply_status = status
        _Stub.sleep_s = 0.0

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


SRV: _Server | None = None


class VisionCapabilityTests(unittest.TestCase):
    """Narrow Vision tests from the work order §9."""

    @classmethod
    def setUpClass(cls):
        global SRV
        SRV = _Server()

    @classmethod
    def tearDownClass(cls):
        SRV.stop()

    # ---- Protocol / Null default ----------------------------------

    def test_provider_protocol_structural(self):
        """Both built-in providers satisfy the VisionProvider Protocol."""
        self.assertIsInstance(NullVisionProvider(), VisionProvider)
        p = HttpChatVisionProvider(
            base_url=SRV.base_url, model="nvidia/x"
        )
        self.assertIsInstance(p, VisionProvider)

    def test_null_provider_raises_unavailable(self):
        n = NullVisionProvider()
        with self.assertRaises(VisionUnavailable):
            n.describe(
                image_bytes=PNG_BYTES, mime="image/png", prompt="p"
            )

    # ---- Construction validation ----------------------------------

    def test_construction_rejects_bad_base_url(self):
        with self.assertRaises(VisionError):
            HttpChatVisionProvider(
                base_url="file:///etc/passwd", model="m"
            )

    def test_construction_rejects_empty_model(self):
        with self.assertRaises(VisionError):
            HttpChatVisionProvider(
                base_url=SRV.base_url, model=""
            )

    def test_construction_rejects_bad_caps(self):
        with self.assertRaises(VisionError):
            HttpChatVisionProvider(
                base_url=SRV.base_url, model="m", max_image_bytes=0
            )
        with self.assertRaises(VisionError):
            HttpChatVisionProvider(
                base_url=SRV.base_url, model="m", max_output_chars=0
            )

    # ---- Describe-time input validation ---------------------------

    def _p(self, **kw):
        return HttpChatVisionProvider(
            base_url=SRV.base_url, model="nvidia/test", **kw
        )

    def test_bytes_required(self):
        with self.assertRaises(VisionError) as cm:
            self._p().describe(image_bytes="not-bytes", mime="image/png",
                               prompt="p")
        self.assertEqual(cm.exception.kind, "input")

    def test_mime_restricted(self):
        with self.assertRaises(VisionError) as cm:
            self._p().describe(image_bytes=PNG_BYTES, mime="image/webp",
                               prompt="p")
        self.assertEqual(cm.exception.kind, "input")

    def test_empty_rejected(self):
        with self.assertRaises(VisionError) as cm:
            self._p().describe(image_bytes=b"", mime="image/png", prompt="p")
        self.assertEqual(cm.exception.kind, "input")

    def test_oversize_rejected(self):
        p = self._p(max_image_bytes=5)
        with self.assertRaises(VisionError) as cm:
            p.describe(image_bytes=b"x" * 10, mime="image/png", prompt="p")
        self.assertEqual(cm.exception.kind, "limit")

    def test_empty_prompt_rejected(self):
        with self.assertRaises(VisionError) as cm:
            self._p().describe(
                image_bytes=PNG_BYTES, mime="image/png", prompt="   "
            )
        self.assertEqual(cm.exception.kind, "input")

    def test_bad_max_tokens(self):
        with self.assertRaises(VisionError):
            self._p().describe(
                image_bytes=PNG_BYTES, mime="image/png",
                prompt="p", max_tokens=0,
            )

    def test_bad_timeout(self):
        with self.assertRaises(VisionError):
            self._p().describe(
                image_bytes=PNG_BYTES, mime="image/png",
                prompt="p", timeout_s=0,
            )

    # ---- Request shape (byte-identical round-trip) ----------------

    def test_request_shape_is_openai_compatible(self):
        SRV.set_reply({
            "id": "c", "object": "chat.completion", "created": 0,
            "model": "nvidia/test",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "hello"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        })
        p = HttpChatVisionProvider(
            base_url=SRV.base_url, model="nvidia/test", api_key="nvapi-fake",
        )
        r = p.describe(
            image_bytes=PNG_BYTES, mime="image/png",
            prompt="Describe.", max_tokens=16, timeout_s=5.0,
        )
        self.assertIsInstance(r, VisionResult)
        self.assertEqual(r.text, "hello")
        self.assertEqual(r.model, "nvidia/test")
        self.assertEqual(r.input_tokens, 3)
        self.assertEqual(r.output_tokens, 1)
        self.assertEqual(r.finish_reason, "stop")
        self.assertFalse(r.truncated)

        cap = _Stub.captured
        self.assertEqual(cap["path"], "/v1/chat/completions")
        self.assertEqual(cap["headers"]["Content-Type"], "application/json")
        self.assertEqual(cap["headers"]["Authorization"], "Bearer nvapi-fake")
        body = cap["body"]
        self.assertEqual(body["model"], "nvidia/test")
        self.assertFalse(body["stream"])
        self.assertEqual(body["max_tokens"], 16)
        self.assertAlmostEqual(body["temperature"], 0.0)
        content = body["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "image_url")
        url = content[0]["image_url"]["url"]
        self.assertTrue(url.startswith("data:image/png;base64,"))
        self.assertEqual(
            base64.b64decode(url.split(",", 1)[1]), PNG_BYTES
        )
        self.assertEqual(content[1], {"type": "text", "text": "Describe."})

    def test_api_key_omitted_from_request_when_not_set(self):
        SRV.set_reply({
            "choices": [{
                "index": 0,
                "message": {"content": "ok"},
                "finish_reason": "stop",
            }],
        })
        p = HttpChatVisionProvider(base_url=SRV.base_url, model="m")
        p.describe(image_bytes=PNG_BYTES, mime="image/png", prompt="p")
        self.assertNotIn("Authorization", _Stub.captured["headers"])

    def test_jpeg_also_accepted(self):
        SRV.set_reply({
            "choices": [{
                "index": 0, "message": {"content": "jpeg ok"},
                "finish_reason": "stop",
            }],
        })
        r = self._p().describe(
            image_bytes=JPEG_BYTES, mime="image/jpeg", prompt="p"
        )
        self.assertEqual(r.text, "jpeg ok")
        url = _Stub.captured["body"]["messages"][0]["content"][0][
            "image_url"]["url"]
        self.assertTrue(url.startswith("data:image/jpeg;base64,"))

    # ---- Failure paths -------------------------------------------

    def test_http_error_surfaced(self):
        SRV.set_raw(b'{"status":401,"title":"Unauthorized"}', status=401)
        with self.assertRaises(VisionError) as cm:
            self._p().describe(
                image_bytes=PNG_BYTES, mime="image/png", prompt="p"
            )
        self.assertEqual(cm.exception.kind, "http_401")
        self.assertIn("Unauthorized", cm.exception.detail)

    def test_malformed_json(self):
        SRV.set_raw(b"not json at all", status=200)
        with self.assertRaises(VisionError) as cm:
            self._p().describe(
                image_bytes=PNG_BYTES, mime="image/png", prompt="p"
            )
        self.assertEqual(cm.exception.kind, "malformed_json")

    def test_malformed_response_shape(self):
        SRV.set_reply({"choices": []})
        with self.assertRaises(VisionError) as cm:
            self._p().describe(
                image_bytes=PNG_BYTES, mime="image/png", prompt="p"
            )
        self.assertEqual(cm.exception.kind, "malformed_response")

    def test_timeout(self):
        SRV.set_reply(
            {"choices": [{"index": 0, "message": {"content": "x"}}]},
            sleep_s=0.5,
        )
        with self.assertRaises(VisionError) as cm:
            self._p().describe(
                image_bytes=PNG_BYTES, mime="image/png", prompt="p",
                timeout_s=0.1,
            )
        self.assertIn(cm.exception.kind, {"network", "transport"})

    # ---- Bounded output + inert text -----------------------------

    def test_output_truncation(self):
        big = "x" * (1024 * 64)
        SRV.set_reply({
            "choices": [{
                "index": 0, "message": {"content": big},
                "finish_reason": "stop",
            }],
        })
        p = self._p(max_output_chars=100)
        r = p.describe(
            image_bytes=PNG_BYTES, mime="image/png", prompt="p"
        )
        self.assertEqual(len(r.text), 100)
        self.assertTrue(r.truncated)

    def test_model_output_is_inert_string(self):
        trick = "__import__('os').system('echo pwned')"
        SRV.set_reply({
            "choices": [{
                "index": 0, "message": {"content": trick},
                "finish_reason": "stop",
            }],
        })
        r = self._p().describe(
            image_bytes=PNG_BYTES, mime="image/png", prompt="p"
        )
        self.assertEqual(r.text, trick)
        self.assertIsInstance(r.text, str)
        # The provider must not have *called* anything with that string.
        # If it had been eval'd, the "pwned" marker would have been emitted
        # by the shell — but the only way to confirm is structural.

    # ---- Façade (observe_image) ---------------------------------

    def test_observe_image_facade(self):
        SRV.set_reply({
            "choices": [{
                "index": 0, "message": {"content": "FAÇADE"},
                "finish_reason": "stop",
            }],
        })
        r = observe_image(
            self._p(),
            image_bytes=PNG_BYTES, mime="image/png", prompt="p",
        )
        self.assertEqual(r.text, "FAÇADE")


class DependencyBoundaryTests(unittest.TestCase):
    """`rsm.vision` must not import any banned / framework library."""

    def test_module_imports_have_no_forbidden_package(self):
        """Walk AST imports — comments / docstrings may legitimately mention
        "OpenAI-compatible" (an API shape), so the test must check actual
        IMPORTS, not words in source text. The project-level
        `check_forbidden_deps.py` gate is case-sensitive and word-bounded,
        so it already allows the comment; this test is stricter.
        """
        import ast
        import inspect
        import rsm.vision.model as m1
        import rsm.vision.provider as m2
        forbidden = {
            "openai", "anthropic", "langchain", "langgraph",
            "llama_index", "crewai", "autogen", "pydantic_ai",
            "strands", "mcp", "boto3", "requests", "httpx",
        }
        for mod in (m1, m2):
            tree = ast.parse(inspect.getsource(mod))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported.add(node.module.split(".")[0])
            bad = imported & forbidden
            self.assertFalse(bad, msg=f"{mod.__name__} imports {bad!r}")

    def test_allowed_mimes_matches_nim_doc(self):
        # NIM for VLMs 1.3.1 documents only JPG/JPEG/PNG. WebP is NOT listed.
        self.assertEqual(ALLOWED_MIMES, frozenset({"image/jpeg", "image/png"}))


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
