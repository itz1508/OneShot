import pytest
from test_contracts import make_request

from modal_build_sandbox.applicator import apply_changes, parse_patch, prepare_changes
from modal_build_sandbox.snapshot import secure_read


def _patch(req):
    import zipfile

    with zipfile.ZipFile(req.candidate_bundle_ref) as z:
        return z.read("candidate.patch")


def test_complete_authorized_patch(tmp_path):
    req = make_request(tmp_path)
    changes = prepare_changes(tmp_path / "source", _patch(req), req.authorized_paths, req.expected_preimages)
    apply_changes(tmp_path / "source", changes)
    assert b"strip().lower()" in secure_read(tmp_path / "source", "app.py")


def test_preflight_rejects_untrusted_path(tmp_path):
    req = make_request(tmp_path)
    patch = _patch(req).replace(b"a/app.py", b"a/secret.py").replace(b"b/app.py", b"b/secret.py")
    with pytest.raises(ValueError, match="unauthorized"):
        prepare_changes(tmp_path / "source", patch, req.authorized_paths, req.expected_preimages)


def test_wrong_preimage_rejects_before_effect(tmp_path):
    req = make_request(tmp_path)
    source = tmp_path / "source" / "app.py"
    source.write_text("changed\n")
    with pytest.raises(ValueError, match="preimage"):
        prepare_changes(tmp_path / "source", _patch(req), req.authorized_paths, req.expected_preimages)
    assert source.read_text() == "changed\n"


def test_reject_malformed_or_binary_patch():
    for data in (b"GIT binary patch\n", b"diff --git a/app.py b/other.py\n", b""):
        with pytest.raises(ValueError):
            parse_patch(data)
