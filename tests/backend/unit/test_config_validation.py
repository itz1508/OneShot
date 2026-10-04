import pytest
from rsm.config.schema import RSMConfig, ConfigValidationError


def test_defaults_valid():
    c = RSMConfig.validate_dict({})
    assert c.daemon.port == 8787


def test_unknown_key_rejected():
    with pytest.raises(ConfigValidationError):
        RSMConfig.validate_dict({"daemon": {"host": "127.0.0.1", "unknown": True}})


def test_bad_port_rejected():
    with pytest.raises(ConfigValidationError):
        RSMConfig.validate_dict({"daemon": {"port": 0}})
