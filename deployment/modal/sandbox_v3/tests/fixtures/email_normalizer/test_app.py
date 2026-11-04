from app import normalize_email


def test_normalize_email() -> None:
    assert normalize_email(" User@Example.COM ") == "user@example.com"
