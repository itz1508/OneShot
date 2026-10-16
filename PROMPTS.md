# Reusable Workflow Prompts

No `PLANS.md` currently exists. Replace bracketed placeholders with an explicitly approved plan or phase; do not infer a roadmap.

## Repository Orientation

Read all applicable `AGENTS.md` files, then `GOALS.md`, `PLANS.md` if present, relevant harness/context/review artifacts, current Git status and branch, implementation entry points, tests, and verification records. Perform read-only discovery only. Identify the exact disposable repository and benchmark copies, summarize applicable instructions, active architecture, evidence gaps, rollback boundary, and explicit non-goals. Do not write, commit, push, deploy, access credentials, contact external services, or begin planning or implementation. Stop after the orientation report.

## Plan or Phase Preparation

Read applicable `AGENTS.md`, `GOALS.md`, `PLANS.md` if present, and the orientation evidence. Prepare a dependency-ordered plan for `[approved objective]` only. Define ownership, approval gates, baseline red test, green condition, refactor boundary, verification checks, and handoff evidence. Do not invent phases or product requirements. Before any later repository write, require an approval summary naming proposed files and commands. Do not modify files or begin execution; stop with the proposed plan and unresolved decisions.

## Execute One Approved Phase

Read applicable `AGENTS.md`, `GOALS.md`, the approved plan/phase `[identifier]`, and relevant source, tests, harness, and review evidence. Run a read-only preflight and reproduce the approved baseline failure. Present an approval summary covering scope, files, commands, risks, and non-goals; wait for explicit write approval. Then execute only this phase using red, green, and the smallest justified refactor. Preserve documented contracts and unrelated behavior. Keep commits, pushes, deployments, credentials, remote operations, and external writes separately gated. Stop after this phase and report observed results.

## Verification and Evidence Gathering

Read applicable `AGENTS.md`, `GOALS.md`, the approved plan/phase, relevant diffs, tests, and prior results. Start with a read-only preflight and state exactly what will be verified; obtain approval before any repository write. Run the shared regression fixture in every assigned benchmark copy, relevant existing checks, normal revision-save coverage, and final diff inspection. Record commands, exit status, and observed output; distinguish skipped or unavailable checks. Do not remediate, commit, push, deploy, use credentials, or perform external writes. Stop with evidence and remaining risks.

## Review or Remediation

Read applicable `AGENTS.md`, `GOALS.md`, the approved phase, implementation diff, review findings, and verification evidence. First review read-only and rank evidence-supported defects against the selected phase; avoid speculative scope. For remediation, provide an approval summary naming exact files, tests, risks, and non-goals, then wait for approval. Apply only the smallest approved correction, repeating red, green, focused refactor, and verification as applicable. Do not commit, push, deploy, access credentials, or start another phase. Stop with findings and observed remediation results.

## Phase Completion and Handoff

Read applicable `AGENTS.md`, `GOALS.md`, the approved plan/phase, final diff, test output, and review artifacts. Perform a read-only completion audit against the phase's success conditions. Request approval before writing any handoff artifact. Report changed files, commands and observed results, preserved contracts, skipped checks, risks, limitations, rollback information, and unresolved decisions. Do not claim completion without evidence; do not commit, push, deploy, access credentials, perform external writes, or begin the next phase. Stop at handoff.
