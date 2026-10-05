"""Reader + Vision wiring tests — the smallest coupling between
`rsm.reader.read_bucket` and the pre-existing `rsm.vision` capability.

Fakes a `VisionProvider` in-process so no NVIDIA credential is required.
The real `HttpChatVisionProvider` is covered independently in
`tests/unit/test_vision.py` (24 tests).

What this suite freezes:

  1. image File + successful provider → ReaderEvent(method=VISION, vision=True)
  2. VisionResult.text is correctly reflected in observed_bytes / observed_chars
  3. ReaderTrace.coverage records the Vision observation
  4. Multiple image Files invoke the provider independently
  5. One Vision failure does NOT stop subsequent Files (isolation)
  6. VisionUnavailable → FILE_FAILED(reason="vision_unavailable")
  7. Provider injection works without global state (two provider instances
     in two calls)
  8. No provider wired → existing FILE_FAILED(reason="vision_unavailable")
     is unchanged
  9. Non-image Files are unaffected when a provider is passed
 10. Reader event counts stay correct (one event per discovered File)
 11. Unsupported image mime (.gif / .bmp / .webp) → vision_unsupported_mime
 12. image_bytes supplied as a dict works; supplied as a callable works
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from rsm.extraction.folder import extract_folder
from rsm.extraction.text import extract_text
from rsm.reader import (
    FileRef,
    FileType,
    ReaderEventKind,
    ReaderMethod,
    ReaderStatus,
    read_bucket,
)
from rsm.vision import (
    NullVisionProvider,
    VisionError,
    VisionProvider,
    VisionResult,
)


# ---- Fakes -----------------------------------------------------------------


class _FakeVisionProvider:
    """Deterministic in-process VisionProvider.

    Satisfies the runtime-checkable `VisionProvider` Protocol — no network,
    no credentials. Records every call so tests can assert independence.
    """

    name = "fake"

    def __init__(self, text: str = "an image of a cat", *, fail: bool = False) -> None:
        self._text = text
        self._fail = fail
        self.calls: List[dict] = []

    def describe(
        self,
        *,
        image_bytes: bytes,
        mime: str,
        prompt: str,
        max_tokens: int = 1024,
        timeout_s: float = 60.0,
    ) -> VisionResult:
        self.calls.append(
            {
                "mime": mime,
                "n_bytes": len(image_bytes),
                "prompt": prompt,
                "max_tokens": max_tokens,
                "timeout_s": timeout_s,
            }
        )
        if self._fail:
            raise VisionError("network", "fake transport failure")
        return VisionResult(text=self._text, model="fake-model")


class _PerFileFakeProvider:
    """Fails for a specific file name; succeeds for every other call.

    Used to prove per-File failure isolation.
    """

    name = "fake-per-file"

    def __init__(self, failing_name: str) -> None:
        self._failing_name = failing_name
        self.calls: List[str] = []

    def describe(self, *, image_bytes, mime, prompt, max_tokens=1024, timeout_s=60.0):
        # The test infrastructure knows which bytes map to which file (see
        # `_image_root`), so we route by the known bytes signature.
        self.calls.append(mime)
        if image_bytes.startswith(b"FAILME"):
            raise VisionError("http_500", "simulated server error")
        return VisionResult(text="ok", model="fake-model")


# ---- Fixtures --------------------------------------------------------------


def _image_root(tmp_path: Path, images: dict[str, bytes]) -> Path:
    """Materialise a folder containing supported + opaque children.

    The folder also has one `.txt` child so a successful observation
    coexists with the image failures in the same ReaderTrace.
    """
    root = tmp_path / "r"
    root.mkdir()
    for name, data in images.items():
        (root / name).write_bytes(data)
    (root / "notes.txt").write_text("caption text")
    return root


def _bucket(root: Path):
    return extract_folder(root).parent


def _bytes_by_name(bucket, name_to_bytes: dict[str, bytes]) -> dict[str, bytes]:
    """Build a file_id → bytes map by scanning the Bucket's manifest."""
    from rsm.reader import scan_bucket

    sc = scan_bucket(bucket)
    out: dict[str, bytes] = {}
    for f in sc.files:
        if f.name in name_to_bytes:
            out[f.file_id] = name_to_bytes[f.name]
    return out


