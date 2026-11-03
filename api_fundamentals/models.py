"""Models for api_fundamentals probe results."""

from pydantic import BaseModel


class StructuredProbeResult(BaseModel):
    """Result of the structured_output capability probe."""

    capability: str
    supported: bool
    observation: str
