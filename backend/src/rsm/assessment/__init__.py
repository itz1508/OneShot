"""rsm.assessment — Source Assessment capability.

Source Assessment answers one narrow architectural question:

    "Given a Bucket, what does RSM's observation + preparation boundary
     promise? What would be released? And what is the honest subset the
     Agent should rely on?"

It is NOT an intent classifier. It is NOT an Agent. It does NOT invoke
LLMs. It is a read-only, pure function of the frozen Bucket (A1 preserved).

Boundaries (same discipline as rsm.reader):

  * uses only stdlib + pydantic + rsm.bucket + rsm.reader
  * never imports rsm.snapshot / rsm.replay / rsm.classification / rsm.execution
  * never performs network I/O
  * never evaluates prepared text

The surface the HTTP layer exposes is `assess_source(bucket)` returning a
`SourceAssessment` DTO.

See `docs/decisions/0016-source-assessment-and-prepared-representation.md`.
"""

from .model import SourceAssessment, SourceAssessmentFiles, SourceAssessmentReason
from .assess import assess_source

__all__ = [
    "SourceAssessment",
    "SourceAssessmentFiles",
    "SourceAssessmentReason",
    "assess_source",
]