# ---- Tests -----------------------------------------------------------------


def test_1_image_with_successful_provider_produces_vision_event(tmp_path: Path):
    data = {"cat.png": b"\x89PNG\r\n\x1a\n" + b"x" * 32}
    root = _image_root(tmp_path, data)
    b = _bucket(root)
    provider = _FakeVisionProvider(text="a cat sitting on a mat")

    r = read_bucket(
        b,
        vision_provider=provider,
        image_bytes=_bytes_by_name(b, data),
    )

    # Exactly one event per discovered File (manifest has 2: cat.png + notes.txt).
    assert len(r.events) == 2
    assert len(r.trace.coverage) == 2

    img_events = [e for e in r.events if e.file_id.endswith(":f1") and "cat.png" in {
        c.file_id for c in r.trace.coverage if c.index == e.index
    } or True]
    # Find the Vision event by method.
    vision_events = [e for e in r.events if e.method == ReaderMethod.VISION]
    assert len(vision_events) == 1
    ev = vision_events[0]
    assert ev.kind == ReaderEventKind.FILE_OBSERVED
    assert ev.vision is True
    assert ev.reason is None
    # Trace counts.
    assert r.trace.failed_count == 0
    assert r.trace.observed_count == 2
    assert r.trace.complete is True
    # Exactly one provider call.
    assert len(provider.calls) == 1
    assert provider.calls[0]["mime"] == "image/png"


def test_2_vision_text_length_is_reflected_in_observed_counters(tmp_path: Path):
    txt = "x" * 97  # odd length, ASCII — bytes == chars
    data = {"photo.jpg": b"\xff\xd8\xff\xe0" + b"j" * 20 + b"\xff\xd9"}
    root = _image_root(tmp_path, data)
    b = _bucket(root)
    provider = _FakeVisionProvider(text=txt)

    r = read_bucket(b, vision_provider=provider, image_bytes=_bytes_by_name(b, data))

    vision_ev = next(e for e in r.events if e.method == ReaderMethod.VISION)
    assert vision_ev.observed_chars == 97
    assert vision_ev.observed_bytes == 97
    assert provider.calls[0]["mime"] == "image/jpeg"


def test_3_reader_trace_records_the_vision_observation(tmp_path: Path):
    data = {"icon.png": b"\x89PNG\r\n\x1a\n" + b"i" * 16}
    root = _image_root(tmp_path, data)
    b = _bucket(root)
    provider = _FakeVisionProvider(text="icon")

    r = read_bucket(b, vision_provider=provider, image_bytes=_bytes_by_name(b, data))

    vision_cov = [c for c in r.trace.coverage if c.method == ReaderMethod.VISION]
    assert len(vision_cov) == 1
    cov = vision_cov[0]
    assert cov.vision is True
    assert cov.status == ReaderStatus.OBSERVED
    assert cov.observed_chars == len("icon")


def test_4_multiple_image_files_invoke_provider_independently(tmp_path: Path):
    data = {
        "a.png": b"\x89PNG\r\n\x1a\n" + b"a" * 16,
        "b.jpg": b"\xff\xd8\xff\xe0" + b"b" * 20 + b"\xff\xd9",
        "c.jpeg": b"\xff\xd8\xff\xe0" + b"c" * 20 + b"\xff\xd9",
    }
    root = _image_root(tmp_path, data)
    b = _bucket(root)
    provider = _FakeVisionProvider(text="pic")

    r = read_bucket(b, vision_provider=provider, image_bytes=_bytes_by_name(b, data))

    vision_evs = [e for e in r.events if e.method == ReaderMethod.VISION]
    assert len(vision_evs) == 3
    assert len(provider.calls) == 3
    # Each call carried the right MIME.
    mimes = sorted(c["mime"] for c in provider.calls)
    assert mimes == ["image/jpeg", "image/jpeg", "image/png"]


