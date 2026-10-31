#!/usr/bin/env python3
"""Independent oracle tests for text_metrics.

Values specified before implementation verification.
"""

import pytest
from text_metrics import count_text


class TestTextMetricsIndependentOracles:
    """These expected values are independent oracles, NOT derived from implementation output."""

    def test_unicode_string(self):
        # A + emoji + LF + B = 4 Unicode code points, 7 UTF-8 bytes, 2 words
        result = count_text("A\U0001f600\nB")
        assert result == {"characters": 4, "bytes": 7, "words": 2}

    def test_empty_string(self):
        result = count_text("")
        assert result == {"characters": 0, "bytes": 0, "words": 0}

    def test_simple_ascii(self):
        result = count_text("hello world")
        assert result == {"characters": 11, "bytes": 11, "words": 2}

    def test_multibyte_utf8(self):
        # "cafe" with accent = 4 code points, 5 UTF-8 bytes, 1 word
        result = count_text("caf\u00e9")
        assert result == {"characters": 4, "bytes": 5, "words": 1}

    def test_multiple_lines(self):
        result = count_text("line1\nline2\nline3")
        assert result["characters"] == 17  # 5*3 + 2 newlines
        assert result["bytes"] == 17
        assert result["words"] == 3

    def test_whitespace_only(self):
        result = count_text("   \t  \n ")
        assert result["words"] == 0

    def test_non_string_rejected(self):
        with pytest.raises(TypeError):
            count_text(123)
        with pytest.raises(TypeError):
            count_text(None)
        with pytest.raises(TypeError):
            count_text(b"bytes not allowed")
