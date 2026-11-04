import io
import tarfile

import pytest

from modal_build_sandbox.snapshot import archive_directory, extract_verified_tar, scan_tree, sha256_file, tree_digest


def _tar(tmp_path, entries):
    path = tmp_path / "malicious.tar"
    with tarfile.open(path, "w") as out:
        for name, kind, data in entries:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.size = len(data)
            info.mode = 0o644
            out.addfile(info, io.BytesIO(data) if info.isfile() else None)
    return path


def test_archive_roundtrip(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("print(123)\n")
    tar = tmp_path / "src.tar"
    archive_id, tree_id = archive_directory(src, tar)
    dst = tmp_path / "dst"
    observed = extract_verified_tar(tar, dst, archive_digest=archive_id, expected_tree_digest=tree_id)
    assert tree_digest(observed) == tree_id
    assert (dst / "app.py").read_text() == "print(123)\n"


@pytest.mark.parametrize("path", ["../bad", "/etc/passwd", "a/../../bad", "C:/bad", "a\\b"])
def test_reject_tar_escape(tmp_path, path):
    tar = _tar(tmp_path, [(path, tarfile.REGTYPE, b"unsafe")])
    with pytest.raises(ValueError):
        extract_verified_tar(tar, tmp_path / "dst", archive_digest=sha256_file(tar), expected_tree_digest="0" * 64)


def test_reject_tar_symlink(tmp_path):
    tar = _tar(tmp_path, [("link", tarfile.SYMTYPE, b"")])
    with pytest.raises(ValueError, match="special"):
        extract_verified_tar(tar, tmp_path / "dst", archive_digest=sha256_file(tar), expected_tree_digest="0" * 64)


def test_reject_duplicate_case_alias(tmp_path):
    tar = _tar(tmp_path, [("app.py", tarfile.REGTYPE, b"a"), ("APP.py", tarfile.REGTYPE, b"b")])
    with pytest.raises(ValueError, match="duplicate"):
        extract_verified_tar(tar, tmp_path / "dst", archive_digest=sha256_file(tar), expected_tree_digest="0" * 64)


def test_reject_extraction_byte_limit(tmp_path):
    tar = _tar(tmp_path, [("a.py", tarfile.REGTYPE, b"x" * 100)])
    with pytest.raises(ValueError, match="exceeds"):
        extract_verified_tar(
            tar,
            tmp_path / "dst",
            archive_digest=sha256_file(tar),
            expected_tree_digest="0" * 64,
            max_extracted_bytes=10,
        )


def test_reject_symlink_in_source(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "link").symlink_to("/etc/passwd")
    with pytest.raises(ValueError):
        scan_tree(src)