def test_5_one_vision_failure_does_not_stop_subsequent_files(tmp_path: Path):
    data = {
        "good1.png": b"\x89PNG\r\n\x1a\n" + b"g" * 16,
        "bad.png": b"FAILMEplease" + b"x" * 16,  # routed to failure by _PerFileFakeProvider
        "good2.jpg": b"\xff\xd8\xff\xe0" + b"g" * 20 + b"\xff\xd9",
    }
    root = _image_root(tmp_path, data)
    b = _bucket(root)
    provider = _PerFileFakeProvider(failing_name="bad.png")

    r = read_bucket(b, vision_provider=provider, image_bytes=_bytes_by_name(b, data))

    # 3 images + notes.txt = 4 events, one per discovered File (isolation).
    assert len(r.events) == 4
    assert len(r.trace.coverage) == 4
    # Exactly one failure, and it is a Vision failure.
    assert r.trace.failed_count == 1
    reasons = {f.reason for f in r.trace.failures}
    assert reasons == {"vision_http_500"}
    # Two successful Vision events + one TEXT event for notes.txt.
    v_ok = [e for e in r.events if e.method == ReaderMethod.VISION and e.kind == ReaderEventKind.FILE_OBSERVED]
    assert len(v_ok) == 2
    text_ev = [e for e in r.events if e.method == ReaderMethod.TEXT]
    assert len(text_ev) == 1  # notes.txt
    # Reader kept going — trace is complete.
    assert r.trace.complete is True


def test_6_vision_unavailable_produces_vision_unavailable(tmp_path: Path):
    data = {"cat.png": b"\x89PNG\r\n\x1a\n" + b"x" * 16}
    root = _image_root(tmp_path, data)
    b = _bucket(root)
    null_provider = NullVisionProvider()

    r = read_bucket(
        b,
        vision_provider=null_provider,
        image_bytes=_bytes_by_name(b, data),
    )

    reasons = {f.reason for f in r.trace.failures}
    assert "vision_unavailable" in reasons
    assert all(e.method != ReaderMethod.VISION for e in r.events)


def test_7_provider_injection_has_no_global_state(tmp_path: Path):
    data = {"cat.png": b"\x89PNG\r\n\x1a\n" + b"x" * 16}
    root = _image_root(tmp_path, data)
    b = _bucket(root)

    p1 = _FakeVisionProvider(text="first")
    p2 = _FakeVisionProvider(text="second")

    r1 = read_bucket(b, vision_provider=p1, image_bytes=_bytes_by_name(b, data))
    r2 = read_bucket(b, vision_provider=p2, image_bytes=_bytes_by_name(b, data))

    ev1 = next(e for e in r1.events if e.method == ReaderMethod.VISION)
    ev2 = next(e for e in r2.events if e.method == ReaderMethod.VISION)
    assert ev1.observed_chars == len("first")
    assert ev2.observed_chars == len("second")
    # Each provider only saw its own call.
    assert len(p1.calls) == 1
    assert len(p2.calls) == 1


def test_8_no_provider_wired_preserves_existing_vision_unavailable(tmp_path: Path):
    data = {"cat.png": b"\x89PNG\r\n\x1a\n" + b"x" * 16}
    root = _image_root(tmp_path, data)
    b = _bucket(root)

    r = read_bucket(b)  # no provider, no bytes — identical to pre-wiring behaviour.

    reasons = {f.reason for f in r.trace.failures}
    assert reasons == {"vision_unavailable"}
    assert r.trace.failed_count == 1
    assert all(e.method != ReaderMethod.VISION for e in r.events)


def test_9_text_file_behaviour_unchanged_when_provider_passed(tmp_path: Path):
    # Simple-source text bucket + a provider should NOT reach Vision at all;
    # the text file is observed via method=TEXT exactly as before.
    bucket = extract_text("hello world", source_uri="demo.txt")
    provider = _FakeVisionProvider(text="should-not-be-called")

    r = read_bucket(bucket, vision_provider=provider, image_bytes={})

    assert len(r.events) == 1
    ev = r.events[0]
    assert ev.method == ReaderMethod.TEXT
    assert ev.vision is False
    assert len(provider.calls) == 0


