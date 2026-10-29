# Research — reusable workflow template

**Applicability:** Use for a source-grounded investigation when the requested outcome is supported findings, requirements, validation values, or an evidence gap. Research can be the only requested work; do not presume Plan or Build follows.

**Existing authority:** The host establishes authorized source scope and tools. Use the current request and already accepted decisions without reasking or inventing values. The authoritative result shape is `output/schema/research.json` (Draft 2020-12). Result storage, when invoked, belongs to the existing Task store. This document is neither a selector nor a storage schema.

**Quality Input:** Use the shared strict contract `templates/schema/input.json`, with `template_id` set to `research`. The selected template is explicit; this does not select a workflow, infer missing fields, ask questions, or grant host permissions. `readiness: blocked` must disclose blocking unknowns. The host decides how to resolve them before execution.

## Inputs and investigation

- User objective, intended audience and explicit exclusions; available source identities, relevant versions/hashes and citations. If a necessary source or meaning is unavailable, report the gap, not a guess.
- Search/inspect only authorized sources. Differentiate observed facts, accepted decisions, external references, historical records, proposals and unresolved contradictions. Cite exact source locations where supported.
- For each material finding, explain what the evidence establishes and what it does **not** establish. Preserve conditions, negatives, source coverage and conflicting evidence.
- Answer, where applicable: **How will the goal's success be observed? Why does that success matter?** Establish evidence-backed success criteria, validation values and realistic fixture expectations as research findings; do not fabricate independent oracle values.

## Result and ownership

- Host produces one `Research(id)` conforming to the existing Research JSON schema. Encode source-grounded evidence and source-backed findings with `statement` and `source_refs`; represent independently supported verification values in optional `validation_values`, use `limitations` for gaps, contradictions and unrepresentable required information.
- A `source_refs` entry must be a meaningful source identity/location, not a pretend evidence reference. Missing independent evidence must be disclosed rather than replaced with an invented citation.
- **Contract:** Optional typed `validation_values` include a stable ID, criterion, expected value and source references. The schema verifies shape, not provenance truth, unique IDs or semantic correctness; fixture evidence must remain independent. Do not invent values. There are no separate typed `fixtures` or `success_criteria` fields.
- Research does not own implementation design, code writes, approval, or a generic recommendation to Build. Only conduct recommendation analysis when explicitly selected as the research objective.

## Completion / handoff

- Complete Research when required findings and their provenance are documented, or material gaps are explicitly recorded; structural validation alone does not establish factual truth.
- Handoff references the Research result's **existing** ID and preserves original source details. Another independently selected template may consume the result, but there is **no automatic next stage**, no authorization transfer and no repository mutation from this document.
