"""rsm.prepared — Prepared Representation envelope.

The Prepared Representation is the typed boundary RSM crosses between
Processor (preparation) and Replay (release). It is NOT a new domain
object; it unites the three existing stable outputs that already describe
what RSM has observed, prepared, and will deliver:

    * SOURCE identity + integrity    — rsm.bucket (A1)
    * READER coverage                — rsm.reader.ReaderTrace (what was
                                        actually observed, per-File
                                        failures preserved)
    * PROCESSOR output                — rsm.snapshot.Snapshot (bounded,
                                        derived preparation of the
                                        Bucket's normalized source)
    * RELEASE envelope                — rsm.replay.build_replay_envelope
                                        (source=rsm, provenance, integrity)
    * ASSESSMENT                      — rsm.assessment.SourceAssessment
                                        (what the host app can rely on
                                        before the Agent reasons)

The `/v1/interactions/{id}/stream` payload already contains four of these
five parts. This module adds the single missing part — the Reader
coverage — and gives the whole thing one explicit name:

    `PreparedRepresentation`

so that the architectural doctrine

    SOURCE → OBSERVATION → PREPARATION → RELEASE → AGENT

is readable in both the code and the API payload. No existing payload key
is renamed; `prepared_representation` is an additive, backward-compatible
alias of the same object.
"""

from .model import PreparedRepresentation, build_prepared_representation

__all__ = [
    "PreparedRepresentation",
    "build_prepared_representation",
]
