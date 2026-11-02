"""Test-only support — scripted adapters, golden evidence, recording helpers.

NOTHING in this package is imported by production code. The modules here are
test infrastructure: they let the behavior-based evaluator axes grade real
provider output without needing a live provider in CI, while keeping the
replay layer visible and auditable.
"""
