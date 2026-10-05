"""Boundary config rejects absurd sizes."""
import pytest
from rsm.config.schema import RSMConfig, ConfigValidationError


def test_zero_max_source_bytes_rejected():
    with pytest.raises(ConfigValidationError):
        RSMConfig.validate_dict({"boundaries": {"max_source_bytes": 0}})
