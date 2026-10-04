"""Provenance models and W3C PROV-JSON projection."""
from .model import ProvenanceRecord
from .prov_json import to_prov_json
__all__ = ["ProvenanceRecord", "to_prov_json"]