def test_10_reader_event_counts_remain_correct(tmp_path: Path):
    data = {
        "a.png": b"\x89PNG\r\n\x1a\n" + b"a" * 16,
        "b.jpg": b"\xff\xd8\xff\xe0" + b"b" * 20 + b"\xff\xd9",
    }
    root = _image_root(tmp_path, data)
    b = _bucket(root)
    provider = _FakeVisionProvider(text="pic")

    r = read_bucket(b, vision_provider=provider, image_bytes=_bytes_by_name(b, data))

    # len(events) == len(coverage) == discovered — isolation invariant.
    assert len(r.events) == len(r.trace.coverage) == r.trace.discovered == 3
    assert r.trace.complete is True


def test_11_unsupported_image_mime_fails_per_file(tmp_path: Path):
    # .webp / .gif / .bmp are OPAQUE in SCAN but NIM VLM only accepts jpg/png.
    data = {
        "ok.png": b"\x89PNG\r\n\x1a\n" + b"o" * 16,
        "weird.webp": b"RIFF????WEBP" + b"w" * 16,
    }
    root = _image_root(tmp_path, data)
    b = _bucket(root)
    provider = _FakeVisionProvider(text="pic")

    r = read_bucket(b, vision_provider=provider, image_bytes=_bytes_by_name(b, data))

    reasons = {f.reason for f in r.trace.failures}
    assert "vision_unsupported_mime" in reasons
    # The .png still succeeded via Vision — isolation holds.
    v_ok = [e for e in r.events if e.method == ReaderMethod.VISION and e.kind == ReaderEventKind.FILE_OBSERVED]
    assert len(v_ok) == 1
    # The provider was only called for the png.
    assert len(provider.calls) == 1
    assert provider.calls[0]["mime"] == "image/png"


def test_12_image_bytes_accepts_dict_or_callable(tmp_path: Path):
    data = {"cat.png": b"\x89PNG\r\n\x1a\n" + b"x" * 16}
    root = _image_root(tmp_path, data)
    b = _bucket(root)

    # ---- dict shape (already covered everywhere; sanity line here) ----
    p1 = _FakeVisionProvider(text="dict")
    r1 = read_bucket(b, vision_provider=p1, image_bytes=_bytes_by_name(b, data))
    assert any(e.method == ReaderMethod.VISION for e in r1.events)

    # ---- callable shape ----
    expected_png = data["cat.png"]

    def lookup(f: FileRef) -> Optional[bytes]:
        if f.file_type == FileType.IMAGE and f.name == "cat.png":
            return expected_png
        return None

    p2 = _FakeVisionProvider(text="callable")
    r2 = read_bucket(b, vision_provider=p2, image_bytes=lookup)
    v2 = next(e for e in r2.events if e.method == ReaderMethod.VISION)
    assert v2.observed_chars == len("callable")
    assert len(p2.calls) == 1


# ---- Boundary / Protocol sanity -------------------------------------------


def test_fake_provider_satisfies_vision_provider_protocol():
    # Must satisfy the runtime-checkable VisionProvider Protocol; otherwise
    # Reader can't trust `isinstance` checks downstream.
    assert isinstance(_FakeVisionProvider(), VisionProvider)
    assert isinstance(_PerFileFakeProvider("x"), VisionProvider)


def test_provider_wired_but_no_bytes_available_fails_vision_unavailable(tmp_path: Path):
    # The provider is wired but the caller didn't supply bytes for this file.
    # Reader must still fail per-File with vision_unavailable, not try to
    # fabricate bytes.
    data = {"cat.png": b"\x89PNG\r\n\x1a\n" + b"x" * 16}
    root = _image_root(tmp_path, data)
    b = _bucket(root)
    provider = _FakeVisionProvider()

    r = read_bucket(b, vision_provider=provider, image_bytes={})  # empty map

    reasons = {f.reason for f in r.trace.failures}
    assert "vision_unavailable" in reasons
    assert len(provider.calls) == 0
