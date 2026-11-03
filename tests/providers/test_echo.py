"""Test echo provider generate."""

from agent.runtime.providers.base import ProviderRequest
from agent.runtime.providers.echo import EchoProvider


def test_echo_generate():
    p = EchoProvider()
    q = ProviderRequest(run_id="r", prompt="hello")
    result = p.generate(q)
    assert result.content.startswith("echo:")
    assert result.provider == "echo"
