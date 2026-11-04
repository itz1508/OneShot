# Audit Discovery

**Start:** Follow up from `/research_requested.md` when provided. Identify the assigned `task_id`, `request_id`, and `request_revision`.

**What to do**
1. Read the assigned request and all relevant Research results supplied by the host. Use their actual references; do not assume there is only one result.
2. Read applicable repository instructions and inspect the repository as it exists. Discover the relevant files, entrypoints, consumers, dependencies, configuration, tests, and current behavior from the source.
3. Record what exists, what is missing, and what conflicts with the accepted user intent. Attach file/line or other verifiable source evidence to each finding.
4. Check the repository identity before and after inspection. If the source changed materially, report the change instead of treating the findings as stable.
5. Prepare the findings, requirement assessments, and candidate CodeIntent for `/plans.md`. Request missing information from Research through the host when needed.

**Return:** The Audit Discovery result through the registered `audit_discovery_record` output (`_audit_discovery.json`). The host may render `/plans.md` from that result.

**Before returning:** Check that findings are grounded in inspected code and that unresolved questions remain visible. Do not edit source files, decide implementation strategy, or dispatch Build.
