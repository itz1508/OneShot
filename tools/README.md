# Tool adapters and active workspace reconciliation

This directory is deliberately **not** populated by renaming historical `src/` modules. Those modules have outdated assignment ownership and incomplete verification. The active Databricks `tools/` files could not be read from this GitHub checkout.

At milestone M0 in [the ExecPlan](../agent/implementation/ExecPlan.md), inventory the *physical* Databricks workspace and compare its tool interfaces, task storage, Scanner bridge, dirty state and tests against this Git repository. Integrate only verified current implementations; use one owner for Scanner and one existing Task Management store. Do not infer that the presence of this README provides runnable tools.

The harness must fail closed when Scanner, artifact resolution, or other required host interfaces are unavailable; it must not fabricate success receipts.
